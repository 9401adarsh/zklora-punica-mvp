from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, List


def now_ts() -> float:
    return time.time()


def utc_label() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def percentile(values: Iterable[float], pct: float) -> float:
    data = sorted(float(v) for v in values)
    if not data:
        return 0.0
    if len(data) == 1:
        return data[0]
    idx = (len(data) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(data) - 1)
    frac = idx - lo
    return data[lo] * (1.0 - frac) + data[hi] * frac


def linear_slope(samples: List[tuple[float, float]]) -> float:
    if len(samples) < 2:
        return 0.0
    xs = [s[0] for s in samples]
    ys = [s[1] for s in samples]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0.0:
        return 0.0
    return num / den


def run_manifest_payload(extra: dict[str, Any]) -> dict[str, Any]:
    try:
        git_sha = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            .strip()
        )
    except Exception:
        git_sha = "unknown"

    payload = {
        "git_commit_sha": git_sha,
        "container_image_digest": "unknown",
        "cuda_driver_runtime": "unknown",
        "seed": 42,
        "hardware_descriptor": "unknown",
    }
    payload.update(extra)
    return payload
