from __future__ import annotations

import argparse
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

import numpy as np

from bench.phase3_common import (
    append_jsonl,
    ensure_dir,
    now_ts,
    run_manifest_payload,
    utc_label,
    write_json,
)
from mvp_server.api.server import MVPServer
from mvp_server.config import AppConfig
from mvp_server.proof.prover_worker import ProverWorker
from mvp_server.proof.zklora_adapter import ZkLoraAdapter
from mvp_server.runtime.model_runtime import InferenceResult


class FakeRuntime:
    loaded = True

    def infer_prefill(self, prompt: str, generation_params: Optional[dict[str, Any]] = None) -> InferenceResult:
        _ = generation_params
        size = max(8, min(64, len(prompt)))
        x = np.ones((1, size), dtype=np.float32)
        d = np.full((1, size), 0.5, dtype=np.float32)
        return InferenceResult(
            output=prompt,
            module_id="transformer.h.0.attn.c_attn",
            h_x="hx",
            h_delta="hd",
            hash_schema_version=1,
            x_pre=x,
            delta_post=d,
        )


def _worker_loop(worker: ProverWorker, stop: threading.Event, sleep_s: float = 0.01) -> None:
    while not stop.is_set():
        if not worker.run_once():
            time.sleep(sleep_s)


def _load_thread(
    server: MVPServer,
    prompt: str,
    stop: threading.Event,
    events_path: Path,
    phase_fn,
) -> None:
    while not stop.is_set():
        t0 = now_ts()
        resp = server.post_infer({"prompt": prompt})
        t1 = now_ts()
        append_jsonl(
            events_path,
            {
                "ts": t1,
                "phase": phase_fn(),
                "request_id": resp["receipt"]["request_id"],
                "proof_status_hint": resp["receipt"]["proof_status_hint"],
                "infer_latency_ms": (t1 - t0) * 1000.0,
            },
        )


def _metrics_sampler(
    server: MVPServer,
    stop: threading.Event,
    metrics_path: Path,
    interval_s: float,
) -> None:
    while not stop.is_set():
        snap = server.get_metrics()
        append_jsonl(metrics_path, {"ts": now_ts(), "metrics": snap})
        time.sleep(interval_s)


def run_single_point(
    run_dir: Path,
    proof_mode: str,
    sample_n: Optional[int],
    concurrency: int,
    warmup_sec: float,
    measure_sec: float,
    prompt: str,
    use_fake_runtime: bool,
) -> dict[str, Any]:
    ensure_dir(run_dir)
    runtime_artifacts = ensure_dir(run_dir / "runtime_artifacts")

    cfg_data: dict[str, Any] = {
        "proof_mode": proof_mode,
        "artifacts_root": str(runtime_artifacts),
    }
    if sample_n is not None:
        cfg_data["sample_n"] = sample_n
    cfg = AppConfig.from_dict(cfg_data)

    server = MVPServer(config=cfg, runtime=FakeRuntime() if use_fake_runtime else None)
    worker = ProverWorker(
        manifest=server.proof_manifest,
        proof_store=server.proof_store,
        adapter=ZkLoraAdapter(str(runtime_artifacts)),
    )

    metrics_path = run_dir / "metrics.jsonl"
    events_path = run_dir / "request_events.jsonl"

    phase = {"value": "warmup"}

    def phase_fn() -> str:
        return phase["value"]

    stop_workers = threading.Event()
    worker_thread = threading.Thread(target=_worker_loop, args=(worker, stop_workers), daemon=True)
    worker_thread.start()

    stop_load = threading.Event()
    load_threads = [
        threading.Thread(
            target=_load_thread,
            args=(server, prompt, stop_load, events_path, phase_fn),
            daemon=True,
        )
        for _ in range(concurrency)
    ]
    for t in load_threads:
        t.start()

    stop_metrics = threading.Event()
    metrics_thread = threading.Thread(
        target=_metrics_sampler,
        args=(server, stop_metrics, metrics_path, 1.0),
        daemon=True,
    )
    metrics_thread.start()

    time.sleep(max(0.0, warmup_sec))
    phase["value"] = "measure"
    measure_start = now_ts()
    time.sleep(max(0.0, measure_sec))
    measure_end = now_ts()

    stop_load.set()
    for t in load_threads:
        t.join(timeout=2.0)

    stop_workers.set()
    worker_thread.join(timeout=1.0)

    # Drain any leftover jobs synchronously after worker thread exits.
    drain_deadline = now_ts() + 2.0
    while now_ts() < drain_deadline and server.proof_manifest.unclaimed_count() > 0:
        worker.run_once()

    stop_metrics.set()
    metrics_thread.join(timeout=1.0)

    config_snapshot = {
        "proof_mode": proof_mode,
        "sample_n": sample_n,
        "concurrency": concurrency,
        "warmup_sec": warmup_sec,
        "measure_sec": measure_sec,
        "prompt_len": len(prompt),
        "measure_start": measure_start,
        "measure_end": measure_end,
    }
    write_json(run_dir / "config_snapshot.json", config_snapshot)

    manifest = run_manifest_payload(
        {
            "proof_mode": proof_mode,
            "sample_n": sample_n,
            "model_id": cfg.base_model_id,
            "adapter_id": cfg.adapter_id,
        }
    )
    write_json(run_dir / "run_manifest.json", manifest)

    records = server.proof_store.all_records()
    status_counts: dict[str, int] = {}
    for rec in records.values():
        status_counts[rec.status] = status_counts.get(rec.status, 0) + 1

    summary = {
        "run_dir": str(run_dir),
        "proof_mode": proof_mode,
        "sample_n": sample_n,
        "concurrency": concurrency,
        "measure_duration_sec": measure_end - measure_start,
        "total_requests": sum(status_counts.values()),
        "status_counts": status_counts,
    }
    write_json(run_dir / "point_summary.json", summary)
    return summary


