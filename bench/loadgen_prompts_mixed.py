from __future__ import annotations

import argparse
from pathlib import Path

from bench.loadgen_prefill_synth import run_single_point
from bench.phase3_common import ensure_dir, utc_label, write_json


MIXED_PROMPTS = [
    "Summarize LoRA adapters in one sentence.",
    "Explain how asynchronous proof pipelines decouple latency from throughput in a system that returns immediate receipts and polls for terminal proof states.",
    "Write a detailed paragraph describing the tradeoffs between deterministic sampled proving and every-request proving for bounded queue systems in GPU-backed inference services.",
]


def run_mixed(
    output_root: Path,
    sample_n: int,
    concurrency: int,
    warmup_sec: float,
    measure_sec: float,
    use_fake_runtime: bool,
) -> Path:
    batch_dir = ensure_dir(output_root / f"mixed-{utc_label()}")
    prompts_path = batch_dir / "prompts.txt"
    prompts_path.write_text("\n".join(MIXED_PROMPTS), encoding="utf-8")

    point_summaries = []
    for idx, prompt in enumerate(MIXED_PROMPTS):
        run_dir = ensure_dir(batch_dir / f"prompt-{idx+1}")
        summary = run_single_point(
            run_dir=run_dir,
            proof_mode="sampled",
            sample_n=sample_n,
            concurrency=concurrency,
            warmup_sec=warmup_sec,
            measure_sec=measure_sec,
            prompt=prompt,
            use_fake_runtime=use_fake_runtime,
        )
        point_summaries.append(summary)

    write_json(batch_dir / "batch_index.json", {"points": point_summaries})
    return batch_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase-3 mixed prompt loadgen")
    parser.add_argument("--output-root", default="artifacts/runs")
    parser.add_argument("--sample-n", type=int, required=True)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--warmup-sec", type=float, default=120.0)
    parser.add_argument("--measure-sec", type=float, default=300.0)
    parser.add_argument("--use-fake-runtime", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    batch_dir = run_mixed(
        output_root=Path(args.output_root),
        sample_n=args.sample_n,
        concurrency=args.concurrency,
        warmup_sec=args.warmup_sec,
        measure_sec=args.measure_sec,
        use_fake_runtime=args.use_fake_runtime,
    )
    print(str(batch_dir))


if __name__ == "__main__":
    main()
