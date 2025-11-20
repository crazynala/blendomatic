from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, DataTable, ProgressBar, Button
from textual import events
from typing import Optional, List

from render_state import RenderRunState, compute_global_progress, AssetStatus


class ExecutionScreen(Screen):
    """
    Shows:
      - Global progress bar, elapsed, ETA
      - Table of all assets with status + duration + progress
    """

    BINDINGS = [
        ("b", "back", "Back"),
    ]

    CSS = """
    ExecutionScreen {
        align: center middle;
    }
    
    #exec_container {
        width: 90%;
        height: 90%;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }
    
    #exec_header {
        height: 3;
        dock: top;
        content-align: center middle;
        text-style: bold;
    }
    
    #exec_stats {
        height: 3;
        margin: 1 0;
    }
    
    ProgressBar {
        margin: 1 0;
    }
    
    DataTable {
        height: 1fr;
        border: solid $secondary;
    }
    
    #exec_footer {
        height: 3;
        dock: bottom;
        align: center middle;
    }
    """

    def __init__(self, state: RenderRunState, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        self.state = state
        self.progress_bar: Optional[ProgressBar] = None
        self.summary_label: Optional[Static] = None
        self.table: Optional[DataTable] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="exec_container"):
            yield Static("🚀 Render Execution Dashboard", id="exec_header")
            
            with Horizontal(id="exec_stats"):
                self.summary_label = Static("Waiting for render...")
                yield self.summary_label
            
            self.progress_bar = ProgressBar(total=100, show_eta=False)
            yield self.progress_bar
            
            self.table = DataTable(id="assets-table")
            yield self.table
            
            with Horizontal(id="exec_footer"):
                yield Button("Back to Main", variant="primary", id="back_btn")

    def on_mount(self) -> None:
        # Configure table columns
        if self.table:
            self.table.cursor_type = "row"
            self.table.zebra_stripes = True
            self.table.add_columns("Asset", "Status", "Duration", "Progress")

        # Initial draw
        self._rebuild_table()
        self._update_global_status()

        # auto-refresh timer
        self.set_interval(0.5, self._refresh_view)

    def _refresh_view(self) -> None:
        """
        Periodic refresh, called from timer.
        Assumes self.state is being mutated by the subprocess reader.
        """
        self._rebuild_table()
        self._update_global_status()

    def _rebuild_table(self) -> None:
        if not self.table:
            return

        table = self.table
        # We'll update existing rows or add new ones
        # For simplicity in this version, we clear and re-add if count differs,
        # or update in place if we can map keys.
        # Textual DataTable supports updating cells by key if we use keys.
        
        # Let's try to be smart: use asset name as row key
        current_keys = set(table.rows.keys())
        col_keys = list(table.columns.keys())
        
        assets: List[AssetStatus] = list(self.state.assets.values())
        assets.sort(key=lambda a: a.name)
        
        for asset in assets:
            duration = f"{asset.duration_sec:.1f}s" if asset.duration_sec is not None else "-"
            progress_pct = int(asset.progress_0_1 * 100)
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "done": "✅",
                "error": "❌"
            }.get(asset.status, asset.status)
            
            row_data = (
                asset.name,
                f"{status_icon} {asset.status}",
                duration,
                f"{progress_pct}%",
            )
            
            if asset.name in current_keys:
                # Update existing row
                for col_idx, val in enumerate(row_data):
                    if col_idx < len(col_keys):
                        table.update_cell(asset.name, col_keys[col_idx], val)
            else:
                # Add new row
                table.add_row(*row_data, key=asset.name)

    def _update_global_status(self) -> None:
        if not self.progress_bar or not self.summary_label:
            return

        metrics = compute_global_progress(self.state)
        percent = int(metrics["percent_complete_0_1"] * 100)
        elapsed = metrics["elapsed_sec"]
        eta = metrics["eta_sec"]

        # Update progress bar
        self.progress_bar.update(progress=percent)

        # Format elapsed + ETA
        def fmt(sec: Optional[float]) -> str:
            if sec is None:
                return "--:--"
            m, s = divmod(int(sec), 60)
            return f"{m:02d}:{s:02d}"

        elapsed_str = fmt(elapsed)
        eta_str = fmt(eta) if eta is not None else "--:--"

        completed = self.state.completed_assets
        total = self.state.total_assets

        self.summary_label.update(
            f"Completed: {completed}/{total}  |  "
            f"Elapsed: {elapsed_str}  |  ETA: {eta_str}  |  "
            f"Global Progress: {percent}%"
        )

    def action_back(self) -> None:
        self.app.pop_screen()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back_btn":
            self.action_back()
