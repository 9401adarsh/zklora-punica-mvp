## Detailed Rewrite: CPU-First MVP Server -> All-Module -> `ezkl-gpu` -> Kernel-Prep
**Timeline:** March 11, 2026 to April 1, 2026 (21 days)  
**Execution model:** All implementation, tests, and benchmarks run in VM container workspace.  
**Primary KPI:** Stable throughput (`req_tps`) under concurrent proof generation with bounded queues and non-blocking inference.

### 1. Locked Baseline (Immutable Through Gate 2)
1. `base_model_id = distilgpt2`
2. `adapter_id = ng0-k1/distilgpt2-finetuned-es`
3. `proof_scope = prefill_only`
4. `target_module_path = transformer.h.0.attn.c_attn`
5. `proof_mode in {every_request, sampled}`
6. `sample_n` required only when `proof_mode=sampled`
7. `prover_backend = cpu`
8. Single adapter enforced
9. Single proof module enforced
10. Decode hooks disabled
11. All-module mode disabled
12. GPU prover disabled
13. Kernel path disabled

### 2. Operational Rules (Environment + Branching)
1. Local host control commands only:
- `./infra/scripts/start-dev.sh`
- `./infra/scripts/ssh-instance.sh`
- `./infra/scripts/stop-dev.sh`

2. VM shell entry sequence:
- `cd ~/zklora-punica-mvp/infra/docker`
- `docker compose up -d dev`
- `docker exec -it aa-zklora-dev bash`

3. In-container rules:
- All code edits under `/workspace`
- Tests/benchmarks run only in container context
- Runtime outputs and benchmark artifacts under `artifacts/`

4. Branching and checkpoint rules:
- Working branch: `mvp-phase1-cpu`
- One commit per phase gate minimum
- Tag pass commits: `gate1-pass` ... `gate6-pass`
- Store gate evidence files in `artifacts/gates/gateN/`

### 3. Architecture (v1 Runtime Contracts)
#### 3.1 Core components
1. `api_server`
2. `config`
3. `schemas`
4. `model_runtime`
5. `proof_hook_registry`
6. `hook_capture`
7. `hashing`
8. `sampling_policy`
9. `witness_queue`
10. `witness_logger`
11. `proof_queue`
12. `proof_job_manifest`
13. `prover_worker`
14. `zklora_adapter`
15. `proof_store`
16. `receipt_builder`
17. `metrics_telemetry`
18. `benchmark_harness`
19. `analysis_report`

#### 3.2 End-to-end request flow
1. Client sends `POST /infer`
2. Config guard validates adapter/mode constraints
3. Runtime executes prefill
4. Hook captures `x_pre` and `delta_post` for target module
5. Hashing layer canonicalizes and computes `H_x`, `H_delta`
6. Sampling policy determines proof inclusion
7. Inference response + receipt returned immediately
8. If sampled:
- enqueue witness packet via bounded non-blocking queue
- on full queue: mark `dropped_overload`, increment metric

9. Logger drains witness queue:
- persists tensor files + metadata
- emits pointer-only `ProofJob`
- appends job to durable manifest

10. Prover worker drains proof queue:
- sets status `pending`
- executes `zklora_adapter.prove(job)`
- persists proof refs + timings
- terminal status: `ready` or `failed`

11. Client polls `GET /proof/{request_id}` for async proof state

### 4. Data/Hash Determinism Contract
1. Tensor canonicalization before hashing:
- cast to `float32`
- contiguous C-order layout
- include exact shape and dtype metadata
- CPU buffer serialization only

2. Hash algorithm:
- `sha256`
- `hash_schema_version = 1`

3. Receipt/proof records must include:
- `H_x`, `H_delta`, `hash_schema_version`

4. Determinism criteria:
- identical request inputs and fixed seed produce identical hashes
- same canonicalization contract applies to CPU and GPU phases

