# MVP Server Design Summary After Phase-2

## 1. What Phase-2 Delivers

Phase-2 turns the Phase-1 scaffold into a durable async proof pipeline with a separate worker process.

At a high level:
- `POST /infer` still returns immediately.
- If sampled, the server persists witness tensors to disk and appends a pointer-only proof job to a manifest.
- A separate worker process claims jobs from the manifest, runs prover logic, and updates shared proof status.
- Clients poll `GET /proof/{request_id}` for lifecycle states.

Core invariant: inference latency remains decoupled from proof generation latency.

---

## 2. End-to-End Server Process

### 2.1 Request path (`POST /infer`)
1. Validate prompt and adapter lock.
2. Run prefill inference with one active proof hook target.
3. Capture `x_pre` and `delta_post`; canonicalize and hash to produce `H_x`, `H_delta`.
4. Evaluate deterministic sampling policy.
5. If unsampled:
   - Set proof status to `not_sampled` (terminal).
6. If sampled:
   - Persist witness files: `x.npy`, `delta.npy`, `meta.json`.
   - Append pointer-only `ProofJob` to JSONL manifest.
   - Set proof status to `queued`.
   - On persistence/append exception, set `dropped_overload`.
7. Return output + receipt with `proof_status_hint`.

### 2.2 Worker path (separate process)
1. Poll manifest for unclaimed jobs.
2. Claim a job by writing request id to claims log.
3. Transition status `queued -> pending`.
4. Run prover adapter.
5. On success: transition `pending -> ready` and attach proof artifact refs.
6. On failure: transition `pending -> failed` with error metadata.

### 2.3 Query path (`GET /proof/{request_id}`)
- `404` for unknown request id.
- `202` for non-terminal active states (`queued`, `pending`).
- `200` for terminal states (`ready`, `failed`, `not_sampled`, `dropped_overload`).

---

## 3. Component-by-Component Design and Tradeoffs

## 3.1 `AppConfig` (`mvp_server/config.py`)

Decision:
- Keep strict Phase-1 baseline constraints (single adapter/module, CPU prover, prefill-only).
- Add Phase-2 filesystem/process knobs:
  - `artifacts_root`
  - optional manifest/claims/store path overrides
  - worker poll interval

Why this was chosen:
- Preserves baseline reproducibility while enabling practical runtime deployment flexibility.

Tradeoffs:
- Pros: deterministic startup constraints, fewer runtime surprises, easy container defaults (`/artifacts`).
- Cons: less flexible for experimentation; hard guardrails mean new modes require code changes, not config-only toggles.

---

## 3.2 API server orchestration (`mvp_server/api/server.py`)

Decision:
- Keep synchronous inference response model.
- Move proof work to best-effort enqueue path with explicit fallback status `dropped_overload`.
- Store statuses durably via shared `ProofStore` file.

Why this was chosen:
- Protects user-facing inference latency and availability from prover latency/failures.

Tradeoffs:
- Pros: simple API contract; predictable client behavior; async proof path does not block generation.
- Cons: enqueue persistence currently happens inline in request path; disk contention can still affect request latency.

---

## 3.3 Runtime inference + hook capture (`mvp_server/runtime/model_runtime.py`, `hook_capture.py`)

Decision:
- Capture one module’s pre/post tensors at prefill time.
- Return canonical tensors in `InferenceResult` (not only hashes).

Why this was chosen:
- Witness persistence requires canonical tensor payloads to be available immediately in the API process.

Tradeoffs:
- Pros: no re-run needed for witness construction; clean handoff to persistence layer.
- Cons: larger in-memory request footprint; single-module scope limits proof coverage breadth in this phase.

Sub-decision (Torch→NumPy fallback):
- If `tensor.numpy()` fails with "Numpy is not available", fallback to `tensor.tolist()` then canonicalize.
- Tradeoff: improved portability across torch/numpy builds vs modest conversion overhead.

---

## 3.4 Deterministic hashing contract (`mvp_server/runtime/hashing.py`)

Decision:
- Canonicalize to contiguous `float32` and hash `header + bytes` with SHA-256.
- Keep `hash_schema_version=1` locked.

Why this was chosen:
- Ensures repeatable digests for receipts and cross-stage verification.

Tradeoffs:
- Pros: stable hashes across equivalent numeric inputs and memory layouts.
- Cons: `float32` cast may lose higher precision; schema upgrades require explicit migration/version handling.

---

## 3.5 Sampling policy (`mvp_server/proof/sampling_policy.py`)

Decision:
- Support `every_request` and deterministic `sampled` mode via hash bucket on `(request_id,module_id)`.

Why this was chosen:
- Deterministic sampling is simple and reproducible without storing RNG state.

Tradeoffs:
- Pros: deterministic and stateless; operationally simple.
- Cons: UUID-based request ids make exact sampled subset unpredictable beforehand; not traffic-adaptive.

---

## 3.6 Witness persistence (`mvp_server/proof/witness_logger.py`)

Decision:
- Persist each sampled witness under:
  - `{artifacts_root}/witness/{request_id}/{module_id}/x.npy`
  - `{artifacts_root}/witness/{request_id}/{module_id}/delta.npy`
  - `{artifacts_root}/witness/{request_id}/{module_id}/meta.json`

Why this was chosen:
- File-based artifacts are easy to inspect, copy, and feed into future prover backends.

Tradeoffs:
- Pros: transparent and debuggable artifact layout; no database dependency.
- Cons: many small files at high QPS; no compression/chunking strategy yet.

