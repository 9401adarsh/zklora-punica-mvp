## MVP Server Architecture RFC Plan (Detailed + Tradeoffs)

### Summary
- Produce a new standalone deep engineering RFC at `plans/mvp-server-architecture-rfc.md`.
- Document the architecture as implemented today (threaded worker + `cpu|gpu` prover backend + async receipt/status flow), then add a focused “near-term deltas” section for GPU trust and utilization risks.
- Include Mermaid diagrams, sequence/state flow, and explicit tradeoff analysis per subsystem.

### Key Implementation Changes
- **New RFC structure (single canonical doc):**
  - Context and goals: problem framing, constraints, non-goals.
  - End-to-end data flow: `POST /infer` path, witness persistence, manifest enqueue, worker claim/process, `GET /proof/{id}` lifecycle.
  - Subsystem contracts:
    - Config and invariants (`proof_mode`, `prover_backend`, `proof_worker_threads`, `inference_device`, hash contract).
    - Runtime/hook capture and witness boundary.
    - Manifest + claims + proof store durability semantics.
    - Worker threading model and adapter lifecycle.
    - Prover adapter backend routing behavior and stage timings.
    - Metrics/observability boundaries.
  - Failure model: status semantics, fail-fast behavior, overload handling, recovery expectations.
  - Tradeoff matrix: for each subsystem, include “Decision”, “Why”, “Pros”, “Cons”, “Operational risk”, “When to revisit”.
- **Diagrams to include in Markdown (Mermaid + short text):**
  - Component architecture diagram.
  - Request/worker sequence diagram.
  - Proof status state machine diagram.
  - Threaded worker concurrency diagram (dispatcher + worker pool).
- **Public APIs/interfaces/types section (explicitly documented):**
  - API contract surfaces: `POST /infer`, `GET /proof/{request_id}`, `get_health`, `get_metrics`.
  - Receipt and proof record fields (including lifecycle timestamps/artifact refs).
  - Worker/prover interface expectations and backend intent (`cpu|gpu`) behavior.
- **Near-term deltas section (bounded, not speculative):**
  - Backend trust validation architecture (runtime intent + CUDA checks + PID correlation evidence).
  - Utilization-focused measurement deltas (cold vs steady-state split, backend/thread isolation runs).
  - Criteria for declaring “GPU backend confidence: low/medium/high”.

### Test Plan (Doc Quality + Technical Correctness)
1. **Implementation parity check:** every major claim in RFC maps to current code behavior in `mvp_server/api/server.py`, `mvp_server/proof/prover_worker.py`, and `mvp_server/proof/zklora_adapter.py`.
2. **Contract consistency check:** statuses, transitions, and response semantics match existing schema/store behavior.
3. **Tradeoff completeness check:** each subsystem has both benefits and liabilities; no one-sided justification.
4. **Diagram validation check:** each Mermaid diagram aligns with described sequence/state text and current implementation.
5. **Review readiness check:** professor can answer “why this architecture now?” and “what are the top risks?” from the document alone.

### Assumptions and Defaults
- Audience is technical (independent-study professor + engineering review).
- Depth target is deep RFC, not presentation summary.
- Existing phase/check-in docs remain as historical/supporting artifacts; the new RFC becomes the canonical architecture reference.
- Scope includes implemented architecture plus tightly scoped near-term deltas for GPU trust/utilization only (no broad future-state redesign).
