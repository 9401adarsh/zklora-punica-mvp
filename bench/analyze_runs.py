from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from bench.phase3_common import linear_slope, percentile, read_json, read_jsonl, write_json


def _summarize_run(run_dir: Path) -> dict[str, Any]:
    config = read_json(run_dir / "config_snapshot.json")
    events = read_jsonl(run_dir / "request_events.jsonl")
    metrics = read_jsonl(run_dir / "metrics.jsonl")
    store = read_json(run_dir / "runtime_artifacts" / "proof" / "proof_store.json")

    measure_start = float(config["measure_start"])
    measure_end = float(config["measure_end"])
    duration = max(1e-6, measure_end - measure_start)

    measured_events = [e for e in events if e.get("phase") == "measure"]
    infer_latencies = [float(e.get("infer_latency_ms", 0.0)) for e in measured_events]
    reqps = len(measured_events) / duration

    records = store.get("records", {})
    status_counts: dict[str, int] = {}
    lag_seconds: list[float] = []
    proof_ready = 0
    drops = 0

    for rec in records.values():
        status = str(rec.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "ready":
            proof_ready += 1
        if status == "dropped_overload":
            drops += 1
        lifecycle = rec.get("lifecycle_timestamps", {})
        accepted = lifecycle.get("request_accepted_at")
        terminal = lifecycle.get("terminal_at")
        if accepted is not None and terminal is not None:
            lag = float(terminal) - float(accepted)
            if lag >= 0.0:
                lag_seconds.append(lag)

    queue_samples: list[tuple[float, float]] = []
    for row in metrics:
        ts = float(row.get("ts", 0.0))
        if ts < measure_start or ts > measure_end:
            continue
        snap = row.get("metrics", {})
        gauges = snap.get("gauges", {})
        queue_samples.append((ts, float(gauges.get("proof_manifest_unclaimed", 0.0))))

    queue_slope = linear_slope(queue_samples)
    queue_max = max((v for _, v in queue_samples), default=0.0)

    drop_rate = drops / max(1, len(records))
    proofs_per_sec = proof_ready / duration

    return {
        "run_dir": str(run_dir),
        "proof_mode": config.get("proof_mode"),
        "sample_n": config.get("sample_n"),
        "concurrency": int(config.get("concurrency", 1)),
        "measure_duration_sec": duration,
        "req_per_sec": reqps,
        "infer_p50_ms": percentile(infer_latencies, 0.50),
        "infer_p95_ms": percentile(infer_latencies, 0.95),
        "proofs_per_sec": proofs_per_sec,
        "lag_p50_sec": percentile(lag_seconds, 0.50),
        "lag_p95_sec": percentile(lag_seconds, 0.95),
        "queue_slope_items_per_sec": queue_slope,
        "queue_max": queue_max,
        "drop_rate": drop_rate,
        "status_counts": status_counts,
    }


def _is_stable(result: dict[str, Any], epsilon: float, drop_threshold: float) -> tuple[bool, str]:
    if float(result["queue_slope_items_per_sec"]) > epsilon:
        return False, f"queue_slope>{epsilon}"
    if float(result["drop_rate"]) > drop_threshold:
        return False, f"drop_rate>{drop_threshold}"
    return True, "stable"


def _render_summary(results: list[dict[str, Any]], epsilon: float, drop_threshold: float) -> str:
    lines: list[str] = []
    lines.append("# Phase-3 Analysis Summary")
    lines.append("")
    lines.append(f"Stability thresholds: queue_slope <= {epsilon}, drop_rate <= {drop_threshold}")
    lines.append("")
    lines.append("| mode | sample_n | conc | req/s | infer p50 ms | infer p95 ms | proofs/s | lag p50 s | lag p95 s | queue slope | drop rate | stable | reason |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")

    stable_results: list[dict[str, Any]] = []
    stable_sampled: list[dict[str, Any]] = []

    for r in results:
        stable, reason = _is_stable(r, epsilon, drop_threshold)
        if stable:
            stable_results.append(r)
            if r.get("proof_mode") == "sampled":
                stable_sampled.append(r)
        lines.append(
            "| {mode} | {n} | {c} | {req:.2f} | {p50:.2f} | {p95:.2f} | {pps:.2f} | {l50:.3f} | {l95:.3f} | {qs:.4f} | {dr:.4f} | {stable} | {reason} |".format(
                mode=r.get("proof_mode"),
                n=r.get("sample_n") if r.get("sample_n") is not None else "-",
                c=r.get("concurrency"),
                req=float(r.get("req_per_sec", 0.0)),
                p50=float(r.get("infer_p50_ms", 0.0)),
                p95=float(r.get("infer_p95_ms", 0.0)),
                pps=float(r.get("proofs_per_sec", 0.0)),
                l50=float(r.get("lag_p50_sec", 0.0)),
                l95=float(r.get("lag_p95_sec", 0.0)),
                qs=float(r.get("queue_slope_items_per_sec", 0.0)),
                dr=float(r.get("drop_rate", 0.0)),
                stable="yes" if stable else "no",
                reason=reason,
            )
        )

    lines.append("")
    if stable_results:
        best = max(stable_results, key=lambda x: float(x["req_per_sec"]))
        lines.append("## Max Stable Frontier Point")
        lines.append(
            f"- mode={best['proof_mode']} sample_n={best.get('sample_n')} concurrency={best['concurrency']} req/s={best['req_per_sec']:.2f}"
        )
    else:
        lines.append("## Max Stable Frontier Point")
        lines.append("- none")

    lines.append("")
    if stable_sampled:
        best_s = max(stable_sampled, key=lambda x: float(x["req_per_sec"]))
        lines.append("## Selected Stable Sampled Point")
        lines.append(
            f"- sample_n={best_s.get('sample_n')} concurrency={best_s['concurrency']} req/s={best_s['req_per_sec']:.2f}"
        )
    else:
        lines.append("## Selected Stable Sampled Point")
        lines.append("- none")

    lines.append("")
    lines.append("## Reproducibility")
    lines.append("- See each run directory's run_manifest.json and config_snapshot.json.")
    return "\n".join(lines) + "\n"


def analyze_batch(batch_dir: Path, epsilon: float, drop_threshold: float) -> dict[str, Any]:
    run_dirs = sorted([p for p in batch_dir.iterdir() if p.is_dir() and (p / "config_snapshot.json").exists()])
    results = [_summarize_run(run_dir) for run_dir in run_dirs]
    summary_md = _render_summary(results, epsilon=epsilon, drop_threshold=drop_threshold)

    (batch_dir / "analysis_summary.md").write_text(summary_md, encoding="utf-8")
    write_json(batch_dir / "analysis_summary.json", {"results": results})
    return {"results": results, "summary_path": str(batch_dir / "analysis_summary.md")}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase-3 benchmark analyzer")
    parser.add_argument("--batch-dir", required=True)
    parser.add_argument("--epsilon", type=float, default=0.1)
    parser.add_argument("--drop-threshold", type=float, default=0.01)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = analyze_batch(Path(args.batch_dir), epsilon=args.epsilon, drop_threshold=args.drop_threshold)
    print(result["summary_path"])


if __name__ == "__main__":
    main()
