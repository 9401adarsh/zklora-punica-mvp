## Phase-2 Plan: Durable Async Proof Pipeline (Separate Worker Process)

### Summary
Phase-1 is complete and stable: config guards, deterministic hashing, receipt contract, runtime hook capture, API skeleton, and core unit tests are in place (with the NumPy fallback fix already validated).  
Phase-2 will implement real witness persistence plus asynchronous proving via a **separate worker process** using a **manifest-backed spool**, with artifacts rooted at a **configurable path defaulting to `/artifacts`**, and a deterministic fake-prover fallback for reliability.

### Implementation Changes
- Server-side enqueue flow:
  - Extend runtime result contract to include canonicalized tensors needed for witness persistence (not just hashes) so `POST /infer` can persist sampled requests.
  - In [`/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/api/server.py`] add Phase-2 flow:
    - sampled request: persist witness, append proof job to manifest, set status `queued`.
    - unsampled request: set status `not_sampled`.
    - enqueue/persist overload/failure path: set `dropped_overload`.
  - Keep HTTP response schema unchanged; receipt still returns immediate `proof_status_hint`.

- Durable storage + shared state:
  - Implement [`/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/witness_logger.py`] to write:
    - `x.npy`, `delta.npy`, `meta.json` under `{artifacts_root}/witness/{request_id}/{module_id}/`.
  - Extend [`/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/proof_job_manifest.py`] from append/read to include claim/replay helpers for worker consumption.
  - Refactor [`/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/proof_store.py`] to persist status records to disk (shared by server + worker), with valid transition enforcement:
    - `queued -> pending -> ready|failed`
    - terminal passthrough for `not_sampled|dropped_overload`.

- Worker process + prover:
  - Implement [`/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/prover_worker.py`] as manifest-driven processor:
    - claim job, set `pending`, call adapter, set `ready|failed`, record artifact refs/error fields.
  - Implement [`/home/ext_adas2133_colorado_edu/zklora-punica-mvp/mvp_server/proof/zklora_adapter.py`] with deterministic fake-proof fallback and structured timings/errors.
  - Add worker entrypoint command (module CLI) for standalone execution in container.

- Config/API/interface additions:
  - Add config fields for `artifacts_root` (default `/artifacts`) and Phase-2 queue/worker knobs needed by server + worker.
  - Internal interface changes:
    - `InferenceResult` gains witness payload references needed for persistence.
    - `ProofJob`/`ProofRecord` fields finalized for pointer-only job contract and proof refs.

### Test Plan
- Unit tests:
  - witness persistence writes expected files/metadata and returns pointer refs.
  - manifest append + claim + replay behavior.
  - proof store transition validation (valid and invalid transitions).
  - adapter fake-prover success and forced-failure paths.
- Integration tests:
  - sampled request lifecycle: `queued -> pending -> ready`.
  - forced prover failure: `queued -> pending -> failed`.
  - unsampled request returns/stays `not_sampled`.
  - overload path returns/stays `dropped_overload`.
  - `GET /proof/{request_id}` returns `202` for non-terminal and `200` for terminal statuses; `404` for unknown.
- Regression:
  - preserve existing Phase-1 API/config/hash tests.

### Assumptions Locked
- Worker model: **separate process** (no in-process thread runner in this phase).
- Job handoff: **manifest-backed spool** (not drop-dir).
- Artifacts path: **configurable**, default **`/artifacts`**.
- Prover behavior: deterministic fake-proof fallback is enabled for MVP stability; failure paths remain explicitly testable.