"""Utilities for tracking render runs, metadata, and manifests."""
from __future__ import annotations

import csv
import json
import os
import getpass
import platform
import subprocess
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from path_utils import RUNS_DIR, CODE_ROOT

try:  # Optional; only needed when BLENDOMATIC_RUN_STORE points at S3.
    import boto3  # type: ignore
    from botocore.exceptions import ClientError  # type: ignore
except Exception:  # pragma: no cover - boto3 not always installed locally
    boto3 = None  # type: ignore
    ClientError = Exception  # type: ignore

COUNTER_FILE = RUNS_DIR / ".counter"
MANIFEST_HEADERS = [
    "timestamp",
    "status",
    "garment",
    "fabric",
    "asset",
    "view",
    "output",
    "worker",
    "notes",
]

RUN_STORE_ENV = "BLENDOMATIC_RUN_STORE"
RUN_STORE_FALLBACK_ENV = "BLENDOMATIC_S3_STORE"


@dataclass
class RunContext:
    run_id: str
    path: Path
    metadata_path: Path
    notes_path: Path
    manifest_path: Path
    plan_path: Path


def _ensure_runs_dir() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _scan_existing_run_numbers() -> int:
    highest = 0
    if not RUNS_DIR.exists():
        return highest
    for child in RUNS_DIR.iterdir():
        if child.is_dir() and child.name.isdigit():
            try:
                highest = max(highest, int(child.name))
            except ValueError:
                continue
    return highest


def _read_git_commit() -> Optional[str]:
    try:
        result = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=CODE_ROOT)
        return result.decode().strip()
    except Exception:
        return None


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"Run store must be an s3:// URI, got '{uri}'")
    without = uri[5:]
    parts = without.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    return bucket, prefix


def _get_s3_counter_store() -> Optional[Dict[str, Any]]:
    uri = os.environ.get(RUN_STORE_ENV) or os.environ.get(RUN_STORE_FALLBACK_ENV)
    if not uri or not uri.startswith("s3://"):
        return None
    if boto3 is None:
        raise RuntimeError("BLENDOMATIC_RUN_STORE points at S3 but boto3 is not installed")
    bucket, prefix = _parse_s3_uri(uri)
    base_runs_prefix = f"{prefix.rstrip('/')}/runs" if prefix.strip("/") else "runs"
    client = boto3.client("s3")
    return {
        "bucket": bucket,
        "base_runs_prefix": base_runs_prefix.rstrip("/"),
        "client": client,
    }


def _read_s3_counter(store: Dict[str, Any]) -> Optional[int]:
    key = f"{store['base_runs_prefix']}/.counter"
    client = store["client"]
    try:
        result = client.get_object(Bucket=store["bucket"], Key=key)
        body = result["Body"].read().decode("utf-8").strip()
        return int(body)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    except Exception:
        return None


def _write_s3_counter(store: Dict[str, Any], value: int) -> None:
    key = f"{store['base_runs_prefix']}/.counter"
    payload = str(value)
    client = store["client"]
    client.put_object(
        Bucket=store["bucket"],
        Key=key,
        Body=payload.encode("utf-8"),
        ContentType="text/plain",
    )


def _scan_existing_s3_run_numbers(store: Dict[str, Any]) -> int:
    highest = 0
    prefix = store["base_runs_prefix"].rstrip("/") + "/"
    client = store["client"]
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=store["bucket"], Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            suffix = key[len(prefix) :]
            run_id = suffix.split("/", 1)[0]
            if run_id.isdigit():
                try:
                    highest = max(highest, int(run_id))
                except Exception:
                    continue
    return highest


def _read_local_counter() -> Optional[int]:
    if COUNTER_FILE.exists():
        try:
            return int(COUNTER_FILE.read_text().strip())
        except Exception:
            return None
    return None


def allocate_run_id(width: int = 4) -> str:
    _ensure_runs_dir()
    candidates: List[int] = []

    s3_store = _get_s3_counter_store()
    if s3_store:
        s3_counter = _read_s3_counter(s3_store)
        if s3_counter is None:
            s3_counter = _scan_existing_s3_run_numbers(s3_store)
        candidates.append(s3_counter)

    local_counter = _read_local_counter()
    if local_counter is not None:
        candidates.append(local_counter)
    candidates.append(_scan_existing_run_numbers())

    current = max(candidates) if candidates else 0
    next_value = current + 1

    COUNTER_FILE.write_text(str(next_value))
    if s3_store:
        _write_s3_counter(s3_store, next_value)
    return f"{next_value:0{width}d}"


