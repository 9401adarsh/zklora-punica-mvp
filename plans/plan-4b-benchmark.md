### Phase 4b - Proper Bounded Benchmark Harness (Full PEFT)

**Summary**
- Current state confirmation: the system already supports multi-threaded proving via `ProverWorker(proof_worker_threads=...)`; `MVPServer` itself enqueues jobs but does not autonomously run proof worker threads.
- Build a proving-focused bounded benchmark harness that uses full PEFT in the proof path (no fake PEFT model), supports parameterized request counts and worker thread counts, and emits direct CPU/GPU + threads + request-count comparisons.
- Use `requests + timeout` bounds (selected) so runs never hang indefinitely.

**Implementation Changes**
- Add a new benchmark entrypoint (e.g. `bench/phase4b_bounded_peft.py`) with CLI parameters:
  - `--backends` (csv, default `cpu,gpu`)
  - `--threads` (csv, default `1,2`)
  - `--requests` (csv, default `5,20`)
  - `--timeout-sec` (default `900`)
  - `--request-concurrency` (default `1`)
  - `--output-root` and optional prompt/seed knobs.
- Harness run flow per matrix point:
  - Create isolated artifacts dir per `(backend, threads, requests)`.
  - Build `AppConfig` with `proof_mode=every_request`, selected backend/threads.
  - Use synthetic 3D inference packets for request generation only (proving-focused mode).
  - Use real `ZkLoraAdapter` defaults (no injected fake `model_loader`/`exporter`/`prove_runner`) to enforce full PEFT + real exporter + real EZKL.
  - Enqueue exactly `N` requests, run worker loop with stop condition, and terminate on either all-terminal completion or timeout.
- Add bounded execution mechanics:
  - Implement harness-level stop control with explicit timeout detection and partial-result capture.
  - Record timeout status per matrix point (`completed`, `timed_out`, `failed_fast`).
- Persist comparison-ready outputs:
  - `summary.json` with per-point metrics.
  - `summary.md` with compact comparison tables for:
    - threads scaling at fixed backend/requests,
    - backend deltas at fixed threads/requests.
- Extend timing capture for real stage metrics:
  - Update adapter/worker path so stage tuple (`setup`, `witness`, `prove`, `total`) is persisted per request when available from proof generator.
  - Keep backward compatibility when stage tuple is missing.

**Public Interfaces / Types**
- New benchmark CLI contract (args above) becomes the official bounded benchmark interface.
- Benchmark output schema in `summary.json`:
  - run metadata (`backend`, `threads`, `requests`, `timeout_sec`, `status`)
  - proof outcome counts (`ready`, `failed`, `pending`, etc.)
  - throughput (`req_per_sec`)
  - per-stage timing aggregates (`setup`, `witness`, `prove`, `total`)
  - `prover_duration_ms` stats and error samples.
- If adapter timing is extended: `ProveResult` gains optional stage timing fields; worker persists them in artifact refs.

**Test Plan**
- Add fast unit tests for matrix expansion, parameter parsing, and bounded stop behavior (including timeout path).
- Add tests ensuring comparison outputs are deterministic in shape and include all required keys.
- Add integration smoke (small `N`) validating full-PEFT path is used (no fake model injection) and run reaches terminal statuses.
- Acceptance scenarios:
  - `(cpu,gpu) x (threads 1,2) x (requests 5,20)` with timeout bound.
  - Expected outcome: `ready:N` on available backend; deterministic fail-fast with clear backend error when GPU runtime is unavailable.

**Assumptions / Defaults**
- Chosen mode: proving-focused harness with full PEFT proof path.
- Chosen bound policy: `max_requests + timeout`.
- Single worker process with intra-process thread pool only (no multi-process worker orchestration).
- Inference is synthetic for benchmark stability; proving path is real.
- Default matrix: backends `cpu,gpu`, threads `1,2`, requests `5,20`, timeout `900s`, request concurrency `1`.
