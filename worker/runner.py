"""Shared worker runner used by the CLI daemon and the TUI client mode."""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from blender_tui_bridge import _run_job
from path_utils import RUNS_DIR
from run_state import prioritize_runs, update_run_state
from worker_registry import (
    get_worker_id,
    get_worker_mode,
    record_heartbeat,
)

try:  # Optional dependency for S3-based stores.
    import boto3  # type: ignore
    from botocore.exceptions import ClientError  # type: ignore
except Exception:  # pragma: no cover - boto3 not always installed locally
    boto3 = None  # type: ignore
    ClientError = Exception  # type: ignore

try:  # Thumbnail generation (optional fallback for local dev)
    from PIL import Image
except Exception:  # pragma: no cover - pillow optional until installed
    Image = None  # type: ignore

LOGGER = logging.getLogger("worker")
STORE_ENV = "BLENDOMATIC_RUN_STORE"
STORE_FALLBACK_ENV = "BLENDOMATIC_S3_STORE"
RUN_CACHE_ROOT = RUNS_DIR / "_worker_cache"
CONFIG_RENDER_ENV = "BLENDOMATIC_RENDER_CONFIG"
CONFIG_GARMENTS_ENV = "BLENDOMATIC_GARMENTS_DIR"
CONFIG_FABRICS_ENV = "BLENDOMATIC_FABRICS_DIR"

StatusCallback = Callable[[str, Dict[str, Any]], None]


@dataclass
class ClaimedJob:
    run_id: str
    job: Dict[str, Any]
    cache_path: Path