def _json_serializable_plan(plan: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not plan:
        return []
    serializable: List[Dict[str, Any]] = []
    for item in plan:
        safe_item = {}
        for key, value in item.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_item[key] = value
            else:
                safe_item[key] = str(value)
        serializable.append(safe_item)
    return serializable


def create_run_record(
    *,
    note: str = "",
    mode: Optional[str] = None,
    garment: Optional[str] = None,
    fabrics: Optional[Iterable[str]] = None,
    assets: Optional[Iterable[str]] = None,
    views: Optional[Iterable[str]] = None,
    total_jobs: int = 0,
    plan: Optional[Iterable[Dict[str, Any]]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> RunContext:
    """Create a new run directory with metadata, notes, and manifest files."""
    run_id = allocate_run_id()
    run_path = RUNS_DIR / run_id
    run_path.mkdir(parents=True, exist_ok=True)

    metadata_path = run_path / "run.json"
    notes_path = run_path / "notes.md"
    manifest_path = run_path / "manifest.csv"
    plan_path = run_path / "plan.json"

    created_at = dt.datetime.utcnow().isoformat() + "Z"
    created_by = os.environ.get("BLENDOMATIC_RUN_USER") or getpass.getuser()
    hostname = platform.node()
    git_commit = _read_git_commit()

    metadata: Dict[str, Any] = {
        "run_id": run_id,
        "created_at": created_at,
        "created_by": created_by,
        "host": hostname,
        "git_commit": git_commit,
        "note": note.strip(),
        "mode": mode,
        "garment": garment,
        "fabrics": sorted(set(fabrics or [])),
        "assets": sorted(set(assets or [])),
        "views": sorted(set(views or [])),
        "total_jobs": total_jobs,
        "status": "pending",
    }
    if extra:
        metadata["extra"] = extra

    metadata_path.write_text(json.dumps(metadata, indent=2))

    note_body = note.strip() or "(no notes provided)"
    notes_path.write_text(f"# Run {run_id}\n\n{note_body}\n")

    serializable_plan = _json_serializable_plan(plan)
    plan_path.write_text(json.dumps(serializable_plan, indent=2))

    if not manifest_path.exists():
        with manifest_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=MANIFEST_HEADERS)
            writer.writeheader()

    return RunContext(
        run_id=run_id,
        path=run_path,
        metadata_path=metadata_path,
        notes_path=notes_path,
        manifest_path=manifest_path,
        plan_path=plan_path,
    )


def load_run_context(run_id: str) -> RunContext:
    run_path = RUNS_DIR / run_id
    if not run_path.exists():
        raise FileNotFoundError(f"Run '{run_id}' does not exist")
    return RunContext(
        run_id=run_id,
        path=run_path,
        metadata_path=run_path / "run.json",
        notes_path=run_path / "notes.md",
        manifest_path=run_path / "manifest.csv",
        plan_path=run_path / "plan.json",
    )


def update_run_metadata(run_ctx: RunContext, **updates: Any) -> None:
    data: Dict[str, Any] = {}
    if run_ctx.metadata_path.exists():
        try:
            data = json.loads(run_ctx.metadata_path.read_text())
        except Exception:
            data = {}
    data.update(updates)
    run_ctx.metadata_path.write_text(json.dumps(data, indent=2))


def append_manifest_entry(run_ctx: RunContext, entry: Dict[str, Any]) -> None:
    manifest_exists = run_ctx.manifest_path.exists()
    with run_ctx.manifest_path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_HEADERS)
        if not manifest_exists:
            writer.writeheader()
        row = {header: entry.get(header, "") for header in MANIFEST_HEADERS}
        writer.writerow(row)


def summarize_run(run_ctx: RunContext) -> Dict[str, Any]:
    if run_ctx.metadata_path.exists():
        try:
            return json.loads(run_ctx.metadata_path.read_text())
        except Exception:
            pass
    return {"run_id": run_ctx.run_id}
