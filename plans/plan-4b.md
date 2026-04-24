## Phase-4b MVP Plan: GPU Backend + Threaded Worker

### Summary
- Goal: hit meaningful proof performance gains quickly for MVP, not production hardening.
- Scope combines two levers:
  1. `cpu|gpu` proving backend path (EZKL runtime selection),
  2. thread-pooled worker (default 2 threads) for throughput.
- Keep proof semantics and API/status contract unchanged.

### Key Changes
- Extend config in [config.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/config.py):
  - `prover_backend: cpu|gpu`
  - `proof_worker_threads` default `2`
  - env wiring for both knobs
- Update worker orchestration in [prover_worker.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/prover_worker.py):
  - dispatcher claims jobs serially
  - N worker threads process jobs concurrently (each thread has its own adapter instance)
  - preserve `queued -> pending -> ready|failed` behavior and existing error mapping
- Update adapter/prover path in [zklora_adapter.py](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/zklora_adapter.py) and zk proof generator:
  - pass backend intent into proof generation
  - fail fast if `gpu` selected but GPU/EZKL GPU runtime unavailable
  - keep setup-cache reuse (`proof_setup`) unchanged
- Minimal infra change in [Dockerfile](/home/ext_adas2133_colorado_edu/zklora-punica-mvp/infra/docker/Dockerfile):
  - add a reproducible EZKL GPU-capable install path for MVP benchmarking
  - keep CPU fallback available

### MVP Acceptance Tests
- Functional:
  - 5-request run with `cpu` backend succeeds (`ready:5`)
  - 5-request run with `gpu` backend succeeds (`ready:5`) or fails fast with clear backend error
- Performance:
  - compare CPU vs GPU stage timings (`setup`, `witness`, `prove`, `total`)
  - compare `threads=1` vs `threads=2` throughput on same workload
- Regression:
  - existing adapter/worker tests still pass
  - API payload shape/status semantics unchanged

### Assumptions (MVP Defaults)
- No production hardening in this phase (no extensive fallback matrix, no rollout controls).
- No proof semantic relaxation; strict proofs only.
- Success criterion for MVP: measurable speedup signal + correctness parity, with documented benchmark artifacts.