class RunStore:
    """Interface for run storage backends."""

    def list_run_ids(self) -> List[str]:
        raise NotImplementedError

    def load_jobs(self, run_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def save_jobs(self, run_id: str, jobs: List[Dict[str, Any]]) -> None:
        raise NotImplementedError

    def load_metadata(self, run_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def save_metadata(self, run_id: str, metadata: Dict[str, Any]) -> None:
        raise NotImplementedError

    def ensure_run_cache(self, run_id: str, cache_root: Path) -> Path:
        raise NotImplementedError

    def upload_output(self, run_id: str, source: Path) -> Optional[str]:
        raise NotImplementedError

    def upload_thumbnail(self, run_id: str, source: Path) -> Optional[str]:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError


class LocalRunStore(RunStore):
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def list_run_ids(self) -> List[str]:
        runs = [entry.name for entry in self.root.iterdir() if entry.is_dir() and entry.name.isdigit()]
        return sorted(runs)

    def load_jobs(self, run_id: str) -> List[Dict[str, Any]]:
        path = self._run_dir(run_id) / "jobs.json"
        return json.loads(path.read_text())

    def save_jobs(self, run_id: str, jobs: List[Dict[str, Any]]) -> None:
        path = self._run_dir(run_id) / "jobs.json"
        path.write_text(json.dumps(jobs, indent=2) + "\n")

    def load_metadata(self, run_id: str) -> Dict[str, Any]:
        path = self._run_dir(run_id) / "run.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def save_metadata(self, run_id: str, metadata: Dict[str, Any]) -> None:
        path = self._run_dir(run_id) / "run.json"
        path.write_text(json.dumps(metadata, indent=2) + "\n")

    def ensure_run_cache(self, run_id: str, cache_root: Path) -> Path:
        # Local nodes can work directly out of the run directory.
        return self._run_dir(run_id)

    def upload_output(self, run_id: str, source: Path) -> Optional[str]:
        target_dir = self._run_dir(run_id) / "outputs"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        return str(target)

    def upload_thumbnail(self, run_id: str, source: Path) -> Optional[str]:
        target_dir = self._run_dir(run_id) / "thumbnails"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copy2(source, target)
        return str(target)

    def describe(self) -> str:
        return f"local:{self.root}"


class S3RunStore(RunStore):
    def __init__(self, uri: str):
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 worker mode but is not installed")
        bucket, prefix = self._parse_uri(uri)
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self.base_runs_prefix = f"{self.prefix}/runs" if self.prefix else "runs"
        self.client = boto3.client("s3")

    @staticmethod
    def _parse_uri(uri: str) -> tuple[str, str]:
        if not uri.startswith("s3://"):
            raise ValueError(f"Run store must be an s3:// URI, got '{uri}'")
        without = uri[5:]
        parts = without.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        return bucket, prefix

    def describe(self) -> str:
        return f"s3://{self.bucket}/{self.base_runs_prefix}".rstrip("/")

    def _run_prefix(self, run_id: str) -> str:
        base = self.base_runs_prefix.rstrip("/")
        return f"{base}/{run_id}" if base else run_id

    def list_run_ids(self) -> List[str]:
        prefix = self.base_runs_prefix.rstrip("/") + "/"
        ids: set[str] = set()
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                suffix = key[len(prefix) :]
                run_id = suffix.split("/", 1)[0]
                if run_id.isdigit():
                    ids.add(run_id)
        return sorted(ids)

    def _read_text(self, key: str) -> str:
        result = self.client.get_object(Bucket=self.bucket, Key=key)
        return result["Body"].read().decode("utf-8")

    def _write_text(self, key: str, payload: str, content_type: str = "application/json") -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload.encode("utf-8"),
            ContentType=content_type,
        )

    def load_jobs(self, run_id: str) -> List[Dict[str, Any]]:
        key = f"{self._run_prefix(run_id)}/jobs.json"
        try:
            return json.loads(self._read_text(key))
        except ClientError as exc:
            raise RuntimeError(f"Unable to load jobs for run {run_id}: {exc}")

    def save_jobs(self, run_id: str, jobs: List[Dict[str, Any]]) -> None:
        key = f"{self._run_prefix(run_id)}/jobs.json"
        payload = json.dumps(jobs, indent=2) + "\n"
        self._write_text(key, payload)

    def load_metadata(self, run_id: str) -> Dict[str, Any]:
        key = f"{self._run_prefix(run_id)}/run.json"
        try:
            return json.loads(self._read_text(key))
        except Exception:
            return {}

    def save_metadata(self, run_id: str, metadata: Dict[str, Any]) -> None:
        key = f"{self._run_prefix(run_id)}/run.json"
        payload = json.dumps(metadata, indent=2) + "\n"
        self._write_text(key, payload)

    def ensure_run_cache(self, run_id: str, cache_root: Path) -> Path:
        run_cache = cache_root / run_id
        run_cache.mkdir(parents=True, exist_ok=True)
        configs_prefix = f"{self._run_prefix(run_id)}/configs"
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=configs_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel = key[len(self._run_prefix(run_id)) + 1 :]
                target = run_cache / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                self.client.download_file(self.bucket, key, str(target))
        return run_cache

    def upload_output(self, run_id: str, source: Path) -> Optional[str]:
        key = f"{self._run_prefix(run_id)}/outputs/{source.name}"
        content_type, _ = mimetypes.guess_type(source.name)
        self.client.upload_file(
            Filename=str(source),
            Bucket=self.bucket,
            Key=key,
            ExtraArgs={"ContentType": content_type or "application/octet-stream"},
        )
        return f"s3://{self.bucket}/{key}"

    def upload_thumbnail(self, run_id: str, source: Path) -> Optional[str]:
        key = f"{self._run_prefix(run_id)}/thumbnails/{source.name}"
        content_type, _ = mimetypes.guess_type(source.name)
        extra_args = {"ContentType": content_type or "image/jpeg"}
        self.client.upload_file(
            Filename=str(source),
            Bucket=self.bucket,
            Key=key,
            ExtraArgs=extra_args,
        )
        return f"s3://{self.bucket}/{key}"


def ensure_cache_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def temporary_env(overrides: Dict[str, str]):
    previous: Dict[str, Optional[str]] = {}
    try:
        for key, value in overrides.items():
            previous[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


class WorkerRunner:
    """Encapsulates the job polling/execution loop."""

    def __init__(
        self,
        store: RunStore,
        *,
        blender_executable: str,
        poll_interval: float = 15.0,
        once: bool = False,
        preferred_run: Optional[str] = None,
        status_callback: Optional[StatusCallback] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.store = store
        self.worker_id = get_worker_id()
        self.worker_mode = get_worker_mode("client")
        self.blender_exe = blender_executable
        self.poll_interval = poll_interval
        self.once = once
        self.preferred_run = preferred_run
        self.status_callback = status_callback
        self.logger = logger or LOGGER
        self.cache_root = ensure_cache_root(RUN_CACHE_ROOT)
        self._stopping = False

    def run(self) -> None:
        self._emit("started", store=self.store.describe())
        self._log("Worker %s starting (mode=%s, store=%s)", self.worker_id, self.worker_mode, self.store.describe())
        while not self._stopping:
            claimed: Optional[ClaimedJob]
            try:
                claimed = self._claim_next_job()
            except Exception as exc:  # pragma: no cover - defensive
                self._log("Warning while scanning runs: %s", exc)
                time.sleep(self.poll_interval)
                continue

            if not claimed:
                self._heartbeat("idle", info={"note": "waiting"})
                self._emit("idle", note="waiting")
                if self.once:
                    break
                self._sleep_interval()
                continue

            try:
                self._heartbeat(
                    "busy",
                    active_job_id=claimed.job.get("job_id"),
                    run_id=claimed.run_id,
                    info={"status": "rendering", "config": claimed.job.get("config", {})},
                )
                self._emit("job-claimed", run_id=claimed.run_id, job_id=claimed.job.get("job_id"))
                self._process_job(claimed)
            except Exception as exc:  # pragma: no cover - safety net
                self._log("Job %s failed: %s", claimed.job.get("job_id"), exc)
                self._emit("job-error", run_id=claimed.run_id, job_id=claimed.job.get("job_id"), error=str(exc))
            finally:
                self._heartbeat("idle")
                if self.once:
                    break
        self._emit("stopped", reason="runner-stop")

    def stop(self) -> None:
        self._stopping = True

    def _sleep_interval(self) -> None:
        slept = 0.0
        step = min(1.0, self.poll_interval)
        while not self._stopping and slept < self.poll_interval:
            time.sleep(step)
            slept += step

    def _log(self, message: str, *args: Any) -> None:
        try:
            self.logger.info(message, *args)
        except Exception:
            pass

    def _debug(self, message: str, **payload: Any) -> None:
        try:
            self.logger.debug(message)
        except Exception:
            pass
        details = dict(payload)
        details["message"] = message
        self._emit("runner-debug", **details)

    def _generate_thumbnail(self, source: Path) -> Optional[Path]:
        if Image is None:
            self._log("Pillow not installed; skipping thumbnail for %s", source)
            return None
        if not source.exists():
            return None
        thumb_path = source.with_name(f"{source.stem}_thumb.jpg")
        try:
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((512, 512), Image.LANCZOS)
                image.save(thumb_path, format="JPEG", quality=85, optimize=True)
            return thumb_path
        except Exception as exc:
            self._log("Failed to generate thumbnail for %s: %s", source, exc)
            return None

    def _emit(self, event: str, **payload: Any) -> None:
        if not self.status_callback:
            return
        try:
            self.status_callback(event, payload)
        except Exception:  # pragma: no cover - callbacks should not crash worker
            self._log("Status callback error for event %s", event)

    def _heartbeat(
        self,
        status: str,
        *,
        active_job_id: Optional[str] = None,
        run_id: Optional[str] = None,
        info: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            record_heartbeat(
                self.worker_id,
                status=status,
                active_job_id=active_job_id,
                run_id=run_id,
                info=info,
                mode=self.worker_mode,
            )
        except Exception as exc:  # pragma: no cover - best effort logging
            self._log("Failed to record heartbeat: %s", exc)

    def _claim_next_job(self) -> Optional[ClaimedJob]:
        run_ids = self.store.list_run_ids()
        self._debug(
            "Scanning runs",
            run_ids=list(run_ids),
            preferred=self.preferred_run,
        )
        ordered = prioritize_runs(run_ids, self.preferred_run)
        for run_id in ordered:
            claimed = self._claim_from_run(run_id)
            if claimed:
                return claimed
        self._debug("No claimable jobs found across runs", run_ids=list(run_ids))
        return None

    def _claim_from_run(self, run_id: str) -> Optional[ClaimedJob]:
        try:
            jobs = self.store.load_jobs(run_id)
        except Exception as exc:
            self._log("Failed to load jobs for run %s: %s", run_id, exc)
            return None

        total = len(jobs)
        pending = sum(1 for job in jobs if (job.get("status") or "").lower() == "pending")
        running = sum(1 for job in jobs if (job.get("status") or "").lower() == "running")
        completed = sum(1 for job in jobs if (job.get("status") or "").lower() == "completed")
        self._debug(
            f"Run {run_id}: total={total}, pending={pending}, running={running}, completed={completed}",
            run_id=run_id,
            total=total,
            pending=pending,
            running=running,
            completed=completed,
        )

        jobs_sorted = sorted(
            jobs,
            key=lambda job: (
                job.get("sequence") if isinstance(job.get("sequence"), int) else float("inf"),
                job.get("job_id"),
            ),
        )
        for job in jobs_sorted:
            if (job.get("status") or "").lower() != "pending":
                continue
            updated = self._transition_job(run_id, job, "pending", "running")
            if not updated:
                self._debug(
                    f"Job {job.get('job_id')} no longer pending when claiming",
                    run_id=run_id,
                    job_id=job.get("job_id"),
                )
                continue
            cache_path = self.store.ensure_run_cache(run_id, self.cache_root)
            return ClaimedJob(run_id=run_id, job=updated, cache_path=cache_path)
        self._debug(
            f"Run {run_id}: no pending jobs available after scan",
            run_id=run_id,
        )
        return None

    def _transition_job(
        self,
        run_id: str,
        job_snapshot: Dict[str, Any],
        expected_status: str,
        next_status: str,
        *,
        result_payload: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        job_id = job_snapshot.get("job_id")
        if not job_id:
            return None

        jobs = self.store.load_jobs(run_id)
        updated_jobs: List[Dict[str, Any]] = []
        changed_record: Optional[Dict[str, Any]] = None
        now = self._iso_now()
        for entry in jobs:
            if entry.get("job_id") != job_id:
                updated_jobs.append(entry)
                continue
            if (entry.get("status") or "").lower() != expected_status:
                self._debug(
                    f"Job {job_id} status mismatch (expected {expected_status}, found {entry.get('status')})",
                    run_id=run_id,
                    job_id=job_id,
                    expected=expected_status,
                    found=entry.get("status"),
                )
                return None
            record = dict(entry)
            record["status"] = next_status
            record["worker"] = self.worker_id
            record["updated_at"] = now
            if next_status == "running":
                record["started_at"] = now
            if next_status in {"completed", "failed"}:
                record["finished_at"] = now
                record["result"] = result_payload or record.get("result")
            if notes is not None:
                record["notes"] = notes
            changed_record = record
            updated_jobs.append(record)
        if not changed_record:
            self._debug(
                f"Job {job_id} not found while attempting transition",
                run_id=run_id,
                job_id=job_id,
            )
            return None
        self.store.save_jobs(run_id, updated_jobs)
        return changed_record

    def _process_job(self, claimed: ClaimedJob) -> None:
        job = claimed.job
        run_id = claimed.run_id
        job_id = job.get("job_id")
        config = job.get("config") or {}

        config_root = claimed.cache_path / "configs"
        overrides = {
            CONFIG_RENDER_ENV: str(config_root / "render_config.json"),
            CONFIG_GARMENTS_ENV: str(config_root / "garments"),
            CONFIG_FABRICS_ENV: str(config_root / "fabrics"),
        }

        job_payload = {
            "job_id": job_id,
            "run_id": run_id,
            "config": {
                "command": "render_with_config",
                "args": {
                    "mode": config.get("mode"),
                    "garment": config.get("garment"),
                    "fabric": config.get("fabric"),
                    "asset": config.get("asset"),
                    "view": config.get("view"),
                    "save_debug_files": config.get("save_debug_files", True),
                },
            },
        }

        job_dir = claimed.cache_path / "work"
        job_dir.mkdir(parents=True, exist_ok=True)
        job_file = job_dir / f"{job_id}.json"
        result_file = job_dir / f"{job_id}.result.json"
        job_file.write_text(json.dumps(job_payload, indent=2) + "\n")
        if result_file.exists():
            result_file.unlink()

        self._log("Running job %s (%s)", job_id, run_id)
        try:
            with temporary_env(overrides):
                exit_code = _run_job(job_file, self.blender_exe, result_file)
        except Exception as exc:
            error_msg = f"render failed: {exc}"
            self._log("Blender job %s crashed: %s", job_id, exc)
            self._transition_job(
                run_id,
                job,
                "running",
                "failed",
                result_payload={"error": error_msg},
                notes=error_msg,
            )
            self._update_run_metadata(run_id)
            self._emit("job-failed", run_id=run_id, job_id=job_id, error=error_msg)
            return

        result_data = json.loads(result_file.read_text()) if result_file.exists() else {}
        command_result = result_data.get("result") or {}
        success = bool(command_result.get("success")) and exit_code == 0

        if success:
            output_path = command_result.get("result")
            uploaded = self.store.upload_output(run_id, Path(output_path)) if output_path else None
            thumbnail_uploaded = None
            thumbnail_path: Optional[Path] = None
            if output_path:
                thumbnail_path = self._generate_thumbnail(Path(output_path))
                if thumbnail_path:
                    try:
                        thumbnail_uploaded = self.store.upload_thumbnail(
                            run_id, thumbnail_path
                        )
                    finally:
                        try:
                            thumbnail_path.unlink()
                        except Exception:
                            pass
            result_payload = {
                "output_path": output_path,
                "uploaded": uploaded,
            }
            if thumbnail_uploaded:
                result_payload["thumbnail"] = thumbnail_uploaded
            updated = self._transition_job(
                run_id,
                job,
                "running",
                "completed",
                result_payload=result_payload,
            )
            if not updated:
                self._log("Job %s completed but status update failed", job_id)
            self._emit(
                "job-completed",
                run_id=run_id,
                job_id=job_id,
                output_path=output_path,
                uploaded=uploaded,
            )
        else:
            error_msg = command_result.get("error") or f"blender exit code {exit_code}"
            self._transition_job(
                run_id,
                job,
                "running",
                "failed",
                result_payload={"error": error_msg},
                notes=error_msg,
            )
            self._emit("job-failed", run_id=run_id, job_id=job_id, error=error_msg)
        self._update_run_metadata(run_id)

    def _update_run_metadata(self, run_id: str) -> None:
        jobs = self.store.load_jobs(run_id)
        total = len(jobs)
        completed = sum(1 for job in jobs if job.get("status") == "completed")
        failed = sum(1 for job in jobs if job.get("status") == "failed")
        running = sum(1 for job in jobs if job.get("status") == "running")
        pending = total - completed - failed - running
        metadata = self.store.load_metadata(run_id)
        metadata["completed_jobs"] = completed
        metadata["failed_jobs"] = failed
        metadata["total_jobs"] = total
        metadata["pending_jobs"] = max(pending, 0)
        if completed == total and total > 0:
            metadata["status"] = "completed"
        elif failed > 0:
            metadata["status"] = "attention"
        elif running > 0:
            metadata["status"] = "running"
        else:
            metadata["status"] = metadata.get("status", "pending")
        metadata["last_activity"] = self._iso_now()
        self.store.save_metadata(run_id, metadata)
        update_run_state(run_id, status=metadata["status"], last_activity=metadata["last_activity"], last_worker=self.worker_id)

    @staticmethod
    def _iso_now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_run_store(uri: Optional[str] = None) -> RunStore:
    override = uri or os.environ.get(STORE_ENV)
    fallback = os.environ.get(STORE_FALLBACK_ENV)
    selected = override or fallback
    if selected and selected.startswith("s3://"):
        return S3RunStore(selected)
    root = RUNS_DIR
    return LocalRunStore(root)
