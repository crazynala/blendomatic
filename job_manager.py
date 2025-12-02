"""Job schema and helpers for distributed rendering."""
from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in-progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

JOB_VERSION = 1


@dataclass
class JobRecord:
    job_id: str
    run_id: str
    sequence: int
    status: str = STATUS_PENDING
    worker: Optional[str] = None
    config: Dict[str, Any] = None  # garment/fabric/asset/view etc.
    created_at: str = ""
    updated_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    version: int = JOB_VERSION
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return dt.datetime.utcnow().isoformat() + "Z"


def create_job_record(run_id: str, sequence: int, config: Dict[str, Any], note: str = "") -> JobRecord:
    job_id = f"{run_id}-{sequence:04d}-{uuid.uuid4().hex[:8]}"
    now = _utc_now()
    return JobRecord(
        job_id=job_id,
        run_id=run_id,
        sequence=sequence,
        status=STATUS_PENDING,
        config=config,
        created_at=now,
        updated_at=now,
        notes=note or config.get("note"),
    )


def expand_configs_to_jobs(run_id: str, configs: Iterable[Dict[str, Any]]) -> List[JobRecord]:
    jobs: List[JobRecord] = []
    for seq, conf in enumerate(configs, start=1):
        jobs.append(create_job_record(run_id, seq, conf))
    return jobs


def job_to_json(job: JobRecord) -> str:
    return json.dumps(job.to_dict(), indent=2)


def update_job_status(job: JobRecord, status: str, *, worker: Optional[str] = None, result: Optional[Dict[str, Any]] = None) -> JobRecord:
    job.status = status
    job.updated_at = _utc_now()
    if status == STATUS_IN_PROGRESS:
        job.started_at = job.started_at or job.updated_at
        if worker:
            job.worker = worker
    elif status in (STATUS_COMPLETED, STATUS_FAILED):
        job.finished_at = job.updated_at
        if result is not None:
            job.result = result
        if worker:
            job.worker = worker
    return job


def save_job_records(jobs: Iterable[JobRecord], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = [job.to_dict() for job in jobs]
    destination.write_text(json.dumps(serialized, indent=2))