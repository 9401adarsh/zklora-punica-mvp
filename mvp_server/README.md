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

## Live CLI Interaction (Two Terminals)

**All commands below are executed inside the dev container at `/workspace`.**

If needed, from host shell:

```bash
docker compose -f infra/docker/docker-compose.yml up -d dev
docker compose -f infra/docker/docker-compose.yml exec dev bash
cd /workspace
```

`MVPServer` is currently an in-process API surface (not an HTTP daemon), so live interaction is done via Python CLI.

Open two terminals in the same dev container and use the same artifacts root.

### Terminal A: run worker continuously

```bash
cd /workspace
export MVP_ARTIFACTS_ROOT=/workspace/artifacts/live-cli
export MVP_PROOF_MODE=every_request
export MVP_PROVER_BACKEND=gpu
export MVP_PROOF_WORKER_THREADS=1
python3 -m mvp_server.proof.prover_worker
```

### Terminal B: interactive prompt loop

```bash
cd /workspace
export MVP_ARTIFACTS_ROOT=/workspace/artifacts/live-cli
export MVP_PROOF_MODE=every_request
export MVP_PROVER_BACKEND=gpu

python3 - <<'PY'
import time
from mvp_server.api.server import MVPServer
from mvp_server.config import AppConfig

srv = MVPServer(config=AppConfig.from_env())
print("Type prompt text. 'quit' to exit.")

while True:
    prompt = input('prompt> ').strip()
    if prompt in {'quit', 'exit'}:
        break
    if not prompt:
        continue

    resp = srv.post_infer({'prompt': prompt})
    rid = resp['receipt']['request_id']
    print('receipt:', resp['receipt'])

    for _ in range(240):
        code, proof = srv.get_proof(rid)
        status = proof.get('status')
        print('proof_status:', status, '(http-like code:', code, ')')
        if status in {'ready', 'failed', 'not_sampled', 'dropped_overload'}:
            break
        time.sleep(0.5)
PY
```

Note: both terminals must share the same `MVP_ARTIFACTS_ROOT`, and both must run inside the same container.

Do not run these commands on the host shell; run both terminals in the same container.

## Runtime Behavior

- `POST /infer` returns immediately with a receipt.
- Inference defaults to GPU (`inference_device=cuda`).
- Sampled requests are persisted under `{artifacts_root}/witness/<request_id>/<module_id>/`.
- A pointer-only proof job is appended to the manifest.
- Worker transitions proof status: `queued -> pending -> ready|failed`.
- Worker concurrency uses a thread pool controlled by `proof_worker_threads`.
- Prover backend is selected by `prover_backend` (`cpu|gpu`).
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
- `gpu backend requested` failures:
  - verify CUDA is available in the worker runtime and rebuild with a GPU-capable EZKL package.

## Config (Env)

```bash
# defaults shown
export MVP_INFERENCE_DEVICE=cuda
export MVP_ARTIFACTS_ROOT=/artifacts
export MVP_WORKER_POLL_INTERVAL_MS=250
export MVP_PROVER_BACKEND=cpu
export MVP_PROOF_WORKER_THREADS=2

# optional explicit overrides
# export MVP_PROOF_MANIFEST_PATH=/artifacts/proof/proof_jobs.jsonl
# export MVP_PROOF_CLAIMS_PATH=/artifacts/proof/proof_claims.jsonl
# export MVP_PROOF_STORE_PATH=/artifacts/proof/proof_store.json
```
