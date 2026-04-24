## Final Presentation Plan (April 23, 2026): zkLoRA-for-Serving MVP

### Summary
- Goal: present architecture, speedup strategy, measured outcomes, and strict claim boundaries.
- Storyline: background -> proof mechanics -> architecture -> speedup ideas -> results -> blockers.
- Confidence posture: CPU claims are claimable with reliability caveats; GPU proving remains non-claimable.
- Runtime target: 10-12 minutes with one-minute safety buffer.

### Core Story
1. **Background and relevance**
- Why proof-aware serving matters in practice.
- Quick intro to zkLoRA and why proving cost dominates deployment ergonomics.

2. **Proof mechanics**
- Explain major steps: export/setup/witness/prove/artifact persistence.
- Show where latency is concentrated and where optimization is meaningful.

3. **Architecture explanation**
- Use the mermaid component flow as the primary systems slide.
- Explain status lifecycle and async decoupling of inference vs proving.

4. **Speedup strategy**
- Idea 1: multi-thread proving + setup cache amortization across batch runs.
- Idea 2: move EZKL proving to GPU via `ezkl-gpu` path and evaluate potential gain.

5. **Scope and results**
- Scope and environment setup for reproducible benchmark cycle.
- CPU results: wall-time improvement with reliability tradeoff.
- GPU results: speedup currently non-claimable due to trust blockers.

6. **Blockers and future work**
- Reliability failures in multi-threaded runs.
- GPU routing/runtime validation blockers.
- Colocation economics question: `prove_time >> request_latency`.

### Slide-Level Message Anchors
1. **Title + objective**
- Set transparent, evidence-first framing.

2. **Background 1: why relevant**
- Motivate operational need for proof-aware serving.

3. **Background 2: zkLoRA quick intro**
- Define zkLoRA role and why proving dominates cost.

4. **What constitutes a proof**
- Explain end-to-end proof stages and timing targets.

5. **Architecture overview I**
- Walk through mermaid component flow.

6. **Architecture overview II**
- Explain lifecycle semantics and bottleneck localization.

7. **Speed up idea 1**
- Multi-thread wall-time reduction and setup cache reuse rationale.

8. **Speed up idea 2**
- GPU proving migration objective and required validation criteria.

9. **Scope of MVP + environment setup**
- Containers, offline mode, harness, and artifact paths.

10. **Results 1: CPU thread scaling**
- Throughput up with threads; reliability drops at higher concurrency.

11. **Results 2: GPU vs CPU**
- As of April 23, 2026, GPU speedup remains non-claimable.

12. **Blockers and future work**
- Reliability hardening, GPU route validation, and colocation decisioning.

13. **Q&A + appendix**
- Route deep technical questions to artifact-backed appendix.

### Detailed Script Per Slide (10-12 min)
1. **Slide 1 (0:50) - Title + objective**
- "Today I’ll walk through zkLoRA-for-serving from an engineering reality perspective: what we implemented, what measured well, and what is still blocked."
- "I want to make one expectation explicit up front: all claims are bounded to evidence as of April 23, 2026."
- "The short version is that CPU-side improvements are real and measurable, while GPU proving remains non-claimable in this cycle."
- Transition line: "With that framing, let me first explain why this problem matters outside a research setting."

2. **Slide 2 (0:55) - Background: why relevant**
- "If we want verifiable AI services, we need proof-aware serving, not just proof generation in isolated notebooks."
- "In production, users care about response experience, and operators care about reliability. So we need a system that can deliver inference quickly while generating proof artifacts safely in the background."
- "That creates a multi-objective problem: latency, throughput, reliability, and trust in backend behavior."
- Transition line: "Given that context, here is the quick zkLoRA mental model."

3. **Slide 3 (0:55) - Background: zkLoRA intro**
- "zkLoRA gives us a proving flow for LoRA-adapted model behavior, with artifacts that can be checked later."
- "The key practical point is that inference is usually much faster than proving. So even if the proving stack is correct, deployment quality depends heavily on system architecture and scheduling."
- "That is why this work focuses not only on cryptographic correctness but on operability under load."
- Transition line: "To make the optimization target concrete, let’s break down what a proof run actually does."

4. **Slide 4 (1:00) - What constitutes a proof**
- "At a high level, the proof path has five major steps: export/resolve artifacts, setup preparation, witness generation, prove execution, and artifact persistence."
- "In our timings, setup and prove are the dominant contributors, while witness generation is smaller but still relevant."
- "This decomposition is important because every speedup idea in this talk is basically trying to reduce or amortize one of these stages."
- Transition line: "Now that the pipeline is clear, I’ll map those stages to our serving architecture."

5. **Slide 5 (1:00) - Architecture overview I (mermaid)**
- "On this diagram, the left side is the user interaction path: `POST /infer` and `GET /proof/:request_id`."
- "The API handles inference and queueing decisions, while proof work is handed off to background workers through the manifest and proof store."
- "Witness artifacts and proof artifacts are persisted so state is durable and externally inspectable."
- "The main design decision is decoupling: inference responsiveness is protected even when proving is slow."
- Transition line: "Next I’ll describe how this architecture behaves over time through statuses and lifecycle semantics."