def run_matrix(
    output_root: Path,
    warmup_sec: float,
    measure_sec: float,
    prompt: str,
    concurrency_list: list[int],
    sampled_n_values: list[int],
    use_fake_runtime: bool,
) -> Path:
    batch_dir = ensure_dir(output_root / utc_label())
    points: list[dict[str, Any]] = []

    matrix: list[tuple[str, Optional[int]]] = [("every_request", None)]
    matrix.extend(("sampled", n) for n in sampled_n_values)

    for proof_mode, sample_n in matrix:
        for concurrency in concurrency_list:
            tag = f"mode-{proof_mode}"
            if sample_n is not None:
                tag += f"-n{sample_n}"
            tag += f"-c{concurrency}"
            run_dir = ensure_dir(batch_dir / tag)
            result = run_single_point(
                run_dir=run_dir,
                proof_mode=proof_mode,
                sample_n=sample_n,
                concurrency=concurrency,
                warmup_sec=warmup_sec,
                measure_sec=measure_sec,
                prompt=prompt,
                use_fake_runtime=use_fake_runtime,
            )
            points.append(result)

    write_json(batch_dir / "batch_index.json", {"points": points})
    return batch_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase-3 synthetic prefill loadgen")
    parser.add_argument("--output-root", default="artifacts/runs")
    parser.add_argument("--warmup-sec", type=float, default=120.0)
    parser.add_argument("--measure-sec", type=float, default=300.0)
    parser.add_argument("--prompt", default="Explain zk proofs in one paragraph.")
    parser.add_argument("--concurrency", default="1,2,4,8")
    parser.add_argument("--sampled-n", default="2,4,8,16,32")
    parser.add_argument("--use-fake-runtime", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    concurrency_list = [int(x) for x in args.concurrency.split(",") if x.strip()]
    sampled_n_values = [int(x) for x in args.sampled_n.split(",") if x.strip()]
    batch_dir = run_matrix(
        output_root=Path(args.output_root),
        warmup_sec=args.warmup_sec,
        measure_sec=args.measure_sec,
        prompt=args.prompt,
        concurrency_list=concurrency_list,
        sampled_n_values=sampled_n_values,
        use_fake_runtime=args.use_fake_runtime,
    )
    print(str(batch_dir))


if __name__ == "__main__":
    main()