### 5. Status Model and State Transitions
1. Valid statuses:
- `queued`
- `pending`
- `ready`
- `failed`
- `not_sampled`
- `dropped_overload`

2. Transition rules:
- unsampled: `not_sampled` terminal
- sampled enqueue success: `queued`
- worker pickup: `queued -> pending`
- success: `pending -> ready`
- prover error: `pending -> failed`
- enqueue overflow: `dropped_overload` terminal

3. Invalid transitions are rejected and logged

4. Restart behavior:
- replay `queued|pending` from persisted manifest/index
- preserve terminal states unchanged

### 6. File + Interface Spec (Decision Complete)
#### 6.1 Directories
1. `mvp_server/`
2. `mvp_server/api/`
3. `mvp_server/runtime/`
4. `mvp_server/proof/`
5. `mvp_server/metrics/`
6. `bench/`
7. `artifacts/`

#### 6.2 Required files and responsibilities
1. `mvp_server/config.py`
- typed config model
- strict validation
- startup fail-fast on baseline violations

2. `mvp_server/schemas.py`
- `Receipt`
- `WitnessRecord`
- `ProofJob`
- `ProofRecord`
- shared status enum
- `schema_version` and `hash_schema_version`

3. `mvp_server/api/server.py`
- `POST /infer`
- `GET /proof/{request_id}`
- `GET /health`
- `GET /metrics`

4. `mvp_server/runtime/model_runtime.py`
- load model/tokenizer/adapter
- canonical module resolution
- hook registration lifecycle
- prefill execution wrapper

5. `mvp_server/runtime/proof_hook_registry.py`
- `ProofModuleSpec` registry
- single active module in v1
- module discovery hooks for Phase 4

6. `mvp_server/runtime/hook_capture.py`
- capture `x_pre` and `delta_post`
- shape/type checks
- packetization for downstream

7. `mvp_server/runtime/hashing.py`
- canonicalization + hashing implementation
- hash metadata assembly

8. `mvp_server/proof/sampling_policy.py`
- `every_request`
- deterministic sampled mode using stable hash over `(request_id,module_id)`

9. `mvp_server/proof/witness_queue.py`
- bounded non-blocking queue
- overflow counter and telemetry hooks

10. `mvp_server/proof/witness_logger.py`
- persist:
  - `artifacts/witness/{request_id}/{module_id}/x.npy`
  - `artifacts/witness/{request_id}/{module_id}/delta.npy`
  - `artifacts/witness/{request_id}/{module_id}/meta.json`
- emit pointer-only proof jobs

11. `mvp_server/proof/proof_queue.py`
- bounded queue for proof jobs
- queue depth instrumentation

12. `mvp_server/proof/proof_job_manifest.py`
- append-only persisted job metadata
- replay support on restart

13. `mvp_server/proof/prover_worker.py`
- consume proof jobs
- invoke adapter
- write `ProofRecord`
- set terminal/non-terminal status transitions

14. `mvp_server/proof/zklora_adapter.py`
- CPU proving wrapper in v1
- normalized timings/errors
- backend switch scaffolding for Phase 5

15. `mvp_server/proof/proof_store.py`
- status index by `request_id`
- lookup and transition validation
- persisted record refs

16. `mvp_server/receipt_builder.py`
- construct synchronous receipts with status hints

17. `mvp_server/metrics/metrics.py`
- counters/histograms/gauges
- snapshot serializer for `/metrics`

18. `bench/loadgen_prefill_synth.py`
- synthetic matrix executor

19. `bench/loadgen_prompts_mixed.py`
- mixed prompt benchmark runner

20. `bench/analyze_runs.py`
- frontier extraction
- queue slope and lag analysis

### 7. API Contracts (v1 + Error Semantics)
#### 7.1 `POST /infer`
1. Request fields:
- `prompt` (required)
- `adapter_id` (optional; if present must equal baseline adapter)
- optional generation params

