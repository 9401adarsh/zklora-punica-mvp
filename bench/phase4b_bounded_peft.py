from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from bench.phase3_common import ensure_dir, utc_label, write_json
from mvp_server.api.server import MVPServer
from mvp_server.config import AppConfig
from mvp_server.proof.proof_store import ProofRecord
from mvp_server.proof.prover_worker import ProverWorker
from mvp_server.proof.zklora_adapter import ZkLoraAdapter
from mvp_server.runtime.model_runtime import InferenceResult


@dataclass(frozen=True)
class BenchmarkCase:
    backend: str
    threads: int
    requests: int

    def tag(self) -> str:
        return f"backend-{self.backend}-threads-{self.threads}-requests-{self.requests}"


class SyntheticRuntime3D:
    loaded = True

    def __init__(self, hidden_dim: int = 768, seq_len: int = 1, seed: Optional[int] = None) -> None:
        self.hidden_dim = hidden_dim
        self.seq_len = seq_len
        self.seed = seed
        self._lock = threading.Lock()
        self._counter = 0

    def infer_prefill(
        self, prompt: str, generation_params: Optional[dict[str, Any]] = None
    ) -> InferenceResult:
        _ = (prompt, generation_params)
        with self._lock:
            idx = self._counter
            self._counter += 1
        value = float((idx % 17) + 1)
        x_pre = np.full((1, self.seq_len, self.hidden_dim), value, dtype=np.float32)
        delta_post = np.full((1, self.seq_len, self.hidden_dim), value * 0.1, dtype=np.float32)
        return InferenceResult(
            output=prompt,
            module_id="transformer.h.0.attn.c_attn",
            h_x="hx",
            h_delta="hd",
            hash_schema_version=1,
            x_pre=x_pre,
            delta_post=delta_post,
        )


