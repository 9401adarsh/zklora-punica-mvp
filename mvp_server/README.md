# MVP Server

GPU-default inference + async proof pipeline.

## Phase-2 Quick Start

Run from inside the dev container at `/workspace`.

```bash
# run tests
python3 -m pytest -q mvp_server/tests

# process one queued proof job
python3 -m mvp_server.proof.prover_worker --once

# process N jobs then exit
python3 -m mvp_server.proof.prover_worker --max-jobs 100

# run worker continuously
python3 -m mvp_server.proof.prover_worker
```

## Runtime Behavior

- `POST /infer` returns immediately with a receipt.
- Inference defaults to GPU (`inference_device=cuda`).
- Sampled requests are persisted under `{artifacts_root}/witness/<request_id>/<module_id>/`.
- A pointer-only proof job is appended to the manifest.
- Worker (separate async process) transitions proof status: `queued -> pending -> ready|failed`.
- Unsampled requests are `not_sampled`.
- Persistence/enqueue failures are marked `dropped_overload`.

## Phase-4 Proof Artifacts (Single Adapter)

- Real ZKLoRA proof generation is enabled in the worker adapter path.
- Proof outputs are written under `{artifacts_root}/proofs/<request_id>/<module_id>/`.
- Minimum expected outputs for a successful proof:
  - one proof artifact (`*.pf`)
  - one verification/settings artifact (`*_settings.json` or `*.vk`)
- Worker status and API response shapes remain backward compatible.

## Troubleshooting

- `ImportError` for `peft`, `onnxruntime`, or `ezkl`:
  - ensure dev container dependencies are installed and `PYTHONPATH` includes `zkLoRA` sources.
- `resolve_module` failures:
  - verify `target_module_path` maps to a LoRA-enabled submodule for the configured adapter.
- `export` failures:
  - validate witness `x_ref` exists and contains expected tensor shape for the target module.
- `prove` failures:
  - inspect per-job proof directory under `{artifacts_root}/proofs/<request_id>/<module_id>/` for generated ONNX/JSON artifacts.

## Config (Env)

```bash
# defaults shown
export MVP_INFERENCE_DEVICE=cuda
export MVP_ARTIFACTS_ROOT=/artifacts
export MVP_WORKER_POLL_INTERVAL_MS=250
# optional explicit overrides
# export MVP_PROOF_MANIFEST_PATH=/artifacts/proof/proof_jobs.jsonl
# export MVP_PROOF_CLAIMS_PATH=/artifacts/proof/proof_claims.jsonl
# export MVP_PROOF_STORE_PATH=/artifacts/proof/proof_store.json
```