2. Response fields:
- `output`
- `receipt`:
  - `request_id`
  - `adapter_id`
  - `module_id`
  - `sampled`
  - `H_x`
  - `H_delta`
  - `hash_schema_version`
  - `proof_status_hint`

3. Error behavior:
- unknown adapter in v1 -> `400 adapter_not_allowed`
- config/boot invalidity -> startup fail-fast, not runtime fallback

#### 7.2 `GET /proof/{request_id}`
1. `202 pending` for `queued|pending`
2. `200 ready`
3. `200 not_sampled`
4. `200 failed`
5. `200 dropped_overload`
6. `404 unknown` for missing request

#### 7.3 `GET /health`
1. process liveness
2. model loaded flag
3. worker thread/process alive flag

#### 7.4 `GET /metrics`
1. serialized point-in-time counters and histograms

### 8. Phase Plan With Daily Intent + Gates
#### Phase 1 (Days 1-4): Serving Skeleton + Deterministic Capture
1. Build config/schemas/server skeleton
2. Integrate runtime load path and fixed module resolution
3. Implement hooks + capture packets
4. Implement hash canonicalization + receipt builder
5. Return response without async proving enabled

**Gate 1 pass criteria**
1. `POST /infer` works for baseline model/adapter
2. fixed module path resolves and logs canonical match
3. `H_x`, `H_delta`, `hash_schema_version` present
4. repeated fixed-seed run yields stable hashes
5. no async proof worker dependency for serving success

#### Phase 2 (Days 5-7): Async Proof Pipeline (CPU)
1. Add witness queue and overflow mapping
2. Add witness logger + artifact persistence
3. Add proof queue + job manifest persistence
4. Add prover worker and proof store transitions
5. Expose proof polling endpoint

**Gate 2 pass criteria**
1. sampled request transitions `queued/pending -> ready`
2. unsampled request yields `not_sampled`
3. forced prover error yields `failed`
4. queue overflow yields `dropped_overload`
5. serving remains non-blocking under induced prover slowdown
6. restart replay restores `queued|pending` jobs and completes processing

#### Phase 3 (Days 8-11): Telemetry + Baseline Load
1. Add end-to-end metrics instrumentation
2. Run synthetic matrix (`every_request`, sampled N)
3. Generate first stability frontier report on T4 baseline environment

**Gate 3 pass criteria**
1. report includes:
- max stable req/s
- p50/p95 infer latency
- proof/sec
- witness/proof queue depth trends
- receipt-to-proof lag p50/p95
- drop counts by status

2. at least one stable sampled operating point validated
3. reproducibility manifest present for each run

#### Phase 4 (Days 12-14): All-Module Expansion
1. enable module discovery and multiple `ProofModuleSpec`
2. emit one witness/proof path per `(request_id,module_id)`
3. add guardrails:
- `max_modules_per_request`
- whitelist/blacklist
- optional per-module sampling override

4. retain backward-compatible v1 API shapes

**Gate 4 pass criteria**
1. single request can expose per-module proof states
2. v1 endpoints remain backward compatible
3. throughput degradation measured and documented against Phase 3 baseline

#### Phase 5 (Days 15-17): `ezkl-gpu` Backend
1. add backend switch in adapter/wrapper (`cpu|gpu`)
2. preserve CPU behavior as reference default
3. rerun Phase 3 matrix with matched configs

**Gate 5 pass criteria**
1. CPU vs GPU comparison table complete
2. frontier delta published
3. inference latency contention impact quantified

#### Phase 6 (Days 18-21): Decode Scaffolding + Kernel-Prep
1. add decode hook scaffolding behind feature flag
2. add decode-specific sampling controls
3. define `BatchWitnessEnvelope`:
- `batch_id`
- `x_batch_ref`
- `delta_batch_ref`
- deterministic row map from batch rows to request/module ranges

4. draft A/B kernel benchmark protocol

**Gate 6 pass criteria**
1. decode toggle does not regress prefill proof path
2. kernel-phase interface spec is implementation-ready
3. benchmark protocol is executable without unresolved design decisions

