from dataclasses import dataclass, field
from typing import Dict, Optional
import re
import time


@dataclass
class AssetStatus:
    name: str
    output_path: Optional[str] = None
    status: str = "pending"  # "pending" | "running" | "done" | "error"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    duration_sec: Optional[float] = None
    progress_0_1: float = 0.0  # 0–1


@dataclass
class RenderRunState:
    assets: Dict[str, AssetStatus] = field(default_factory=dict)
    current_asset_name: Optional[str] = None
    run_started_at: float = field(default_factory=time.time)
    run_finished_at: Optional[float] = None
    run_id: Optional[str] = None

    @property
    def total_assets(self) -> int:
        return len(self.assets)

    @property
    def completed_assets(self) -> int:
        return sum(1 for a in self.assets.values() if a.status == "done")

    @property
    def avg_duration_sec(self) -> Optional[float]:
        durations = [a.duration_sec for a in self.assets.values() if a.duration_sec is not None]
        if not durations:
            return None
        return sum(durations) / len(durations)

    def mark_finished(self):
        if self.run_finished_at is None:
            self.run_finished_at = time.time()


class BlenderLogParser:
    """
    Consume Blender stdout/stderr lines and update RenderRunState.
    """

    # [RENDER] Output file: service_shirt_M-navy_royal_oxford-placket-reg.png
    OUTPUT_FILE_RE = re.compile(r"\[RENDER\]\s+Output file:\s+(?P<file>.+)")
    # Saved: '/path/to/file.png'
    SAVED_RE = re.compile(r"^Saved:\s+'(?P<path>.+)'")
    # Time: 00:07.54 (Saving: 00:00.03)
    FINAL_TIME_RE = re.compile(r"^Time:\s+(?P<mm>\d{2}):(?P<ss>\d{2}\.\d{2})")
    # Fra:1 ... | Sample 1/128 (Using optimized kernels)
    SAMPLE_RE = re.compile(r"Sample\s+(?P<cur>\d+)/(?P<total>\d+)")

    def __init__(self, state: RenderRunState):
        self.state = state

    def handle_line(self, line: str) -> bool:
        """
        Parse a single log line.
        Returns True if state was updated (so the TUI can refresh).
        """
        updated = False
        text = line.rstrip("\n")

        m = self.OUTPUT_FILE_RE.search(text)
        if m:
            file_name = m.group("file").strip()
            self._on_asset_start(file_name)
            return True

        m = self.SAVED_RE.search(text)
        if m:
            path = m.group("path").strip()
            self._on_asset_saved(path)
            return True

        m = self.FINAL_TIME_RE.search(text)
        if m:
            mm = int(m.group("mm"))
            ss = float(m.group("ss"))
            duration = mm * 60 + ss
            self._on_asset_duration(duration)
            return True

        m = self.SAMPLE_RE.search(text)
        if m:
            cur = int(m.group("cur"))
            total = int(m.group("total"))
            progress = cur / total if total > 0 else 0.0
            self._on_sample_progress(progress)
            return True

        return updated

    def mark_all_pending_as_error(self):
        """Mark all pending or running assets as error"""
        for asset in self.state.assets.values():
            if asset.status in ("pending", "running"):
                asset.status = "error"

    # --- internal helpers ---

    def _get_or_create_asset(self, name: str) -> AssetStatus:
        if name not in self.state.assets:
            self.state.assets[name] = AssetStatus(name=name)
        return self.state.assets[name]

    def _on_asset_start(self, file_name: str) -> None:
        asset = self._get_or_create_asset(file_name)
        asset.status = "running"
        asset.started_at = time.time()
        asset.progress_0_1 = 0.0
        self.state.current_asset_name = file_name

    def _on_asset_saved(self, path: str) -> None:
        from pathlib import Path
        filename = Path(path).name
        asset = self._get_or_create_asset(filename)
        asset.output_path = path
        if asset.started_at is None:
            asset.started_at = time.time()

    def _on_asset_duration(self, duration_sec: float) -> None:
        name = self.state.current_asset_name
        if not name:
            return
        asset = self._get_or_create_asset(name)
        asset.duration_sec = duration_sec
        asset.finished_at = (asset.started_at + duration_sec) if asset.started_at else time.time()
        asset.status = "done"
        asset.progress_0_1 = 1.0

    def _on_sample_progress(self, progress: float) -> None:
        name = self.state.current_asset_name
        if not name:
            return
        asset = self._get_or_create_asset(name)
        asset.progress_0_1 = max(asset.progress_0_1, min(1.0, progress))


def compute_global_progress(state: RenderRunState) -> dict:
    """
    Compute global progress + ETA from current state.
    """
    import time as _time

    total = state.total_assets
    if total == 0:
        return {"percent_complete_0_1": 0.0, "eta_sec": None, "elapsed_sec": 0.0}

    # If run is finished, use the finished time to calculate elapsed
    if state.run_finished_at is not None:
        elapsed = state.run_finished_at - state.run_started_at
    else:
        elapsed = _time.time() - state.run_started_at
        
    completed = state.completed_assets
    avg_duration = state.avg_duration_sec

    current_fraction = 0.0
    if state.current_asset_name:
        asset = state.assets[state.current_asset_name]
        current_fraction = asset.progress_0_1

    percent_complete = (completed + current_fraction) / total

    eta = None
    # Only calculate ETA if run is not finished
    if state.run_finished_at is None and avg_duration is not None:
        remaining_assets = max(total - completed - 1, 0)
        remaining_time = remaining_assets * avg_duration + (1.0 - current_fraction) * avg_duration
        eta = remaining_time
    elif state.run_finished_at is not None:
        eta = 0.0

    return {
        "percent_complete_0_1": max(0.0, min(1.0, percent_complete)),
        "eta_sec": eta,
        "elapsed_sec": elapsed,
    }
