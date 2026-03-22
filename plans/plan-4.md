## Phase-4 Execution Checklist: Single-Adapter ZKLoRA Integration

### Summary
Implement real ZKLoRA proving in the async worker path for one configured adapter, replacing fake proofs while preserving existing API/status behavior.

### Task-Ordered Build Plan
1. **Add adapter runtime config wiring**
- Update `mvp_server/proof/zklora_adapter.py` constructor to accept `artifacts_root`, `base_model_id`, `adapter_id`.
- Update `mvp_server/proof/prover_worker.py` `build_worker_from_config()` to pass those fields from `AppConfig`.
- Keep process model unchanged: separate worker process remains authoritative.

2. **Refactor adapter internals into explicit stages**
- In `ZkLoraAdapter`, split `prove(job)` into private helpers:
  - `_load_witness_inputs(job)` reads `meta.json` and tensor refs from witness artifacts.
  - `_load_or_get_peft_model()` loads base model + single adapter once and caches in adapter instance.
  - `_resolve_target_submodule(module_id)` validates module exists on PEFT model.
  - `_export_onnx_and_inputs(...)` emits ONNX + JSON into per-job proof work dir.
  - `_run_zklora_prove(...)` invokes local ZKLoRA APIs and validates expected outputs.
  - `_collect_proof_refs(...)` normalizes final `proof_ref/public_ref`.
- Keep `ProveResult` contract unchanged.

3. **Define proof artifact contract**
- Standardize output under `{artifacts_root}/proofs/{request_id}/{module_id}/`.
- Require at minimum:
  - proof artifact ref (`.pf` or canonical proof file from ZKLoRA output),
  - public/settings ref for verification path,
  - optional auxiliary refs kept in same directory.
- Return canonical refs in `ProveResult` so `ProofStore.artifact_refs` remains stable.

4. **Lock error mapping and no-fallback policy**
- Remove fake-proof generation from success path.
- Any adapter-stage failure raises `RuntimeError` with stage-prefixed message (`load_witness`, `resolve_module`, `export`, `prove`, `collect`).
- Worker keeps existing behavior and maps exception to:
  - status `failed`,
  - `error_code="prove_failed"`,
  - propagated `error_message`.

5. **Compatibility and guardrails**
- Preserve `POST /infer` and `GET /proof/{request_id}` payload shapes.
- Keep single-adapter guard (`adapter_id` match) and single-module flow unchanged.
- Do not introduce all-module logic or per-module API expansion in this phase.

6. **Documentation updates**
- Update `plans/plan-4.md` with the final checklist and acceptance criteria.
- Update `mvp_server/README.md` worker section to clarify “real ZKLoRA proofs enabled in phase-4” and artifact expectations.
- Add short troubleshooting notes for missing `ezkl/onnxruntime/peft` runtime errors.

### Test Plan
1. **Adapter unit tests**
- `test_zklora_adapter_prove_writes_artifacts`: update to assert real proof artifact refs (not fake `proof.json/public.json` assumptions).
- Add `test_zklora_adapter_module_missing_fails` for invalid `module_id`.
- Keep `force_fail` path only if still intentionally supported; otherwise replace with deterministic mock failure test.

2. **Worker integration tests**
- `test_prover_worker_pending_to_ready`: assert `ready` and real artifact refs populated.
- `test_prover_worker_pending_to_failed`: assert `failed`, `error_code="prove_failed"`, and non-empty message.

3. **API/status regression tests**
- Re-run existing API/status suite to confirm `queued|pending|ready|failed|not_sampled|dropped_overload` semantics unchanged.
- Ensure no backward-incompatible response field changes.

4. **Phase-4 functional gate**
- End-to-end sampled request:
  - server returns immediate receipt,
  - worker processes asynchronously,
  - `GET /proof/{request_id}` transitions to `ready` with real proof refs.

### Assumptions
- Scope is strictly single-adapter ZKLoRA integration (not all-module expansion).
- Integration path is direct local ZKLoRA Python API usage (no MPI socket service).
- No fake-proof fallback is allowed on proof failure.
- Inference-time PEFT adapter loading is out of scope for this phase (prove-only integration).

### Acceptance Criteria (Phase-4 Functional Gate)
- Sampled request returns immediate receipt while worker processes proof asynchronously.
- Worker reads witness metadata/tensor refs and runs staged ZKLoRA proof flow (`load_witness`, `resolve_module`, `export`, `prove`, `collect`).
- Successful proof writes artifacts under `{artifacts_root}/proofs/<request_id>/<module_id>/` and stores proof/public refs in `ProofStore`.
- Adapter errors are surfaced as stage-prefixed `RuntimeError` messages and worker maps them to `failed` with `error_code=prove_failed`.
- Existing API payload shapes and status semantics remain backward compatible.