### 9. Benchmark Plan (Exact Runs + Reproducibility)
#### 9.1 Synthetic prefill matrix
1. Modes:
- `every_request`
- `sampled N in {2,4,8,16,32}`

2. Duration:
- warmup 2 min
- measure 5 min

3. Metrics:
- `req_tps`
- infer latency p50/p95
- witness queue depth over time
- proof queue depth over time
- proof/sec
- receipt-to-proof lag p50/p95
- drop counts by cause

#### 9.2 Mixed prompt run
1. fixed short/medium/long prompt set
2. run best `N` selected from synthetic matrix
3. collect same metrics and compare to synthetic frontier point

#### 9.3 Artifact outputs per run
1. `artifacts/runs/<timestamp>/metrics.jsonl`
2. `artifacts/runs/<timestamp>/config_snapshot.json`
3. `artifacts/runs/<timestamp>/run_manifest.json`
4. `artifacts/runs/<timestamp>/analysis_summary.md`

#### 9.4 Mandatory run manifest fields
1. git commit SHA
2. container image digest
3. CUDA/driver/runtime versions (if applicable)
4. model + adapter IDs
5. proof mode and sampling config
6. seed(s)
7. hardware descriptor

### 10. Failure Semantics (Authoritative)
1. Witness enqueue full:
- inference succeeds
- status `dropped_overload`
- increment overflow metric
- no proof job emitted

2. Unsampled request:
- status `not_sampled`
- no proof job emitted

3. Prover exception:
- status `failed`
- record `error_code`, `error_message`, timing span

4. Unknown proof request:
- return `404 unknown` unless index contains non-terminal state

5. Restart:
- rebuild non-terminal jobs from manifest/index
- maintain terminal states as immutable

6. Corrupt artifact pointer:
- mark `failed` with explicit error code
- never block serving path

### 11. Test Plan (Must Exist Before Gate 3)
#### 11.1 Unit
1. module path resolution and canonicalization
2. hook capture shape/type assertions
3. hash determinism with fixed seed
4. sampling determinism
5. queue overflow -> status mapping
6. status transition guard validation

#### 11.2 Integration
1. `queued/pending -> ready` happy path
2. `not_sampled` path
3. `failed` path via forced prover error
4. `dropped_overload` path under bounded queue pressure
5. polling correctness for all statuses
6. restart recovery for non-terminal jobs

#### 11.3 Load/soak
1. 30-minute sampled run near frontier
2. verify queue boundedness
3. verify no status corruption
4. verify lag remains within expected frontier envelope

### 12. Risks and Mitigations
1. Adapter/model mismatch:
- startup compatibility check + fail-fast

2. Hook path drift due to wrappers:
- emit canonical module list at startup
- hard fail if configured path not exact-match

3. Disk I/O pressure in witness logging:
- pointer-only jobs
- compact metadata writes
- retention policy for old artifacts

4. Prover throughput bottleneck:
- sampled mode tuning
- explicit overload semantics
- queue depth telemetry and alerts

5. Environment drift:
- container-only execution
- run manifest snapshots

6. Scope creep:
- no decode/kernel implementation before Gate 3 completion evidence

### 13. Definition of Done
1. CPU-first MVP serves inference and async proofs end-to-end on VM
2. `every_request` and sampled modes behave per defined status semantics
3. deterministic hashes and restart-safe pipeline are verified
4. first stability frontier is measured and archived with reproducibility metadata
5. all-module decomposition works with documented throughput tradeoff
6. CPU vs GPU proof comparison is completed
7. kernel-phase interfaces and benchmark protocol are implementation-ready

### 14. Assumptions (Locked)
1. Throughput/stability are prioritized over full security hardening in this window
2. Benchmark breadth may be reduced if schedule slips; gate criteria remain mandatory
3. CPU path is correctness reference; GPU path must match functional semantics
4. API backward compatibility is preserved through Gate 4 for existing v1 clients
