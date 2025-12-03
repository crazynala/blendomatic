"""Run state manifest helpers for coordinating farm priorities."""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

from path_utils import RUNS_DIR

STATE_PATH = RUNS_DIR / "state.json"
DEFAULT_PRIORITY = 100
_STATE_LOCK = threading.RLock()


def _coerce_run_id(run_id: str) -> int:
    try:
        return int(run_id)
    except Exception:
        return int(1e9)


def load_run_state() -> Dict[str, Any]:
    """Load the shared state manifest; return default structure when missing/corrupt."""
    with _STATE_LOCK:
        if not STATE_PATH.exists():
            return {"runs": {}, "default": {"priority": DEFAULT_PRIORITY}}
        try:
            data = json.loads(STATE_PATH.read_text())
            if "runs" not in data:
                data["runs"] = {}
            if "default" not in data:
                data["default"] = {"priority": DEFAULT_PRIORITY}
            return data
        except Exception:
            return {"runs": {}, "default": {"priority": DEFAULT_PRIORITY}}


def save_run_state(data: Dict[str, Any]) -> None:
    with _STATE_LOCK:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, indent=2) + "\n")


def update_run_state(run_id: str, **fields: Any) -> Dict[str, Any]:
    """Merge arbitrary fields into a run entry and persist."""
    with _STATE_LOCK:
        data = load_run_state()
        runs = data.setdefault("runs", {})
        entry = runs.get(run_id, {}).copy()
        entry.update(fields)
        runs[run_id] = entry
        save_run_state(data)
        return entry


def get_run_state(run_id: str) -> Dict[str, Any]:
    data = load_run_state()
    return data.get("runs", {}).get(run_id, {})


def prioritize_runs(run_ids: List[str], preferred: Optional[str] = None) -> List[str]:
    """Order run ids by manifest priority, skipping any paused entries."""
    state = load_run_state()
    runs = state.get("runs", {})
    default_priority = state.get("default", {}).get("priority", DEFAULT_PRIORITY)

    def _key(run_id: str):
        entry = runs.get(run_id, {})
        paused = bool(entry.get("paused"))
        priority = entry.get("priority", default_priority)
        sequence = entry.get("sequence")
        fallback = _coerce_run_id(run_id)
        return (paused, priority, sequence if isinstance(sequence, (int, float)) else fallback, fallback)

    ordered = sorted(run_ids, key=_key)
    filtered = [rid for rid in ordered if not runs.get(rid, {}).get("paused", False)]
    if preferred and preferred in filtered:
        return [preferred] + [rid for rid in filtered if rid != preferred]
    if preferred and preferred in run_ids:
        return [preferred] + filtered
    return filtered


def pause_run(run_id: str, paused: bool = True) -> Dict[str, Any]:
    return update_run_state(run_id, paused=paused)


def set_run_priority(run_id: str, priority: int) -> Dict[str, Any]:
    return update_run_state(run_id, priority=priority)
