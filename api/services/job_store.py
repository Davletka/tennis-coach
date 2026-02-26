"""
Redis-backed job state store.

Each job is stored as a JSON blob under key ``job:{job_id}``.

Schema
------
{
    "job_id":          str,
    "status":          "pending" | "running" | "completed" | "failed",
    "progress":        int (0-100),
    "message":         str,
    "created_at":      ISO-8601 datetime str,
    "updated_at":      ISO-8601 datetime str,
    # Set only when completed:
    "input_s3_key":    str,
    "annotated_s3_key": str,
    "fps":             float,
    "total_source_frames": int,
    "metrics":         dict,
    "coaching_report": dict,
    # Set only when failed:
    "error":           str,
}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis

from api.settings import settings


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _key(job_id: str) -> str:
    return f"job:{job_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_job(job_id: str) -> Dict[str, Any]:
    """Insert a new job record with status=pending. Returns the record."""
    now = _now_iso()
    record: Dict[str, Any] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Queued",
        "created_at": now,
        "updated_at": now,
    }
    r = _redis()
    r.set(_key(job_id), json.dumps(record), ex=settings.job_ttl)
    return record


def update_job(job_id: str, **fields: Any) -> None:
    """
    Merge *fields* into the existing job record and refresh TTL.

    Common fields: status, progress, message, input_s3_key,
                   annotated_s3_key, fps, total_source_frames,
                   metrics, coaching_report, error.
    """
    r = _redis()
    raw = r.get(_key(job_id))
    if raw is None:
        return
    record: Dict[str, Any] = json.loads(raw)
    record.update(fields)
    record["updated_at"] = _now_iso()
    r.set(_key(job_id), json.dumps(record), ex=settings.job_ttl)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Return the job record, or None if not found."""
    r = _redis()
    raw = r.get(_key(job_id))
    if raw is None:
        return None
    return json.loads(raw)
