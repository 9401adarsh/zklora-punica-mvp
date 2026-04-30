---
title: "zkLoRA × Punica MVP: A Proof-Aware Serving Pipeline with Bounded Benchmarking"
author:
  - "Adarsh"
date: "April 2026"
bibliography: references.bib
---

## Abstract

Proof-aware serving for LoRA-adapted language models is a systems problem: inference must remain responsive while proof generation is expensive and operationally fragile. This report presents a Phase 4b MVP that integrates asynchronous proof generation into a serving pipeline, adds a bounded benchmark harness, and evaluates two speedup levers: multi-threaded proving and setup-cache reuse. The implementation combines a receipt-first API, durable witness/proof artifacts, a threaded prover worker, and explicit backend intent routing (`cpu|gpu`). In benchmark runs dated April 23, 2026, CPU proving throughput improved from 0.010338 req/s (1 thread) to 0.017747 req/s (5 threads), but reliability declined at higher thread counts. GPU-intent runs were also evaluated; however, GPU speedup is non-claimable in this cycle because backend-routing trust remained low and prove-path confidence was not sufficient for a valid GPU claim. The report summarizes architecture, methods, measured outcomes, and limitations.

## Background

Low-Rank Adaptation (LoRA) enables parameter-efficient model adaptation by introducing trainable low-rank updates instead of full-model fine-tuning [@hu2021lora]. In multi-tenant or third-party adaptation workflows, two concerns emerge: (1) proving that an adapter behaves as claimed, and (2) doing so in a way that does not leak proprietary adapter information. zkLoRA addresses this verification setting through succinct proof generation for LoRA compatibility checks [@roy2025zklora].

From a serving perspective, the main challenge is not only proof correctness but operational integration. Systems such as Punica and vLLM emphasize that deployment quality is shaped by scheduling, memory behavior, and throughput-latency tradeoffs [@chen2023punica; @kwon2023pagedattention]. In this project, the same systems lens is applied to proof-aware serving: inference should return quickly, while proving executes asynchronously with explicit status tracking and reproducible benchmark artifacts.

The target in this phase is therefore practical and bounded: implement a proof-aware MVP, measure throughput/reliability under controlled CPU/GPU-intent settings, and keep claims conservative when backend trust is uncertain.

## Work Done

The work implemented in this cycle focuses on a serving-plus-proof architecture with benchmark-ready instrumentation.

1. **Asynchronous proof-aware API path.** `POST /infer` returns immediately with a receipt and proof status hint, while proof execution runs in the background. Sampled requests persist witness artifacts and enqueue proof jobs; clients poll proof state via request identifier.

2. **Durable artifact and status flow.** Witness metadata, proof jobs, and proof status records are persisted so runs are auditable and restart-friendly. Status transitions are explicit (`queued -> pending -> ready|failed`, plus non-sampled/overload outcomes) and support benchmark aggregation.

3. **Threaded prover worker.** A manifest-driven worker supports configurable thread pools to process independent proof jobs concurrently. This is the primary throughput lever tested in the CPU baseline.

4. **Backend intent routing and guardrails.** Prover backend intent is configurable (`cpu|gpu`) with routing-policy behavior (`strict|fallback`) and backend-trust metadata captured per run. This enables controlled CPU/GPU-intent comparisons without changing API shape.

5. **Bounded benchmark harness.** A dedicated harness (`bench/phase4b_bounded_peft.py`) executes matrix points under request-count + timeout bounds, records per-point summaries, and emits comparison-ready artifacts.

6. **Setup-cache reuse support.** Setup artifacts are cacheable across runs, enabling cold-vs-warm measurements and amortization analysis.

Figure 1 summarizes the architecture implemented for this phase.

## Experiments

### Setup and Scope

Experiments use a bounded Phase 4b harness with full PEFT proof path and persisted run artifacts. The scope is intentionally narrow: one target prefill module, strict proof semantics, and controlled matrix points for backend/thread analysis. The numerical results in this report are sourced from the benchmark record dated April 23, 2026.

### Workloads and Matrices

The following groups were used:

- **CPU baseline pack (throughput focus):** `threads = {1,2,5,10}`, `requests = 20`.
- **Matched CPU/GPU-intent bug-check pairs:** `(threads,requests) = (1,20)` and `(2,20)`.
- **GPU cold/warm cache check:** `(threads,requests) = (1,1)` on a shared setup-cache root.

### Measured Metrics

Primary metrics:

- throughput (`req_per_sec`),
- status counts (`ready`, `failed`, etc.),
- ready-rate as reliability signal,
- stage timings (`setup`, `witness`, `prove`) when available,
- backend trust indicators for GPU-intent runs.

For GPU-intent interpretation, this phase enforces conservative trust logic: backend intent alone is insufficient evidence of GPU proving. Additional signals (API routing support, telemetry, controls) are required before claiming GPU speedup.

## Results

### CPU Throughput and Reliability

CPU throughput increased with thread count up to 5 threads, then flattened, while reliability declined at higher concurrency.

| threads | requests | req_per_sec | ready | failed | ready_rate |
|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 0.010338 | 20 | 0 | 1.00 |
| 2 | 20 | 0.014695 | 16 | 4 | 0.80 |
| 5 | 20 | 0.017747 | 13 | 7 | 0.65 |
| 10 | 20 | 0.017619 | 13 | 7 | 0.65 |

The headline throughput point is **0.017747 req/s at 5 threads**, with a readiness caveat (**13 ready / 7 failed**). Observed failures at higher thread counts were dominated by export-stage errors in this run cycle.

### Matched CPU vs GPU-Intent Trust Table

| pair | backend | threads | requests | req_per_sec | ready | failed | trust |
|---|---|---:|---:|---:|---:|---:|---|
| t=1 matched | cpu | 1 | 20 | 0.010043 | 20 | 0 | n/a |
| t=1 matched | gpu intent | 1 | 20 | 0.009996 | 20 | 0 | low |
| t=2 matched | cpu | 2 | 20 | 0.022152 | 10 | 10 | n/a |
| t=2 matched | gpu intent | 2 | 20 | 0.020053 | 11 | 9 | low |

As of **April 23, 2026**, GPU proving speedup is **non-claimable** in this benchmark cycle due to low backend confidence. Upstream blocker tracking and repeated panic signatures further motivate this conservative boundary [@ezklIssue882].

### Cold vs Warm Setup Cache Signal

A cold-vs-warm GPU-intent cache-root reuse check showed a strong setup amortization effect (cold setup `191.640715s` vs warm setup `0.000000s`), with throughput rising from `0.003521` to `0.010442` req/s for the single-request probe. This indicates setup reuse is a meaningful optimization lever even when backend trust constraints remain unresolved.

## Limitations

1. **Reliability under higher thread counts.** Throughput gains did not preserve uniform readiness; failure rates increased at larger thread settings in this cycle.

2. **GPU trust boundary not crossed.** Backend intent could not be promoted to high-confidence effective GPU proving, so GPU performance claims remain non-claimable as of April 23, 2026.

3. **Blocker sensitivity in proving stack.** Icicle-related panic signatures were observed during version-sweep debugging, reinforcing the need for strict routing validation and fail-fast behavior before making GPU speedup claims [@ezklIssue882].

4. **Narrow benchmark scope.** Results are based on bounded synthetic-request harness settings and prefill-only proof scope; broader production traffic characteristics were out of scope for this phase.

Overall, this phase demonstrates an architecture that is measurable and reproducible, with clear CPU-side scaling signal and an explicit claim boundary on GPU proving. The next step is trust-hardening and reliability stabilization before extending optimization claims.