---

## 3.7 Manifest-backed spool (`mvp_server/proof/proof_job_manifest.py`)

Decision:
- Use append-only JSONL job log plus JSONL claims log.
- Worker discovers unclaimed jobs by replaying records and subtracting claimed ids.

Why this was chosen:
- Minimal infrastructure, auditable logs, and straightforward restart semantics.

Tradeoffs:
- Pros: operational simplicity; replay/debug friendliness; aligns with "separate process" requirement.
- Cons:
  - claim operation is not a cross-process transactional lock.
  - replay cost grows linearly with manifest size.
  - no compaction/rotation yet.

---

## 3.8 Durable proof state machine (`mvp_server/proof/proof_store.py`)

Decision:
- Persist status records to disk (`proof_store.json`) with transition validation.
- Enforced transitions:
  - `queued -> pending -> ready|failed`
  - terminal passthrough for `not_sampled`, `dropped_overload`, `ready`, `failed`

Why this was chosen:
- API and worker need shared, restart-safe truth for request status.

Tradeoffs:
- Pros: explicit lifecycle safety; easy client polling semantics.
- Cons:
  - file-based store is single-node oriented.
  - full-file rewrite on updates may become costly under heavy churn.

---

## 3.9 Prover adapter (`mvp_server/proof/zklora_adapter.py`)

Decision:
- Implement deterministic fake-proof path in Phase-2.
- Produce stable JSON artifacts (`proof.json`, `public.json`) and timing metadata.

Why this was chosen:
- Unblocks integration and lifecycle testing before real prover backend hardening.

Tradeoffs:
- Pros: fast and reliable CI/integration loop; deterministic failure injection (`force_fail`).
- Cons: does not measure true proving performance or backend-specific error surface.

---

## 3.10 Worker process (`mvp_server/proof/prover_worker.py`)

Decision:
- Ship standalone module CLI worker with three modes:
  - `--once`
  - `--max-jobs`
  - continuous polling

Why this was chosen:
- Supports local debugging, batch processing, and service-style operation with one implementation.

Tradeoffs:
- Pros: clear process boundary from API server; easy operational control.
- Cons: polling loop introduces idle wakeups; no external queue backpressure protocol yet.

---

## 3.11 Schemas/contracts (`mvp_server/schemas.py`)

Decision:
- Keep receipt contract stable while extending witness/proof job fields for pointer-only handoff.

Why this was chosen:
- Preserve client compatibility while enabling durable internal Phase-2 pipeline.

Tradeoffs:
- Pros: minimal API breakage; clear internal handoff records.
- Cons: schema evolution currently manual; no migration framework/version negotiation yet.

---

## 3.12 Metrics and observability (`mvp_server/metrics/metrics.py` + API usage)

Decision:
- Keep lightweight in-memory counters/gauges and expose snapshot endpoint.

Why this was chosen:
- Lowest-friction instrumentation for MVP behavior checks.

Tradeoffs:
- Pros: easy to add/inspect; no external metrics system required.
- Cons: not durable, not multi-process aggregated, limited production observability.

---

## 4. Status Model (Operational Semantics)

Defined statuses:
- `queued`
- `pending`
- `ready`
- `failed`
- `not_sampled`
- `dropped_overload`

Design intent:
- Distinguish "not selected" (`not_sampled`) from "selected but could not enqueue/persist" (`dropped_overload`).
- Keep `queued/pending` as explicit async-progress states for polling behavior.

Tradeoff summary:
- Better client transparency vs slightly more lifecycle complexity.

---

## 5. Testing Strategy in This Phase

Coverage added/updated includes:
- server API lifecycle states (`queued`, `not_sampled`, `dropped_overload`)
- manifest append + claim/replay behavior
- proof-store transition enforcement
- witness persistence file outputs
- adapter success/failure
- integration path `queued -> ready` via worker

Tradeoff:
- Strong deterministic functional coverage now, but still limited load/concurrency stress against file-based manifest/store under multi-worker conditions.

---

## 6. Key Phase-2 Design Choices and Why They Were Accepted

1. Separate worker process over in-process thread
- Accepted for stronger isolation and clearer production trajectory.
- Cost: requires durable handoff and shared-state design complexity.

2. Manifest-backed spool over drop-dir/DB queue
- Accepted because existing JSONL abstraction already existed and is easy to reason about.
- Cost: weaker concurrency guarantees than transactional queue systems.

3. File-based durable state over database
- Accepted for MVP speed and low infrastructure burden.
- Cost: scalability and contention limits appear sooner.

4. Deterministic fake prover in Phase-2
- Accepted to validate pipeline correctness before real backend hardening.
- Cost: performance and backend integration risk deferred to next phase.

5. Strict baseline constraints retained
- Accepted to reduce confounders while stabilizing async architecture.
- Cost: feature expansion (multi-module, GPU proving) deferred.

---

## 7. Current Known Limitations (Post Phase-2)

- Manifest claim mechanism is append-log based, not transactional locking.
- No manifest compaction/rotation strategy yet.
- `ProofStore` is file-backed and single-node oriented.
- Metrics are process-local and in-memory.
- Prover adapter is still fake/deterministic, not real zkLoRA proving.
- Queue helpers (`ProofQueue`, `WitnessQueue`) remain secondary to the manifest-path in the separate-worker design.

These are expected tradeoffs for this phase and are consistent with the chosen implementation priorities.
