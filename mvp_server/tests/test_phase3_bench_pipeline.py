from pathlib import Path

from bench.analyze_runs import analyze_batch
from bench.loadgen_prefill_synth import run_matrix


def test_synthetic_run_and_analysis_outputs(tmp_path: Path) -> None:
    batch_dir = run_matrix(
        output_root=tmp_path,
        warmup_sec=0.05,
        measure_sec=0.15,
        prompt="hello",
        concurrency_list=[1],
        sampled_n_values=[2],
        use_fake_runtime=True,
    )

    assert (batch_dir / "batch_index.json").exists()
    assert (batch_dir / "mode-every_request-c1" / "metrics.jsonl").exists()
    assert (batch_dir / "mode-sampled-n2-c1" / "run_manifest.json").exists()

    result = analyze_batch(batch_dir, epsilon=0.1, drop_threshold=0.01)
    summary_path = Path(result["summary_path"])
    assert summary_path.exists()
    content = summary_path.read_text(encoding="utf-8")
    assert "Phase-3 Analysis Summary" in content
    assert "Max Stable Frontier Point" in content