def parse_csv_strings(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def parse_csv_ints(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def expand_cases(
    backends: list[str], threads: list[int], requests: list[int]
) -> list[BenchmarkCase]:
    cases: list[BenchmarkCase] = []
    for backend in backends:
        for thread_count in threads:
            for request_count in requests:
                cases.append(
                    BenchmarkCase(
                        backend=backend,
                        threads=thread_count,
                        requests=request_count,
                    )
                )
    return cases


def _count_statuses(records: dict[str, ProofRecord], request_ids: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for request_id in request_ids:
        record = records.get(request_id)
        if record is None:
            counts["missing"] = counts.get("missing", 0) + 1
            continue
        counts[record.status] = counts.get(record.status, 0) + 1
    return counts


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"count": 0, "avg": None, "min": None, "max": None}
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_from_ref(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _summarize_setup_cache(entries: list[bool]) -> dict[str, Any]:
    hits = sum(1 for flag in entries if flag)
    misses = sum(1 for flag in entries if not flag)
    total = hits + misses
    return {
        "enabled": total > 0,
        "hits": hits,
        "misses": misses,
        "hit_rate": None if total == 0 else round(hits / total, 6),
    }


def _normalize_backend_token(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"cpu", "gpu"}:
        return text
    return None


def _summarize_backend_trust(
    intents: list[str],
    effectives: list[str],
    routing_supported_flags: list[bool],
    fallback_flags: list[bool],
    reasons: list[str],
    default_intent: str,
) -> dict[str, Any]:
    backend_intent = intents[-1] if intents else default_intent
    if effectives:
        backend_effective = effectives[-1]
    elif backend_intent == "cpu":
        backend_effective = "cpu"
    else:
        backend_effective = "unknown"

    backend_routing_supported = (
        None if not routing_supported_flags else all(routing_supported_flags)
    )
    backend_fallback_used = None if not fallback_flags else any(fallback_flags)
    fallback_rate = (
        None
        if not fallback_flags
        else round(sum(1 for flag in fallback_flags if flag) / len(fallback_flags), 6)
    )
    reasons_unique = sorted(set(reasons))
    routing_reason = "; ".join(reasons_unique[:3]) if reasons_unique else None

    if backend_intent != "gpu":
        confidence = "n/a"
    elif backend_routing_supported is True and backend_fallback_used is False and backend_effective == "gpu":
        confidence = "high"
    else:
        confidence = "low"

    return {
        "backend_intent": backend_intent,
        "backend_effective": backend_effective,
        "backend_routing_supported": backend_routing_supported,
        "backend_fallback_used": backend_fallback_used,
        "backend_fallback_rate": fallback_rate,
        "backend_routing_reason": routing_reason,
        "confidence": confidence,
    }


def _empty_backend_trust(default_intent: str) -> dict[str, Any]:
    return _summarize_backend_trust(
        intents=[],
        effectives=[],
        routing_supported_flags=[],
        fallback_flags=[],
        reasons=[],
        default_intent=default_intent,
    )


def _extract_case_metrics(
    records: dict[str, ProofRecord],
    request_ids: list[str],
    default_backend: str,
) -> dict[str, Any]:
    prover_duration_ms: list[float] = []
    stage_setup_s: list[float] = []
    stage_witness_s: list[float] = []
    stage_prove_s: list[float] = []
    stage_total_s: list[float] = []
    setup_cache_entries: list[bool] = []
    error_messages: list[str] = []
    backend_intents: list[str] = []
    backend_effectives: list[str] = []
    backend_routing_supported_flags: list[bool] = []
    backend_fallback_flags: list[bool] = []
    backend_routing_reasons: list[str] = []

    for request_id in request_ids:
        record = records.get(request_id)
        if record is None:
            continue
        refs = record.artifact_refs
        if "prover_duration_ms" in refs:
            prover_duration_ms.append(float(refs["prover_duration_ms"]))
        if "stage_setup_s" in refs:
            stage_setup_s.append(float(refs["stage_setup_s"]))
        if "stage_witness_s" in refs:
            stage_witness_s.append(float(refs["stage_witness_s"]))
        if "stage_prove_s" in refs:
            stage_prove_s.append(float(refs["stage_prove_s"]))
        if "stage_total_s" in refs:
            stage_total_s.append(float(refs["stage_total_s"]))
        cache_enabled = _bool_from_ref(refs.get("setup_cache_enabled"))
        cache_hit = _bool_from_ref(refs.get("setup_cache_hit"))
        if cache_enabled and cache_hit is not None:
            setup_cache_entries.append(cache_hit)
        backend_intent = _normalize_backend_token(refs.get("backend_intent"))
        if backend_intent is not None:
            backend_intents.append(backend_intent)
        backend_effective = _normalize_backend_token(refs.get("backend_effective"))
        if backend_effective is not None:
            backend_effectives.append(backend_effective)
        backend_routing_supported = _bool_from_ref(refs.get("backend_routing_supported"))
        if backend_routing_supported is not None:
            backend_routing_supported_flags.append(backend_routing_supported)
        backend_fallback_used = _bool_from_ref(refs.get("backend_fallback_used"))
        if backend_fallback_used is not None:
            backend_fallback_flags.append(backend_fallback_used)
        backend_routing_reason = refs.get("backend_routing_reason")
        if isinstance(backend_routing_reason, str) and backend_routing_reason:
            backend_routing_reasons.append(backend_routing_reason)
        if record.error_message:
            error_messages.append(record.error_message)

    unique_errors = sorted(set(error_messages))
    return {
        "prover_duration_ms": _stats(prover_duration_ms),
        "stage_timing_s": {
            "setup": _stats(stage_setup_s),
            "witness": _stats(stage_witness_s),
            "prove": _stats(stage_prove_s),
            "total": _stats(stage_total_s),
        },
        "error_samples": unique_errors[:5],
        "setup_cache": _summarize_setup_cache(setup_cache_entries),
        "backend_trust": _summarize_backend_trust(
            intents=backend_intents,
            effectives=backend_effectives,
            routing_supported_flags=backend_routing_supported_flags,
            fallback_flags=backend_fallback_flags,
            reasons=backend_routing_reasons,
            default_intent=default_backend,
        ),
    }


def _extract_case_metrics_from_raw_records(
    records: dict[str, Any], default_backend: str
) -> dict[str, Any]:
    prover_duration_ms: list[float] = []
    stage_setup_s: list[float] = []
    stage_witness_s: list[float] = []
    stage_prove_s: list[float] = []
    stage_total_s: list[float] = []
    setup_cache_entries: list[bool] = []
    error_messages: list[str] = []
    backend_intents: list[str] = []
    backend_effectives: list[str] = []
    backend_routing_supported_flags: list[bool] = []
    backend_fallback_flags: list[bool] = []
    backend_routing_reasons: list[str] = []

    for record in records.values():
        if not isinstance(record, dict):
            continue

        refs = record.get("artifact_refs")
        if isinstance(refs, dict):
            duration_ms = _float_or_none(refs.get("prover_duration_ms"))
            if duration_ms is not None:
                prover_duration_ms.append(duration_ms)

            setup_s = _float_or_none(refs.get("stage_setup_s"))
            if setup_s is not None:
                stage_setup_s.append(setup_s)

            witness_s = _float_or_none(refs.get("stage_witness_s"))
            if witness_s is not None:
                stage_witness_s.append(witness_s)

            prove_s = _float_or_none(refs.get("stage_prove_s"))
            if prove_s is not None:
                stage_prove_s.append(prove_s)

            total_s = _float_or_none(refs.get("stage_total_s"))
            if total_s is not None:
                stage_total_s.append(total_s)

            cache_enabled = _bool_from_ref(refs.get("setup_cache_enabled"))
            cache_hit = _bool_from_ref(refs.get("setup_cache_hit"))
            if cache_enabled and cache_hit is not None:
                setup_cache_entries.append(cache_hit)

            backend_intent = _normalize_backend_token(refs.get("backend_intent"))
            if backend_intent is not None:
                backend_intents.append(backend_intent)
            backend_effective = _normalize_backend_token(refs.get("backend_effective"))
            if backend_effective is not None:
                backend_effectives.append(backend_effective)
            backend_routing_supported = _bool_from_ref(refs.get("backend_routing_supported"))
            if backend_routing_supported is not None:
                backend_routing_supported_flags.append(backend_routing_supported)
            backend_fallback_used = _bool_from_ref(refs.get("backend_fallback_used"))
            if backend_fallback_used is not None:
                backend_fallback_flags.append(backend_fallback_used)
            backend_routing_reason = refs.get("backend_routing_reason")
            if isinstance(backend_routing_reason, str) and backend_routing_reason:
                backend_routing_reasons.append(backend_routing_reason)

        error_message = record.get("error_message")
        if isinstance(error_message, str) and error_message:
            error_messages.append(error_message)

    unique_errors = sorted(set(error_messages))
    return {
        "prover_duration_ms": _stats(prover_duration_ms),
        "stage_timing_s": {
            "setup": _stats(stage_setup_s),
            "witness": _stats(stage_witness_s),
            "prove": _stats(stage_prove_s),
            "total": _stats(stage_total_s),
        },
        "error_samples": unique_errors[:5],
        "setup_cache": _summarize_setup_cache(setup_cache_entries),
        "backend_trust": _summarize_backend_trust(
            intents=backend_intents,
            effectives=backend_effectives,
            routing_supported_flags=backend_routing_supported_flags,
            fallback_flags=backend_fallback_flags,
            reasons=backend_routing_reasons,
            default_intent=default_backend,
        ),
    }


def _classify_completed_case(requests: int, status_counts: dict[str, int]) -> str:
    ready = status_counts.get("ready", 0)
    failed = status_counts.get("failed", 0)
    if ready == requests:
        return "completed"
    if failed == requests and requests > 0:
        return "failed_fast"
    return "completed"


def _enqueue_requests(
    server: MVPServer,
    prompt: str,
    total_requests: int,
    request_concurrency: int,
) -> tuple[list[str], list[str]]:
    request_ids: list[str] = []
    enqueue_errors: list[str] = []
    index_lock = threading.Lock()
    request_index = {"value": 0}

    def producer() -> None:
        while True:
            with index_lock:
                idx = request_index["value"]
                if idx >= total_requests:
                    return
                request_index["value"] += 1
            payload = {"prompt": f"{prompt} [{idx}]"}
            try:
                response = server.post_infer(payload)
                with index_lock:
                    request_ids.append(response["receipt"]["request_id"])
            except Exception as exc:  # pragma: no cover - best-effort error capture
                with index_lock:
                    enqueue_errors.append(str(exc))

    workers = max(1, request_concurrency)
    threads = [threading.Thread(target=producer, daemon=True) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return request_ids, enqueue_errors


def run_case_direct(
    case: BenchmarkCase,
    case_dir: Path,
    prompt: str,
    request_concurrency: int,
    seed: Optional[int] = None,
    hidden_dim: int = 768,
    seq_len: int = 1,
    base_model_id: Optional[str] = None,
    adapter_id: Optional[str] = None,
    setup_cache_root: Optional[str] = None,
    gpu_routing_policy: str = "strict",
) -> dict[str, Any]:
    runtime_artifacts = ensure_dir(case_dir / "runtime_artifacts")
    config_data: dict[str, Any] = {
        "artifacts_root": str(runtime_artifacts),
        "proof_mode": "every_request",
        "prover_backend": case.backend,
        "gpu_routing_policy": gpu_routing_policy,
        "proof_worker_threads": case.threads,
    }
    if base_model_id is not None:
        config_data["base_model_id"] = base_model_id
    if adapter_id is not None:
        config_data["adapter_id"] = adapter_id
    config = AppConfig.from_dict(config_data)
    server = MVPServer(
        config=config,
        runtime=SyntheticRuntime3D(hidden_dim=hidden_dim, seq_len=seq_len, seed=seed),
    )
    worker = ProverWorker(
        manifest=server.proof_manifest,
        proof_store=server.proof_store,
        adapter_factory=lambda: ZkLoraAdapter(
            artifacts_root=config.artifacts_root,
            base_model_id=config.base_model_id,
            adapter_id=config.adapter_id,
            prover_backend=config.prover_backend,
            gpu_routing_policy=config.gpu_routing_policy,
            setup_cache_root=setup_cache_root,
        ),
        proof_worker_threads=config.proof_worker_threads,
    )

    request_ids, enqueue_errors = _enqueue_requests(
        server=server,
        prompt=prompt,
        total_requests=case.requests,
        request_concurrency=request_concurrency,
    )
    enqueued_requests = len(request_ids)

    worker_started_at = time.time()
    processed = worker.run(
        max_jobs=enqueued_requests,
        poll_interval_s=config.worker_poll_interval_ms / 1000.0,
    )
    worker_wall_s = time.time() - worker_started_at

    records = server.proof_store.all_records()
    status_counts = _count_statuses(records, request_ids)
    metrics = _extract_case_metrics(records, request_ids, default_backend=case.backend)
    status = _classify_completed_case(enqueued_requests, status_counts)
    throughput = (
        (enqueued_requests / worker_wall_s) if worker_wall_s > 0 and enqueued_requests > 0 else 0.0
    )

    result = {
        "backend": case.backend,
        "threads": case.threads,
        "requests": case.requests,
        "enqueued_requests": enqueued_requests,
        "processed_jobs": processed,
        "status": status,
        "status_counts": status_counts,
        "worker_wall_s": round(worker_wall_s, 6),
        "req_per_sec": round(throughput, 6),
        "prover_duration_ms": metrics["prover_duration_ms"],
        "stage_timing_s": metrics["stage_timing_s"],
        "error_samples": metrics["error_samples"],
        "setup_cache": metrics["setup_cache"],
        "backend_trust": metrics["backend_trust"],
        "enqueue_errors": enqueue_errors[:5],
        "case_dir": str(case_dir),
    }
    write_json(case_dir / "summary.json", result)
    return result


def _run_case_subprocess_target(
    case_payload: dict[str, Any],
    case_dir: str,
    prompt: str,
    request_concurrency: int,
    seed: Optional[int],
    hidden_dim: int,
    seq_len: int,
    base_model_id: Optional[str],
    adapter_id: Optional[str],
    setup_cache_root: Optional[str],
    gpu_routing_policy: str,
    out_queue: mp.Queue,
) -> None:
    case = BenchmarkCase(**case_payload)
    try:
        result = run_case_direct(
            case=case,
            case_dir=Path(case_dir),
            prompt=prompt,
            request_concurrency=request_concurrency,
            seed=seed,
            hidden_dim=hidden_dim,
            seq_len=seq_len,
            base_model_id=base_model_id,
            adapter_id=adapter_id,
            setup_cache_root=setup_cache_root,
            gpu_routing_policy=gpu_routing_policy,
        )
        out_queue.put({"ok": True, "result": result})
    except Exception as exc:  # pragma: no cover - defensive benchmark error capture
        out_queue.put({"ok": False, "error": str(exc)})


def _load_partial_status(
    case_dir: Path, default_backend: str
) -> tuple[dict[str, int], dict[str, Any]]:
    store_path = case_dir / "runtime_artifacts" / "proof" / "proof_store.json"
    empty_metrics = {
        "prover_duration_ms": {"count": 0, "avg": None, "min": None, "max": None},
        "stage_timing_s": {
            "setup": {"count": 0, "avg": None, "min": None, "max": None},
            "witness": {"count": 0, "avg": None, "min": None, "max": None},
            "prove": {"count": 0, "avg": None, "min": None, "max": None},
            "total": {"count": 0, "avg": None, "min": None, "max": None},
        },
        "error_samples": [],
        "setup_cache": {"enabled": False, "hits": 0, "misses": 0, "hit_rate": None},
        "backend_trust": _empty_backend_trust(default_intent=default_backend),
    }

    if not store_path.exists():
        return {}, empty_metrics

    with store_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    records = payload.get("records", {})
    if not isinstance(records, dict):
        return {}, empty_metrics

    status_counts: dict[str, int] = {}
    for rec in records.values():
        if not isinstance(rec, dict):
            continue
        status = str(rec.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1

    metrics = _extract_case_metrics_from_raw_records(
        records, default_backend=default_backend
    )
    return status_counts, metrics


def run_case_bounded(
    case: BenchmarkCase,
    run_dir: Path,
    timeout_sec: int,
    prompt: str,
    request_concurrency: int,
    seed: Optional[int],
    hidden_dim: int,
    seq_len: int,
    base_model_id: Optional[str] = None,
    adapter_id: Optional[str] = None,
    setup_cache_root: Optional[str] = None,
    gpu_routing_policy: str = "strict",
) -> dict[str, Any]:
    case_dir = ensure_dir(run_dir / case.tag())
    queue: mp.Queue = mp.Queue(maxsize=1)
    started_at = time.time()
    proc = mp.Process(
        target=_run_case_subprocess_target,
        args=(
            asdict(case),
            str(case_dir),
            prompt,
            request_concurrency,
            seed,
            hidden_dim,
            seq_len,
            base_model_id,
            adapter_id,
            setup_cache_root,
            gpu_routing_policy,
            queue,
        ),
        daemon=True,
    )
    proc.start()
    proc.join(timeout=timeout_sec)
    elapsed = time.time() - started_at

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=3.0)
        status_counts, metrics = _load_partial_status(
            case_dir, default_backend=case.backend
        )
        processed_jobs = status_counts.get("ready", 0) + status_counts.get("failed", 0)
        throughput = (processed_jobs / elapsed) if elapsed > 0 and processed_jobs > 0 else 0.0
        result = {
            "backend": case.backend,
            "threads": case.threads,
            "requests": case.requests,
            "enqueued_requests": status_counts.get("ready", 0)
            + status_counts.get("failed", 0)
            + status_counts.get("pending", 0)
            + status_counts.get("queued", 0),
            "processed_jobs": processed_jobs,
            "status": "timed_out",
            "status_counts": status_counts,
            "worker_wall_s": round(elapsed, 6),
            "req_per_sec": round(throughput, 6),
            "prover_duration_ms": metrics["prover_duration_ms"],
            "stage_timing_s": metrics["stage_timing_s"],
            "error_samples": metrics["error_samples"],
            "setup_cache": metrics["setup_cache"],
            "backend_trust": metrics["backend_trust"],
            "enqueue_errors": [],
            "case_dir": str(case_dir),
        }
        write_json(case_dir / "summary.json", result)
        return result

    outcome = queue.get() if not queue.empty() else {"ok": False, "error": "missing result"}
    if not outcome.get("ok"):
        result = {
            "backend": case.backend,
            "threads": case.threads,
            "requests": case.requests,
            "enqueued_requests": 0,
            "processed_jobs": 0,
            "status": "failed_fast",
            "status_counts": {"failed": case.requests},
            "worker_wall_s": round(elapsed, 6),
            "req_per_sec": 0.0,
            "prover_duration_ms": {"count": 0, "avg": None, "min": None, "max": None},
            "stage_timing_s": {
                "setup": {"count": 0, "avg": None, "min": None, "max": None},
                "witness": {"count": 0, "avg": None, "min": None, "max": None},
                "prove": {"count": 0, "avg": None, "min": None, "max": None},
                "total": {"count": 0, "avg": None, "min": None, "max": None},
            },
            "error_samples": [str(outcome.get("error", "unknown benchmark error"))],
            "setup_cache": {"enabled": False, "hits": 0, "misses": 0, "hit_rate": None},
            "backend_trust": _empty_backend_trust(default_intent=case.backend),
            "enqueue_errors": [],
            "case_dir": str(case_dir),
        }
        write_json(case_dir / "summary.json", result)
        return result

    return outcome["result"]


def _format_stage_avg(stats: dict[str, Any], key: str) -> str:
    stage_stats = stats.get(key, {})
    avg = stage_stats.get("avg")
    return "-" if avg is None else f"{avg:.6f}"


def render_summary_markdown(payload: dict[str, Any]) -> str:
    points = payload["points"]
    lines = [
        "# Phase 4b Bounded Full-PEFT Benchmark Summary",
        "",
        f"- run_dir: `{payload['run_dir']}`",
        f"- timeout_sec: `{payload['timeout_sec']}`",
        f"- request_concurrency: `{payload['request_concurrency']}`",
        f"- setup_cache_root: `{payload.get('setup_cache_root') or '-'}`",
        f"- gpu_routing_policy: `{payload.get('gpu_routing_policy') or '-'}`",
        "",
        "## All Points",
        "",
        "| backend | threads | requests | status | ready | failed | wall_s | req_per_sec | setup_s(avg) | witness_s(avg) | prove_s(avg) | total_s(avg) | cache_hits | cache_misses | cache_hit_rate | backend_effective | routing_supported | fallback_rate | trust |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|",
    ]
    for point in points:
        counts = point["status_counts"]
        ready = counts.get("ready", 0)
        failed = counts.get("failed", 0)
        timings = point["stage_timing_s"]
        setup_cache = point.get("setup_cache", {})
        cache_hits = int(setup_cache.get("hits", 0))
        cache_misses = int(setup_cache.get("misses", 0))
        hit_rate = setup_cache.get("hit_rate")
        cache_hit_rate = "-" if hit_rate is None else f"{float(hit_rate):.6f}"
        backend_trust = point.get("backend_trust", {})
        backend_effective = str(backend_trust.get("backend_effective", "-"))
        routing_supported_val = backend_trust.get("backend_routing_supported")
        routing_supported = "-" if routing_supported_val is None else str(bool(routing_supported_val)).lower()
        fallback_rate_val = backend_trust.get("backend_fallback_rate")
        fallback_rate = "-" if fallback_rate_val is None else f"{float(fallback_rate_val):.6f}"
        confidence = str(backend_trust.get("confidence", "-"))
        lines.append(
            "| {backend} | {threads} | {requests} | {status} | {ready} | {failed} | {wall:.6f} | {rps:.6f} | {setup} | {witness} | {prove} | {total} | {cache_hits} | {cache_misses} | {cache_hit_rate} | {backend_effective} | {routing_supported} | {fallback_rate} | {confidence} |".format(
                backend=point["backend"],
                threads=point["threads"],
                requests=point["requests"],
                status=point["status"],
                ready=ready,
                failed=failed,
                wall=point["worker_wall_s"],
                rps=point["req_per_sec"],
                setup=_format_stage_avg(timings, "setup"),
                witness=_format_stage_avg(timings, "witness"),
                prove=_format_stage_avg(timings, "prove"),
                total=_format_stage_avg(timings, "total"),
                cache_hits=cache_hits,
                cache_misses=cache_misses,
                cache_hit_rate=cache_hit_rate,
                backend_effective=backend_effective,
                routing_supported=routing_supported,
                fallback_rate=fallback_rate,
                confidence=confidence,
            )
        )

    lines.extend(
        [
            "",
            "## Thread Scaling (Fixed Backend + Requests)",
            "",
            "| backend | requests | thread_a | rps_a | thread_b | rps_b | speedup_b_over_a |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for point in points:
        key = (point["backend"], point["requests"])
        grouped.setdefault(key, []).append(point)
    for (backend, requests), rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda r: r["threads"])
        if len(rows) < 2:
            continue
        first = rows[0]
        for row in rows[1:]:
            denom = first["req_per_sec"]
            speedup = (row["req_per_sec"] / denom) if denom > 0 else 0.0
            lines.append(
                "| {backend} | {requests} | {ta} | {ra:.6f} | {tb} | {rb:.6f} | {sp:.6f} |".format(
                    backend=backend,
                    requests=requests,
                    ta=first["threads"],
                    ra=first["req_per_sec"],
                    tb=row["threads"],
                    rb=row["req_per_sec"],
                    sp=speedup,
                )
            )

    lines.extend(
        [
            "",
            "## Backend Delta (Fixed Threads + Requests)",
            "",
            "| threads | requests | cpu_rps | gpu_rps | gpu_over_cpu |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    by_thread_req: dict[tuple[int, int], dict[str, dict[str, Any]]] = {}
    for point in points:
        key = (point["threads"], point["requests"])
        by_thread_req.setdefault(key, {})[point["backend"]] = point
    for (threads, requests), backend_map in sorted(by_thread_req.items()):
        cpu = backend_map.get("cpu")
        gpu = backend_map.get("gpu")
        if not cpu or not gpu:
            continue
        cpu_rps = cpu["req_per_sec"]
        gpu_rps = gpu["req_per_sec"]
        ratio = (gpu_rps / cpu_rps) if cpu_rps > 0 else 0.0
        lines.append(
            f"| {threads} | {requests} | {cpu_rps:.6f} | {gpu_rps:.6f} | {ratio:.6f} |"
        )
    return "\n".join(lines) + "\n"


def run_matrix(
    output_root: Path,
    backends: list[str],
    threads: list[int],
    requests: list[int],
    timeout_sec: int,
    request_concurrency: int,
    prompt: str,
    seed: Optional[int],
    hidden_dim: int,
    seq_len: int,
    base_model_id: Optional[str] = None,
    adapter_id: Optional[str] = None,
    setup_cache_root: Optional[str] = None,
    gpu_routing_policy: str = "strict",
) -> Path:
    run_dir = ensure_dir(output_root / f"phase4b-bounded-peft-{utc_label()}")
    cases = expand_cases(backends=backends, threads=threads, requests=requests)
    points: list[dict[str, Any]] = []
    for case in cases:
        points.append(
            run_case_bounded(
                case=case,
                run_dir=run_dir,
                timeout_sec=timeout_sec,
                prompt=prompt,
                request_concurrency=request_concurrency,
                seed=seed,
                hidden_dim=hidden_dim,
                seq_len=seq_len,
                base_model_id=base_model_id,
                adapter_id=adapter_id,
                setup_cache_root=setup_cache_root,
                gpu_routing_policy=gpu_routing_policy,
            )
        )

    payload = {
        "run_dir": str(run_dir),
        "timeout_sec": timeout_sec,
        "request_concurrency": request_concurrency,
        "seed": seed,
        "hidden_dim": hidden_dim,
        "seq_len": seq_len,
        "setup_cache_root": setup_cache_root,
        "gpu_routing_policy": gpu_routing_policy,
        "points": points,
    }
    write_json(run_dir / "summary.json", payload)
    (run_dir / "summary.md").write_text(render_summary_markdown(payload), encoding="utf-8")
    return run_dir


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase-4b bounded benchmark harness (full PEFT + real proof path)"
    )
    parser.add_argument("--backends", default="cpu,gpu")
    parser.add_argument("--threads", default="1,2")
    parser.add_argument("--requests", default="5,20")
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument("--request-concurrency", type=int, default=1)
    parser.add_argument("--output-root", default="artifacts/runs")
    parser.add_argument("--prompt", default="Explain zk proofs in one paragraph.")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--hidden-dim", type=int, default=768)
    parser.add_argument("--seq-len", type=int, default=1)
    parser.add_argument("--base-model-id", default=AppConfig.base_model_id)
    parser.add_argument("--adapter-id", default=AppConfig.adapter_id)
    parser.add_argument(
        "--setup-cache-root",
        default=None,
        help="Optional persistent setup cache root. When set, setup artifacts are reused across runs.",
    )
    parser.add_argument(
        "--gpu-routing-policy",
        default="strict",
        choices=["fallback", "strict"],
        help="Routing behavior when gpu backend intent cannot be proven routable.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    run_dir = run_matrix(
        output_root=Path(args.output_root),
        backends=parse_csv_strings(args.backends),
        threads=parse_csv_ints(args.threads),
        requests=parse_csv_ints(args.requests),
        timeout_sec=args.timeout_sec,
        request_concurrency=max(1, args.request_concurrency),
        prompt=args.prompt,
        seed=args.seed,
        hidden_dim=args.hidden_dim,
        seq_len=args.seq_len,
        base_model_id=args.base_model_id,
        adapter_id=args.adapter_id,
        setup_cache_root=args.setup_cache_root,
        gpu_routing_policy=args.gpu_routing_policy,
    )
    print(str(run_dir))


if __name__ == "__main__":
    main()
