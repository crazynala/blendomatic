"""Worker registration and heartbeat utilities (local or S3-backed)."""
from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    import boto3  # type: ignore
except ImportError:  # pragma: no cover - boto3 optional until needed
    boto3 = None

WORKER_STORE_ENV = "BLENDOMATIC_WORKER_STORE"
WORKER_ID_ENV = "BLENDOMATIC_WORKER_ID"
WORKER_MODE_ENV = "BLENDOMATIC_NODE_MODE"
S3_STORE_FALLBACK_ENV = "BLENDOMATIC_S3_STORE"


@dataclass
class WorkerStore:
    kind: str  # "local" or "s3"
    local_path: Optional[Path] = None
    bucket: Optional[str] = None
    prefix: str = ""
    s3_client: Any = None


@dataclass
class WorkerRecord:
    worker_id: str
    hostname: str
    status: str
    last_seen: str
    active_job_id: Optional[str]
    mode: Optional[str]
    payload: Dict[str, Any]


_store: Optional[WorkerStore] = None
_log_sink: Optional[Callable[[str], None]] = None


def _log(msg: str) -> None:
    text = f"[WORKER_REGISTRY] {msg}"
    print(text, flush=True)
    if _log_sink is not None:
        try:
            _log_sink(text)
        except Exception:
            pass


def set_log_sink(callback: Optional[Callable[[str], None]]) -> None:
    """Allow callers (like the TUI) to receive registry log messages."""
    global _log_sink
    _log_sink = callback


def _build_store() -> WorkerStore:
    primary = os.environ.get(WORKER_STORE_ENV)
    fallback = os.environ.get(S3_STORE_FALLBACK_ENV)
    value = primary or fallback
    _log(
        f"Initializing worker store. Env {WORKER_STORE_ENV}={primary} | {S3_STORE_FALLBACK_ENV}={fallback}"
    )
    if not primary and fallback:
        _log(f"Using {S3_STORE_FALLBACK_ENV} for worker store configuration")

    if not value:
        raise RuntimeError(
            "BLENDOMATIC_WORKER_STORE (or BLENDOMATIC_S3_STORE) must be set to an s3:// bucket/prefix"
        )

    if not value.startswith("s3://"):
        raise RuntimeError(
            f"Unsupported worker store value '{value}'. Only s3:// URIs are allowed."
        )

    if boto3 is None:
        raise RuntimeError("boto3 is required for S3 worker store but is not installed")

    without_scheme = value[5:]
    parts = without_scheme.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    prefix = prefix.rstrip("/")
    client = boto3.client("s3")
    _log(f"Using S3 worker store bucket={bucket} prefix='{prefix}'")
    return WorkerStore(kind="s3", bucket=bucket, prefix=prefix, s3_client=client)


def _get_store() -> WorkerStore:
    global _store
    if _store is None:
        _store = _build_store()
        _log(f"Worker store ready (kind={_store.kind})")
    return _store


def get_worker_id() -> str:
    if os.environ.get(WORKER_ID_ENV):
        return os.environ[WORKER_ID_ENV]
    host = platform.node() or socket.gethostname()
    return host or "unknown-worker"


def get_worker_mode(default: str = "master") -> str:
    return os.environ.get(WORKER_MODE_ENV, default)


def _iso_now() -> str:
    return _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _build_payload(
    *,
    worker_id: str,
    status: str,
    active_job_id: Optional[str] = None,
    run_id: Optional[str] = None,
    info: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "worker_id": worker_id,
        "hostname": platform.node(),
        "status": status,
        "active_job_id": active_job_id,
        "run_id": run_id,
        "last_seen": _iso_now(),
        "pid": os.getpid(),
        "info": info or {},
        "mode": mode,
        "version": 1,
    }
    return payload


def _local_worker_path(store: WorkerStore, worker_id: str) -> Path:
    assert store.local_path is not None
    return store.local_path / f"{worker_id}.json"


def record_heartbeat(
    worker_id: str,
    *,
    status: str,
    active_job_id: Optional[str] = None,
    run_id: Optional[str] = None,
    info: Optional[Dict[str, Any]] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Record/update worker heartbeat."""
    store = _get_store()
    payload = _build_payload(
        worker_id=worker_id,
        status=status,
        active_job_id=active_job_id,
        run_id=run_id,
        info=info,
        mode=mode,
    )

    try:
        if store.kind == "s3":
            assert store.bucket and store.s3_client
            prefix = f"{store.prefix}/workers" if store.prefix else "workers"
            key = f"{prefix.rstrip('/')}/{worker_id}.json"
            body = json.dumps(payload).encode("utf-8")
            store.s3_client.put_object(
                Bucket=store.bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        else:
            path = _local_worker_path(store, worker_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2))
    except Exception as exc:  # pragma: no cover - best effort logging
        _log(f"Failed to record heartbeat: {exc}")

    return payload


def _load_local_worker_records(store: WorkerStore) -> List[WorkerRecord]:
    records: List[WorkerRecord] = []
    assert store.local_path is not None
    for file in store.local_path.glob("*.json"):
        try:
            data = json.loads(file.read_text())
            records.append(
                WorkerRecord(
                    worker_id=data.get("worker_id", file.stem),
                    hostname=data.get("hostname", "unknown"),
                    status=data.get("status", "unknown"),
                    last_seen=data.get("last_seen", ""),
                    active_job_id=data.get("active_job_id"),
                    mode=data.get("mode"),
                    payload=data,
                )
            )
        except Exception as exc:
            print(f"[WORKER_REGISTRY] Could not read worker file {file}: {exc}")
    return records


def _load_s3_worker_records(store: WorkerStore) -> List[WorkerRecord]:
    assert store.s3_client and store.bucket
    prefix = f"{store.prefix}/workers" if store.prefix else "workers"
    prefix = prefix.rstrip("/") + "/"
    records: List[WorkerRecord] = []

    _log(f"Listing workers from s3://{store.bucket}/{prefix}")
    paginator = store.s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=store.bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            try:
                body = store.s3_client.get_object(Bucket=store.bucket, Key=key)["Body"].read()
                data = json.loads(body)
                worker_id = data.get("worker_id") or Path(key).stem
                records.append(
                    WorkerRecord(
                        worker_id=worker_id,
                        hostname=data.get("hostname", "unknown"),
                        status=data.get("status", "unknown"),
                        last_seen=data.get("last_seen", ""),
                        active_job_id=data.get("active_job_id"),
                        mode=data.get("mode"),
                        payload=data,
                    )
                )
            except Exception as exc:
                _log(f"Failed to read worker key {key}: {exc}")
    return records


def list_workers() -> List[WorkerRecord]:
    store = _get_store()
    if store.kind == "s3":
        return _load_s3_worker_records(store)
    _log("Listing workers from local store")
    return _load_local_worker_records(store)