6. **Slide 6 (0:55) - Architecture overview II (execution semantics)**
- "The lifecycle is explicit: `queued` to `pending` to terminal states like `ready` or `failed`, plus `not_sampled` and `dropped_overload` when applicable."
- "Because states are explicit, we can distinguish true proof failures from policy outcomes, and we can measure where requests spend time."
- "This status model is also what enables credible benchmarking, because we can aggregate readiness and failure rates by scenario."
- Transition line: "With architecture in place, here were the two speedup strategies we tested."

7. **Slide 7 (0:55) - Speed up idea 1**
- "Idea one was straightforward: increase proof worker threads to reduce batch wall time."
- "We paired that with setup cache reuse to amortize expensive setup work instead of paying full setup repeatedly."
- "Conceptually this came from the same intuition as setup amortization in zkLoRA-style pipelines: reuse expensive precomputation whenever valid."
- "The expected tradeoff was potential reliability stress at higher concurrency, which we do observe in results."
- Transition line: "Idea two was the higher-upside path: moving proving to GPU."

8. **Slide 8 (0:55) - Speed up idea 2**
- "Idea two was to route EZKL proving through an `ezkl-gpu` path, since prove-heavy workloads are natural GPU candidates."
- "We modified the integration path so this could be attempted in the MVP environment."
- "But for this to be claimable, we need backend intent to match backend effective behavior with trustworthy evidence."
- "In this cycle, that confidence bar was not met, so we treat GPU performance claims as non-claimable."
- Transition line: "Before showing results, I’ll quickly ground the exact benchmark scope and infra."

9. **Slide 9 (0:50) - Scope + environment**
- "Runs were executed in controlled CPU and GPU containers with offline model/adapter constraints to avoid network drift."
- "We used a bounded harness matrix and persisted run artifacts, summaries, and telemetry for auditability."
- "So the numbers you see are reproducible from terminal commands and linked artifacts, not hand-curated screenshots."
- Transition line: "Now let’s look at the CPU results first, since those are the currently claimable performance results."

10. **Slide 10 (1:05) - Results 1 (CPU)**
- "CPU throughput improves as thread count increases from 1 to 5, with approximate wall time for 20 requests dropping from 32.24 minutes to 18.78 minutes."
- "At 10 threads, throughput is similar to 5 threads, so gains flatten."
- "The key caveat is reliability: ready rate declines as thread count rises, with recurring export-related failures in higher-thread runs."
- "So the honest takeaway is: we achieved wall-time reduction, but not at uniform reliability."
- Transition line: "Next is the question everyone asks: did GPU proving beat CPU in a claimable way?"

11. **Slide 11 (1:05) - Results 2 (GPU vs CPU)**
- "For matched CPU/GPU-intent runs, throughput alone does not establish trustworthy GPU proving speedup."
- "As of April 23, 2026, GPU speedup is non-claimable because routing confidence is low and Icicle-path instability appears in backtrace evidence."
- "So this slide is intentionally a trust-boundary slide, not a victory slide."
- "We are choosing credibility over overclaiming."
- Transition line: "Given that boundary, here are the blockers and the practical path forward."

12. **Slide 12 (1:00) - Blockers + future work**
- "First blocker is reliability under multithreaded proving, where failure taxonomy and mitigation need to improve."
- "Second blocker is GPU routing/runtime validation: we need strict routing guarantees and stable Icicle behavior before any GPU performance claim."
- "Third is systems economics: when proving time is much larger than request latency, we need to reevaluate how much colocation optimization is worth in this MVP context."
- "The strategy is to pass trust gates first, then optimize."
- Transition line: "I’ll close with the claim boundary and open Q&A."

13. **Slide 13 (0:40) - Q&A**
- "Closing summary: CPU improvements are real with reliability caveats; GPU proving claims remain intentionally gated."
- "If you want details, we can jump directly to appendix artifacts, including summary JSONs, telemetry logs, and version-sweep backtraces."
- "I’m happy to go deep on architecture, benchmark method, or blocker triage."

**Time check**
- Planned talk time: ~11:25
- Buffer: ~0:35 to 1:00 for pauses or one extra question

### Claim Boundary (Must Keep Verbatim)
- As of **April 23, 2026**, GPU proof execution confidence is **low**.
- GPU performance claims are **non-claimable** in this cycle.
- CPU baseline claims are claimable with explicit reliability caveats.

### Appendix Artifacts to Cite
- `artifacts/runs/phase4b-bounded-peft-20260423T034102Z/summary.json`
- `artifacts/runs/telemetry/icicle-backtrace-r1-20260423T033504Z.log`
- `artifacts/runs/telemetry/icicle-backtrace-r1-ezkl15_6_2-20260423T034457Z.log`
- `artifacts/runs/telemetry/icicle-backtrace-r1-ezkl15_5_0-20260423T034710Z.log`
- `artifacts/runs/telemetry/icicle-backtrace-r1-ezkl15_4_0-20260423T034922Z.log`
- `artifacts/runs/telemetry/icicle-backtrace-r1-ezkl15_1_0-20260423T035133Z.log`

### Q&A Guardrails
- If asked, "Did GPU proving work?"
- Response: "Not reliably demonstrable in this benchmark cycle."
- If asked, "Can we claim GPU speedup?"
- Response: "No. GPU proving remains non-claimable as of April 23, 2026."

### Deck QA Checklist
- All displayed metrics match `plans/final-benchmark.md`.
- Date language uses explicit date strings (April 23, 2026).
- No slide implies validated GPU proving throughput.
- Main narrative keeps GPU confidence at `low`.
