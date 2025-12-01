"""
Fixed Blender TUI that properly handles Textual's logging system
This version avoids all conflicts with Textual's internal log property
"""
import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Header, Footer, Static, Button, SelectionList, Label, Log, Checkbox, Input
    from textual.screen import Screen
    from textual import on, events
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    # Create dummy classes to prevent import errors when textual unavailable
    class App: 
        def run(self): pass
    class ComposeResult: pass
    class Container: pass
    class Header: pass
    class Footer: pass
    class Static: pass
    class Button: 
        class Pressed: pass
    class SelectionList:
        SelectionHighlighted = object()
    class Label: pass
    class Log: pass
    class Checkbox: pass
    class Input: pass
    
    def on(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

# Path handling centralized
from path_utils import (
    GARMENTS_DIR,
    FABRICS_DIR,
    RENDER_CONFIG_PATH,
)

from blender_tui_bridge import BlenderTUISession
import sys
from render_state import RenderRunState, BlenderLogParser, AssetStatus
from execution_screen import ExecutionScreen

# Modal Screen Classes must be defined before use
if TEXTUAL_AVAILABLE:
    # Base single-error modal (robust even on older Textual versions)
    try:
        from textual.screen import ModalScreen
        from textual.widgets import Button, Label
        from textual.containers import Grid

        class JsonErrorModal(ModalScreen):
            """Modal screen to show JSON parsing errors with an OK button."""
            BINDINGS = []

            def __init__(self, file_path: str, error: str):
                super().__init__()
                self.file_path = file_path
                self.error = error

            def compose(self):
                yield Grid(
                    Label("❌ JSON Parsing Error", id="json_error_title"),
                    Label(f"File: {self.file_path}", id="json_error_path"),
                    Label(f"Error: {self.error}", id="json_error_message"),
                    Button("OK", variant="error", id="json_error_ok"),
                    id="json_dialog",
                )

            def on_button_pressed(self, event: Button.Pressed) -> None:
                try:
                    self.app.pop_screen()
                except Exception:
                    pass
    except Exception:
        JsonErrorModal = None  # type: ignore

    # Consolidated errors modal (optional; requires newer Textual widgets)
    try:
        from textual.widgets import Static
        from textual.containers import Horizontal, Vertical

        class JsonErrorsModal(ModalScreen):
            """Consolidated modal listing all JSON errors with details and Retry."""
            BINDINGS = []

            def __init__(self, errors: Dict[str, Dict[str, Any]]):
                super().__init__()
                self.errors: Dict[str, Dict[str, Any]] = errors
                self._selected: Optional[str] = next(iter(errors.keys()), None)
                self._list_mode: str = "auto"  # optionlist|buttons
                self._button_map: Dict[str, str] = {}
                self._label_to_path: Dict[str, str] = {}

            def compose(self):
                # Left: files list, Right: error details
                left_widget = None
                try:
                    # Prefer OptionList when available
                    from textual.widgets import OptionList  # type: ignore
                    files_list = OptionList(id="json_error_files")
                    for path in sorted(self.errors.keys(), key=lambda p: Path(p).name.lower()):
                        try:
                            label = Path(path).name
                        except Exception:
                            label = path
                        self._label_to_path[label] = path
                        try:
                            files_list.add_option(label)
                        except Exception:
                            pass
                    left_widget = files_list
                    self._list_mode = "optionlist"
                except Exception:
                    # Fallback: vertical list of buttons (no checkboxes)
                    from textual.widgets import Button as _Btn
                    buttons = []
                    self._button_map.clear()
                    for idx, path in enumerate(sorted(self.errors.keys(), key=lambda p: Path(p).name.lower())):
                        try:
                            label = Path(path).name
                        except Exception:
                            label = path
                        btn_id = f"json_file_btn_{idx}"
                        self._button_map[btn_id] = path
                        buttons.append(_Btn(label, id=btn_id))
                    left_widget = Vertical(*buttons, id="json_error_files_panel")
                    self._list_mode = "buttons"

                detail_title = Label("JSON Error Details", id="json_errors_detail_title")
                detail_path = Label("", id="json_errors_detail_path")
                detail_message = Label("", id="json_errors_detail_message")
                detail_snippet = Static("", id="json_errors_detail_snippet")

                # Buttons
                retry_btn = Button("Retry", id="json_errors_retry", variant="primary")
                close_btn = Button("Close", id="json_errors_close", variant="error")

                # Layout grid
                yield Grid(
                    Label("❌ JSON Parsing Errors Found", id="json_errors_title"),
                    Horizontal(
                        left_widget,
                        Grid(
                            detail_title,
                            detail_path,
                            detail_message,
                            detail_snippet,
                            id="json_errors_detail_grid",
                        ),
                        id="json_errors_split",
                    ),
                    Grid(retry_btn, close_btn, id="json_errors_buttons"),
                    id="json_errors_dialog",
                )

            def on_mount(self) -> None:
                self._update_details()
                # Highlight & select the initial file
                try:
                    if self._list_mode == "optionlist":
                        from textual.widgets import OptionList as _OL  # type: ignore
                        files_list = self.query_one("#json_error_files", _OL)
                        try:
                            files_list.index = 0  # highlight first
                        except Exception:
                            pass
                        try:
                            files_list.action_select_cursor()
                        except Exception:
                            pass
                    elif self._list_mode == "buttons":
                        # Focus first button and set selected
                        panel = self.query_one("#json_error_files_panel", Vertical)
                        btns = list(panel.query("Button"))
                        if btns:
                            try:
                                btns[0].focus()
                            except Exception:
                                pass
                            try:
                                self._selected = self._button_map.get(btns[0].id, self._selected)
                                self._update_details()
                            except Exception:
                                pass
                except Exception:
                    pass

            def _update_details(self) -> None:
                try:
                    detail_path = self.query_one("#json_errors_detail_path", Label)
                    detail_message = self.query_one("#json_errors_detail_message", Label)
                    detail_snippet = self.query_one("#json_errors_detail_snippet", Static)
                except Exception:
                    return
                if not self._selected or self._selected not in self.errors:
                    detail_path.update("")
                    detail_message.update("Select a file on the left to view details.")
                    try:
                        detail_snippet.update("")
                    except Exception:
                        pass
                    return
                info = self.errors[self._selected]
                line = info.get("line")
                col = info.get("column")
                loc = f" (line {line}, col {col})" if line and col else ""
                detail_path.update(f"File: {self._selected}")
                detail_message.update(f"Error: {info.get('message', 'Unknown error')}{loc}")
                snippet = info.get("snippet", "")
                try:
                    detail_snippet.update(snippet)
                except Exception:
                    pass

            def on_option_list_option_selected(self, event):
                try:
                    from textual.widgets import OptionList as _OL
                except Exception:
                    _OL = None
                if _OL and hasattr(event, 'option_list') and event.option_list.id == "json_error_files":
                    try:
                        label = str(getattr(event.option, 'prompt', ''))
                        path = self._label_to_path.get(label)
                        if path:
                            self._selected = path
                            self._update_details()
                    except Exception:
                        pass

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if self._list_mode != "buttons":
                    return
                btn_id = getattr(event.button, 'id', '') or ''
                if btn_id.startswith("json_file_btn_"):
                    path = self._button_map.get(btn_id)
                    if path:
                        self._selected = path
                        self._update_details()

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "json_errors_close":
                    try:
                        self.app.pop_screen()
                    except Exception:
                        pass
                elif event.button.id == "json_errors_retry":
                    # Ask app to rescan and update this modal
                    try:
                        if hasattr(self.app, "_rescan_json_errors_and_update_modal"):
                            self.app._rescan_json_errors_and_update_modal(self)
                    except Exception:
                        pass
    except Exception:
        JsonErrorsModal = None  # type: ignore

    class GarmentSelectionList(SelectionList):
        """SelectionList variant that only toggles when its checkbox is clicked."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._last_pointer_on_checkbox: bool = True

        def on_click(self, event: events.Click) -> None:  # type: ignore[override]
            try:
                gutter = self._get_left_gutter_width()
                # Checkbox lives inside the left gutter area; clicks past it should not toggle.
                self._last_pointer_on_checkbox = event.x <= gutter if gutter else True
            except Exception:
                self._last_pointer_on_checkbox = True
            if not self._last_pointer_on_checkbox:
                try:
                    option_index = getattr(event.style, "meta", {}).get("option")
                except Exception:
                    option_index = None
                if option_index is not None:
                    try:
                        self.index = option_index  # Move highlight without toggling checkbox
                    except Exception:
                        pass
                event.stop()
                return None
            handler = getattr(super(), "on_click", None)
            if handler:
                return handler(event)
            return None

        def _on_option_list_option_selected(self, event):  # type: ignore[override]
            is_checkbox = getattr(self, "_last_pointer_on_checkbox", True)
            # Reset after each click to keep keyboard toggles functional.
            self._last_pointer_on_checkbox = True
            if not is_checkbox:
                event.stop()
                return
            super()._on_option_list_option_selected(event)
else:
    JsonErrorModal = None  # type: ignore
    JsonErrorsModal = None  # type: ignore
    class GarmentSelectionList(SelectionList):
        pass

class BlenderTUIApp(App):
    """
    Textual TUI that communicates with Blender via bridge
    Properly handles Textual's logging system without conflicts
    """
    
    TITLE = "Blendomatic - Blender TUI"
    
    CSS = """
    .left_column {
        width: 25%;
        margin: 0 1 1 0;
        padding: 1;
    }
    
    .middle_column {
        width: 35%;
        margin: 0 1 1 0;
        padding: 1;
    }
    
    .right_column {
        width: 40%;
        margin: 0 0 1 0;
        padding: 1;
    }
    
    .controls_row {
        height: 4;
        margin: 0 0 0 0;
        padding: 0;
        border-top: solid white;
    }
    
    .timeout_config {
        width: 40%;
        margin: 0 1 0 0;
        padding: 0 1 0 0;
    }
    
    .message_panel {
        dock: bottom;
        height: 35%;
        margin: 1;
        padding: 1;
        border-top: solid white;
        overflow: hidden;
    }
    
    Log {
        scrollbar-size: 1 1;
    }
    
    SelectionList {
        height: 12;
        border: solid gray;
        margin: 0 0 1 0;
        overflow-y: auto;
        scrollbar-color: $secondary $background;
    }

    #mode_list {
        height: 5;
        overflow-y: auto;
        border: solid $primary;
    }
    #view_list {
        height: 5;
        overflow-y: auto;
        border: solid $primary;
    }
    #fabric_list {
        border: solid $primary;
    }
    #garment_list {
        border: solid $primary;
    }
    #asset_list {
        border: solid $primary;
    }
    
    Button {
        height: 3;
        margin: 0 1 0 0;
        width: 15;
    }
    
    Input {
        height: 1;
        margin: 0 0 1 0;
        width: 10;
    }
    
    Checkbox {
        margin: 0 0 1 0;
    }

    /* Modal styling for JSON error */
    JsonErrorModal {
        align: center middle;
    }

    #json_dialog {
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 3 3;
        padding: 0 1;
        width: 80;
        height: 12;
        border: thick $background 80%;
        background: $surface;
    }

    #json_error_title {
        column-span: 2;
        height: 1fr;
        width: 1fr;
        content-align: center middle;
    }

    #json_error_path {
        column-span: 2;
    }

    #json_error_message {
        column-span: 2;
    }

    #json_dialog Button {
        width: 100%;
    }

    /* Consolidated JSON errors modal */
    JsonErrorsModal {
        align: center middle;
    }

    #json_errors_dialog {
        grid-size: 1;
        grid-rows: auto 1fr auto;
        padding: 1 2;
        width: 100;
        height: 24;
        border: thick $background 80%;
        background: $surface;
    }

    #json_errors_title {
        height: 3;
        content-align: center middle;
    }

    #json_errors_split {
        height: 1fr;
        width: 1fr;
    }

    #json_errors_split OptionList {
        width: 40%;
        height: 100%;
        border: solid $primary;
        margin-right: 2;
    }

    #json_error_files_panel {
        width: 40%;
        height: 100%;
        margin-right: 2;
        border: solid $primary;
    }

    #json_error_files_panel Button {
        width: 100%;
        content-align: left middle;
    }

    #json_errors_detail_grid {
        width: 60%;
        height: 100%;
        grid-size: 1;
        grid-rows: auto auto auto 1fr;
        padding: 1;
        border: solid $secondary;
    }

    #json_errors_detail_title {
        content-align: left middle;
    }

    #json_errors_detail_path {
        color: $text 60%;
    }

    #json_errors_detail_message {
        color: $warning;
        overflow: auto;
    }

    #json_errors_detail_snippet {
        overflow: auto;
        height: 1fr;
        padding: 1 0 0 0;
        border-top: dashed $secondary 50%;
        color: $text;
        text-style: bold;
    }

    #json_errors_buttons {
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 2;
        height: 3;
    }
    """
    
    def __init__(self, blender_executable="blender"):
        super().__init__()
        self.session: Optional[BlenderTUISession] = None
        self.blender_exe = blender_executable
        
        # UI components - avoid 'log' in names to prevent conflicts
        self.message_display: Optional[Log] = None  # Renamed from log_display
        self.mode_list: Optional[SelectionList] = None
        self.garment_list: Optional[SelectionList] = None
        self.fabric_list: Optional[SelectionList] = None
        self.asset_list: Optional[SelectionList] = None
        self.view_list: Optional[SelectionList] = None
        self.toggle_all_checkbox: Optional[Checkbox] = None
        self.save_debug_checkbox: Optional[Checkbox] = None
        self.render_button: Optional[Button] = None
        self.cancel_button: Optional[Button] = None
        
        # Local data caches
        self.garment_data: Dict[str, Any] = {}
        self.current_garment_name: Optional[str] = None
        
        # Local selections (work without Blender bridge)
        self.selected_mode: Optional[str] = None
        self.selected_garment: Optional[str] = None  
        self.selected_fabrics: List[str] = []
        self.selected_assets: List[str] = []
        self.selected_views: List[str] = []
        
        # Debug files configuration
        self.save_debug_files: bool = False
        
        # Rendering state
        self.is_rendering: bool = False
        self.current_render_task: Optional[asyncio.Task] = None
        self.current_log_task: Optional[asyncio.Task] = None
        self.render_pid: Optional[int] = None

        # JSON errors + watcher
        self._json_errors: Dict[str, Dict[str, Any]] = {}
        self._json_watch_task: Optional[asyncio.Task] = None
        self._json_changed_flag: bool = False
        self._json_last_scan: Dict[str, float] = {}

        # Cached data for toggle-all / recall logic
        self.available_garments: List[str] = []
        self.available_fabrics: List[str] = []
        self.available_assets: List[str] = []
        self.available_views: List[str] = []

        # Display name + per-garment selection caches
        self.garment_display_names: Dict[str, str] = {}
        self.fabric_display_names: Dict[str, str] = {}
        self.asset_selection_by_garment: Dict[str, List[str]] = {}
        self.view_selection_by_garment: Dict[str, List[str]] = {}

        # Execution state
        self.render_state = RenderRunState()
        self.log_parser = BlenderLogParser(self.render_state)
    
    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """Load a JSON file safely"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # Specific JSON parse error: record and show consolidated modal
            self.write_message(f"❌ JSON parse error in {file_path}: {e}")
            self._record_json_error(str(file_path))
            return {}
        except Exception as e:
            self.write_message(f"❌ Error loading {file_path}: {e}")
            self._record_json_error(str(file_path), generic_message=str(e))
            return {}

    # -----------------------------
    # JSON Watch / Consolidated Modal
    # -----------------------------
    def _json_candidate_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        try:
            if GARMENTS_DIR and GARMENTS_DIR.exists():
                dirs.append(GARMENTS_DIR)
        except Exception:
            pass
        try:
            if FABRICS_DIR and FABRICS_DIR.exists():
                dirs.append(FABRICS_DIR)
        except Exception:
            pass
        try:
            if RENDER_CONFIG_PATH and RENDER_CONFIG_PATH.exists():
                dirs.append(RENDER_CONFIG_PATH.parent)
        except Exception:
            pass
        # De-duplicate
        seen = set()
        unique_dirs: List[Path] = []
        for d in dirs:
            if str(d) not in seen:
                seen.add(str(d))
                unique_dirs.append(d)
        return unique_dirs

    def _json_files_to_check(self) -> List[Path]:
        files: List[Path] = []
        for d in self._json_candidate_dirs():
            try:
                files.extend(sorted(d.glob("*.json")))
            except Exception:
                pass
        # Ensure render_config explicitly included
        try:
            if RENDER_CONFIG_PATH and RENDER_CONFIG_PATH.exists() and RENDER_CONFIG_PATH not in files:
                files.append(RENDER_CONFIG_PATH)
        except Exception:
            pass
        return files

    def _extract_json_error_info(self, path: Path) -> Optional[Dict[str, Any]]:
        """Try parsing JSON and return structured error info when failing."""
        try:
            with open(path, "r") as f:
                json.load(f)
            return None
        except json.JSONDecodeError as e:
            info: Dict[str, Any] = {"message": e.msg, "line": e.lineno, "column": e.colno}
            # Build context snippet
            try:
                text = path.read_text()
                lines = text.splitlines()
                idx = (e.lineno - 1) if e.lineno else 0
                start = max(0, idx - 2)
                end = min(len(lines), idx + 3)
                snippet_lines: List[str] = []
                for i in range(start, end):
                    pointer = ">" if i == idx else " "
                    snippet_lines.append(f"{pointer} {i+1:4d} | {lines[i]}")
                    if i == idx and e.colno and e.colno > 0:
                        caret_indent = " " * (7 + len(str(i+1)) + e.colno)  # rough align caret under character
                        snippet_lines.append(f"      | {caret_indent}^")
                info["snippet"] = "\n".join(snippet_lines)
            except Exception:
                pass
            return info
        except Exception as e:
            return {"message": str(e)}

    def _scan_all_json_errors(self) -> Dict[str, Dict[str, Any]]:
        errors: Dict[str, Dict[str, Any]] = {}
        for p in self._json_files_to_check():
            info = self._extract_json_error_info(p)
            if info:
                errors[str(p)] = info
        return errors

    def _record_json_error(self, path: str, generic_message: Optional[str] = None) -> None:
        p = Path(path)
        info = self._extract_json_error_info(p)
        if not info:
            # fallback when not a JSON decode error
            info = {"message": generic_message or "Unknown error"}
        self._json_errors[path] = info
        self._json_changed_flag = True
        # Show consolidated modal
        self._show_json_errors_modal()

    def _show_json_errors_modal(self) -> None:
        if JsonErrorsModal is None:
            # Fallback: show single error modal when consolidated unavailable
            if self._json_errors:
                path, info = next(iter(self._json_errors.items()))
                msg = info.get("message", "Unknown error") if isinstance(info, dict) else str(info)
                self._show_json_error_modal(path, msg)
            return

        def _push_or_update():
            # If a modal already present, replace it by pushing a new one
            try:
                self.push_screen(JsonErrorsModal(dict(self._json_errors)))
            except Exception as e:
                self.write_message(f"⚠️ Failed to open consolidated JSON modal: {e}")

        try:
            self.call_from_thread(_push_or_update)
        except Exception:
            _push_or_update()

    def _rescan_json_errors_and_update_modal(self, modal: Optional["JsonErrorsModal"]) -> None:
        # Run an async rescan with a short delay to avoid reading during writes
        async def _rescan_and_update():
            try:
                await asyncio.sleep(0.25)
                fresh = self._scan_all_json_errors()
                self._json_errors = fresh
            except Exception as e:
                self.write_message(f"⚠️ JSON rescan failed: {e}")
                return

            try:
                if not self._json_errors:
                    try:
                        self.pop_screen()
                    except Exception:
                        pass
                    try:
                        await self.refresh_all_lists()
                    except Exception:
                        pass
                else:
                    try:
                        self.pop_screen()
                    except Exception:
                        pass
                    if JsonErrorsModal is not None:
                        self.push_screen(JsonErrorsModal(dict(self._json_errors)))
            except Exception as e:
                self.write_message(f"⚠️ Modal update failed: {e}")

        try:
            asyncio.create_task(_rescan_and_update())
        except Exception:
            # Fallback synchronous path
            try:
                self._json_errors = self._scan_all_json_errors()
            except Exception:
                return
            if not self._json_errors:
                try:
                    self.pop_screen()
                except Exception:
                    pass
                try:
                    asyncio.create_task(self.refresh_all_lists())
                except Exception:
                    pass
            else:
                if JsonErrorsModal is not None:
                    self.push_screen(JsonErrorsModal(dict(self._json_errors)))
    
    def _get_local_garments(self) -> List[Dict[str, str]]:
        """Return garment filenames with user-facing display names."""
        garments: List[Dict[str, str]] = []
        if not GARMENTS_DIR.exists():
            return garments
        for file_path in sorted(GARMENTS_DIR.glob("*.json")):
            display_name = file_path.stem
            data = self._load_json_file(file_path)
            if isinstance(data, dict):
                display_name = data.get("name") or display_name
            garments.append({"file_name": file_path.name, "display_name": display_name})
        return garments
    
    def _get_local_fabrics(self) -> List[Dict[str, str]]:
        """Return fabric filenames with user-facing display names."""
        fabrics: List[Dict[str, str]] = []
        if not FABRICS_DIR.exists():
            return fabrics
        for file_path in sorted(FABRICS_DIR.glob("*.json")):
            display_name = file_path.stem
            data = self._load_json_file(file_path)
            if isinstance(data, dict):
                display_name = data.get("name") or display_name
            fabrics.append({"file_name": file_path.name, "display_name": display_name})
        return fabrics
    
    def _get_garment_assets(self, garment_name: str) -> List[str]:
        """Get assets for a specific garment from local file"""
        if not garment_name:
            return []
            
        garment_path = GARMENTS_DIR / garment_name
        if not garment_path.exists():
            return []
            
        garment_data = self._load_json_file(garment_path)
        assets = garment_data.get("assets", [])
        return [asset.get("name", "") for asset in assets if asset.get("name")]

    def _extract_garment_views(self, garment_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Normalize view definitions from a garment file."""
        views: List[Dict[str, Any]] = []
        fallback_blend = garment_data.get("blend_file")
        fallback_prefix = garment_data.get("output_prefix") or garment_data.get("name") or "garment"
        raw_views = garment_data.get("views")

        if isinstance(raw_views, list) and raw_views:
            for view in raw_views:
                if not isinstance(view, dict):
                    continue
                code = (view.get("code") or "").strip()
                blend_file = view.get("blend_file") or fallback_blend
                output_prefix = view.get("output_prefix") or fallback_prefix
                if not code or not blend_file:
                    continue
                views.append({
                    "code": code,
                    "blend_file": blend_file,
                    "output_prefix": output_prefix,
                })

        if not views and fallback_blend:
            views.append({
                "code": garment_data.get("default_view", "default"),
                "blend_file": fallback_blend,
                "output_prefix": fallback_prefix,
            })

        return views

    def _set_selection_values(self, selection_list: Optional[SelectionList], values: List[str]) -> None:
        """Synchronize a SelectionList with explicit values."""
        if not selection_list:
            return
        try:
            selection_list.deselect_all()
        except Exception:
            pass
        for value in values:
            try:
                selection_list.select(value)
            except Exception:
                continue

    def _get_display_label(self, mapping: Dict[str, str], key: Optional[str]) -> str:
        if not key:
            return "Not selected"
        return mapping.get(key, key)

    def _get_views_for_garment(self, garment_name: Optional[str]) -> List[str]:
        if not garment_name:
            return []
        if garment_name == self.current_garment_name:
            return list(self.selected_views)
        return list(self.view_selection_by_garment.get(garment_name, []))

    def _get_assets_for_garment(self, garment_name: Optional[str]) -> List[str]:
        if not garment_name:
            return []
        if garment_name == self.current_garment_name:
            return list(self.selected_assets)
        return list(self.asset_selection_by_garment.get(garment_name, []))
    

    
    def validate_render_config(self) -> List[Dict[str, Any]]:
        """Validate selections and return list of fabric × asset × view combinations."""
        errors = []
        
        if not self.selected_mode:
            errors.append("Mode not selected")
        if not self.selected_garment:
            errors.append("Garment not selected")
        if not self.selected_fabrics:
            errors.append("No fabrics selected")
        
        if errors:
            raise ValueError(f"Missing selections: {', '.join(errors)}")

        assets_for_render = self._get_assets_for_garment(self.selected_garment)
        views_for_render = self._get_views_for_garment(self.selected_garment)

        if not assets_for_render:
            raise ValueError("Missing selections: No assets selected")
        if not views_for_render:
            raise ValueError("Missing selections: No views selected")

        garment_path = GARMENTS_DIR / self.selected_garment
        if not garment_path.exists():
            raise ValueError(f"Garment file not found: {garment_path}")

        garment_data = self._load_json_file(garment_path)
        if not garment_data:
            raise ValueError(f"Failed to load garment: {self.selected_garment}")

        views = self._extract_garment_views(garment_data)
        if not views:
            raise ValueError(f"Garment '{garment_data.get('name', self.selected_garment)}' has no views configured")

        views_by_code = {view["code"]: view for view in views}
        ordered_view_codes = [view["code"] for view in views]

        selected_view_pool = set(views_for_render)
        selected_view_codes = [code for code in ordered_view_codes if code in selected_view_pool]
        if not selected_view_codes:
            if views_for_render:
                self.write_message("⚠️ Selected views are not available on this garment; using all views instead")
            selected_view_codes = ordered_view_codes
        selected_view_set = set(selected_view_codes)

        asset_map = {
            asset.get("name"): asset
            for asset in garment_data.get("assets", [])
            if asset.get("name")
        }

        configs: List[Dict[str, Any]] = []
        for fabric in self.selected_fabrics:
            for asset_name in assets_for_render:
                asset_def = asset_map.get(asset_name)
                if not asset_def:
                    raise ValueError(f"Asset '{asset_name}' not found in garment definition")

                raw_requested = asset_def.get("render_views")
                if isinstance(raw_requested, list) and raw_requested:
                    requested_views = [str(code) for code in raw_requested if isinstance(code, (str, int))]
                elif isinstance(raw_requested, str) and raw_requested:
                    requested_views = [raw_requested]
                elif raw_requested:
                    requested_views = [str(raw_requested)]
                else:
                    requested_views = ordered_view_codes

                requested_set = set(requested_views)
                valid_views = [
                    code
                    for code in ordered_view_codes
                    if code in requested_set and code in selected_view_set
                ]

                missing_views = [code for code in requested_views if code not in views_by_code]
                if missing_views:
                    self.write_message(
                        f"⚠️ Asset '{asset_name}' references unknown views: {', '.join(missing_views)}"
                    )

                if not valid_views:
                    raise ValueError(
                        f"Asset '{asset_name}' is not configured for any of the selected views (selected: {', '.join(selected_view_codes)})"
                    )

                asset_suffix = asset_def.get('suffix') or asset_name.replace(" ", "_").lower()

                for view_code in valid_views:
                    view_info = views_by_code.get(view_code, {})
                    config = {
                        'mode': self.selected_mode,
                        'garment': self.selected_garment,
                        'fabric': fabric,
                        'asset': asset_name,
                        'view': view_code,
                        'view_output_prefix': view_info.get('output_prefix'),
                        'asset_suffix': asset_suffix,
                        'save_debug_files': self.save_debug_files
                    }
                    configs.append(config)
        
        return configs
    
    def compose(self):
        yield Header(show_clock=True)
        
        with Container():
            # Three-column main layout
            with Horizontal():
                # Left column: Mode & Fabric
                with Vertical(classes="left_column"):
                    self.mode_list = SelectionList(id="mode_list")
                    yield self.mode_list
                    self.toggle_all_checkbox = Checkbox("Select All", value=False, id="toggle_all_checkbox")
                    yield self.toggle_all_checkbox
                    self.fabric_list = SelectionList(id="fabric_list")
                    yield self.fabric_list
                    # Set border titles programmatically (Textual doesn't support border-title in CSS)
                    for widget, title in [
                        (self.mode_list, "Mode"),
                        (self.fabric_list, "Fabric")
                    ]:
                        try:
                            widget.border_title = title  # Newer API
                        except Exception:
                            try:
                                widget.styles.border_title = title  # Fallback API
                            except Exception:
                                pass
                
                # Middle column: Garments
                with Vertical(classes="middle_column"):
                    self.garment_list = GarmentSelectionList(id="garment_list")
                    yield self.garment_list
                    try:
                        self.garment_list.border_title = "Garment"
                    except Exception:
                        try:
                            self.garment_list.styles.border_title = "Garment"
                        except Exception:
                            pass
                
                # Right column: Assets
                with Vertical(classes="right_column"):
                    self.view_list = SelectionList(id="view_list")
                    yield self.view_list
                    self.asset_list = SelectionList(id="asset_list")
                    yield self.asset_list
                    try:
                        self.view_list.border_title = "Views"
                    except Exception:
                        try:
                            self.view_list.styles.border_title = "Views"
                        except Exception:
                            pass
                    try:
                        self.asset_list.border_title = "Asset"
                    except Exception:
                        try:
                            self.asset_list.styles.border_title = "Asset"
                        except Exception:
                            pass
            
            # Bottom section: Render controls
            with Horizontal(classes="controls_row"):
                # Save debug files toggle near render button
                self.save_debug_checkbox = Checkbox("Save debug files", value=False, id="save_debug_checkbox")
                yield self.save_debug_checkbox
                
                self.render_button = Button("🎬 RENDER", id="render_btn", variant="success", flat=True)
                yield self.render_button
                self.cancel_button = Button("❌ CANCEL", id="cancel_btn", variant="error")
                self.cancel_button.display = False  # Hidden by default
                yield self.cancel_button
            
            # Message panel
            with Container(classes="message_panel"):
                yield Static("📄 Messages & Blender Output", id="message_title")
                self.message_display = Log(auto_scroll=True)
                yield self.message_display
        
        yield Footer()
    
    async def on_mount(self):
        """Initialize the session when app starts"""
        self.write_message("🚀 Initializing Blender TUI...")
        # Log Textual version and consolidated modal support for diagnostics
        try:
            import textual  # type: ignore
            ver = getattr(textual, "__version__", "unknown")
            consolidated = "enabled" if (TEXTUAL_AVAILABLE and 'JsonErrorsModal' in globals() and JsonErrorsModal is not None) else "disabled"
            self.write_message(f"🔧 DEBUG: Textual v{ver}; consolidated JSON modal {consolidated}")
        except Exception:
            pass
        
        # Always load local file data (garments, fabrics) regardless of bridge status
        await self.refresh_all_lists()
        
        # Try to initialize Blender bridge (for modes and actual rendering)
        try:
            self.write_message("🔗 Connecting to Blender bridge...")
            self.session = await asyncio.get_event_loop().run_in_executor(
                None, lambda: BlenderTUISession(self.blender_exe)
            )
            
            self.write_message("✅ Blender bridge connected")
            # Refresh again to get modes from bridge
            await self.refresh_all_lists()
            await self.update_local_status()
            
        except Exception as e:
            self.write_message(f"⚠️  Blender bridge unavailable: {e}")
            self.write_message("📁 Running in file-only mode (no rendering)")
        
        # Start background JSON watcher (polling with debounce)
        try:
            self._json_watch_task = asyncio.create_task(self._json_watch_loop())
        except Exception as e:
            self.write_message(f"⚠️ Failed to start JSON watcher: {e}")

        # Initial proactive scan; show consolidated modal if any errors
        try:
            self._json_errors = self._scan_all_json_errors()
            if self._json_errors:
                self.write_message(f"❌ Found JSON issues in {len(self._json_errors)} files; opening modal.")
                self._show_json_errors_modal()
        except Exception as e:
            self.write_message(f"⚠️ Initial JSON scan failed: {e}")

        self.write_message("✅ TUI ready - click on items to select them")
    
    def write_message(self, message: str):
        """Write message to the message display (avoiding 'log' method name)"""
        if self.message_display:
            self.message_display.write_line(message)
        # Also use Textual's built-in logging properly
        if hasattr(self, 'log') and hasattr(self.log, 'info'):
            self.log.info(message)
        print(message)  # Also print to console for debugging

    # -------------------------------------------------
    # JSON Error Modal Handling
    # -------------------------------------------------
    def _show_json_error_modal(self, path: str, error: str):
        """Display a modal screen with JSON parsing error details."""
        try:
            if JsonErrorModal is None:
                raise RuntimeError("JsonErrorModal unavailable")

            def _push():
                try:
                    self.push_screen(JsonErrorModal(path, error))
                except Exception as _inner:
                    self.write_message(f"⚠️ Failed to push modal: {_inner}")

            # Use Textual's thread-safe scheduler if available
            try:
                self.call_from_thread(_push)
            except Exception:
                # If we're on the UI thread, push directly
                _push()
        except Exception as e:
            # Fallback: ensure at least logged
            self.write_message(f"⚠️ Failed to show error modal: {e}")

    async def _json_watch_loop(self):
        """Poll JSON files for changes and rescan with debounce."""
        debounce_window = 0.5  # seconds
        scan_interval = 1.0    # seconds
        pending_since: Optional[float] = None

        while True:
            try:
                await asyncio.sleep(scan_interval)
                changed = False
                for p in self._json_files_to_check():
                    try:
                        mtime = p.stat().st_mtime
                    except Exception:
                        mtime = 0.0
                    prev = self._json_last_scan.get(str(p))
                    if prev is None or mtime > prev:
                        changed = True
                        self._json_last_scan[str(p)] = mtime

                if changed:
                    now = asyncio.get_event_loop().time()
                    if pending_since is None:
                        pending_since = now
                    # If stable for debounce_window, perform scan
                    if now - pending_since >= debounce_window:
                        pending_since = None
                        new_errors = self._scan_all_json_errors()
                        # Only update and show modal if changed
                        if new_errors != self._json_errors:
                            self._json_errors = new_errors
                            if self._json_errors:
                                self.write_message(f"❌ JSON issues detected: {len(self._json_errors)} files")
                                self._show_json_errors_modal()
                            else:
                                self.write_message("✅ JSON issues resolved")
                                try:
                                    # Close any existing modal by pushing close
                                    self.call_from_thread(lambda: self.pop_screen())
                                except Exception:
                                    pass
                                # Refresh lists when things parse OK
                                try:
                                    await self.refresh_all_lists()
                                except Exception:
                                    pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.write_message(f"⚠️ JSON watch loop error: {e}")
                # continue loop
    
    async def refresh_all_lists(self):
        """Refresh all selection lists"""
        try:
            # Get modes from render config file (local loading as fallback)
            modes = []
            if self.session:
                try:
                    modes = await asyncio.get_event_loop().run_in_executor(
                        None, self.session.list_modes
                    )
                    self.write_message(f"🔧 DEBUG: Loaded modes from Blender bridge: {modes}")
                except Exception as e:
                    self.write_message(f"⚠️ Bridge mode loading failed: {e}")
            
            # Fallback: load modes directly from render config file
            if not modes:
                try:
                    with open(RENDER_CONFIG_PATH, 'r') as f:
                        config_data = json.load(f)
                        modes = list(config_data.get("modes", {}).keys())
                        self.write_message(f"🔧 DEBUG: Loaded modes from local config: {modes}")
                except Exception as e:
                    self.write_message(f"❌ Failed to load modes from config: {e}")
            
            # Get garments and fabrics from local files (no Blender needed)
            garments = await asyncio.get_event_loop().run_in_executor(
                None, self._get_local_garments
            )
            fabrics = await asyncio.get_event_loop().run_in_executor(
                None, self._get_local_fabrics
            )
            self.available_garments = [g["file_name"] for g in garments]
            self.available_fabrics = [f["file_name"] for f in fabrics]
            self.garment_display_names = {g["file_name"]: g["display_name"] for g in garments}
            self.fabric_display_names = {f["file_name"]: f["display_name"] for f in fabrics}

            # Drop cached selections for removed garments
            self.asset_selection_by_garment = {
                garment: selections
                for garment, selections in self.asset_selection_by_garment.items()
                if garment in self.available_garments
            }
            self.view_selection_by_garment = {
                garment: selections
                for garment, selections in self.view_selection_by_garment.items()
                if garment in self.available_garments
            }

            if self.current_garment_name and self.current_garment_name not in self.available_garments:
                self.current_garment_name = None
                self.selected_garment = None
                self.selected_views = []
                self.selected_assets = []
                self.available_views = []
                self.available_assets = []
            # Debug: which directories are being used
            try:
                self.write_message(f"🔧 DEBUG: GARMENTS_DIR = {GARMENTS_DIR}")
                self.write_message(f"🔧 DEBUG: FABRICS_DIR = {FABRICS_DIR}")
            except Exception:
                pass
            
            # Update lists
            if self.mode_list:
                self.mode_list.clear_options()
                for mode in modes:
                    self.mode_list.add_option((mode, mode))
                self.write_message(f"🔧 DEBUG: Loaded modes: {modes}")
            
            if self.garment_list:
                self.garment_list.clear_options()
                for garment in garments:
                    self.garment_list.add_option((garment["display_name"], garment["file_name"]))
                
            if self.fabric_list:
                self.fabric_list.clear_options()
                for fabric in fabrics:
                    self.fabric_list.add_option((fabric["display_name"], fabric["file_name"]))
            
            await self.refresh_view_list()
            await self.refresh_assets_list()

            # Debug info about loaded data
            asset_count = len(self.available_assets)
            self.write_message(f"📋 Lists refreshed - Modes: {len(modes)}, Garments: {len(garments)}, Fabrics: {len(fabrics)}, Assets: {asset_count}")
            if asset_count:
                self.write_message(f"Available assets: {', '.join(self.available_assets)}")
            else:
                self.write_message("No assets loaded (garment must be selected first)")
            
        except Exception as e:
            self.write_message(f"❌ Failed to refresh lists: {e}")
    
    async def refresh_assets_list(self):
        """Refresh only the assets list (called after garment selection)"""
        self.write_message(f"🔍 DEBUG: refresh_assets_list called, current_garment_name: {self.current_garment_name}")
        
        if not self.asset_list:
            self.write_message("🔍 DEBUG: asset_list is None")
            return
        
        try:
            assets: List[str] = []
            if self.current_garment_name:
                if self.current_garment_name not in self.available_garments:
                    self.write_message("🔍 DEBUG: Current garment no longer available; clearing assets list")
                else:
                    self.write_message(f"🔍 DEBUG: Getting assets for garment: {self.current_garment_name}")
                    assets = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self._get_garment_assets(self.current_garment_name)
                    )
                    self.write_message(f"🔍 DEBUG: Found {len(assets)} assets: {assets}")
            
            self.asset_list.clear_options()
            for asset in assets:
                self.asset_list.add_option((asset, asset))

            if self.current_garment_name:
                cached_selection = self.asset_selection_by_garment.get(self.current_garment_name)
                if cached_selection:
                    selection = [asset for asset in cached_selection if asset in assets]
                else:
                    selection = []
                self.asset_selection_by_garment[self.current_garment_name] = selection
                self.selected_assets = list(selection)
                self._set_selection_values(self.asset_list, selection)
            else:
                self.selected_assets = []

            self.available_assets = list(assets)

            # Debug info
            if assets:
                self.write_message(f"🎯 Assets refreshed ({len(assets)} available): {', '.join(assets)}")
            else:
                self.write_message("🎯 No assets available (select a garment first)")
            
        except Exception as e:
            self.write_message(f"❌ Failed to refresh assets: {e}")
            import traceback
            self.write_message(f"🔍 DEBUG: Traceback: {traceback.format_exc()}")

    async def refresh_view_list(self):
        """Refresh the view list whenever the garment context changes."""
        if not self.view_list:
            return

        try:
            if not self.current_garment_name:
                self.view_list.clear_options()
                self.available_views = []
                self.selected_views = []
                self.write_message("👁 No garment selected - view list cleared")
                return
            if self.current_garment_name not in self.available_garments:
                self.view_list.clear_options()
                self.available_views = []
                self.selected_views = []
                self.write_message("👁 Current garment not found - view list cleared")
                return

            garment_path = GARMENTS_DIR / self.current_garment_name

            def _load_views() -> List[Dict[str, Any]]:
                data = self._load_json_file(garment_path)
                return self._extract_garment_views(data)

            views = await asyncio.get_event_loop().run_in_executor(None, _load_views)
            self.view_list.clear_options()
            codes: List[str] = []
            for view in views:
                code = view.get("code")
                if not code:
                    continue
                codes.append(code)
                self.view_list.add_option((code, code))

            self.available_views = codes

            cached_selection = self.view_selection_by_garment.get(self.current_garment_name)
            if cached_selection:
                selection = [code for code in cached_selection if code in codes]
            else:
                selection = []
            self.view_selection_by_garment[self.current_garment_name] = selection
            self.selected_views = list(selection)
            self._set_selection_values(self.view_list, selection)

            if codes:
                self.write_message(f"👁 Views available ({len(codes)}): {', '.join(codes)}")
            else:
                self.write_message("👁 Garment has no view definitions")
        except Exception as e:
            self.write_message(f"❌ Failed to refresh views: {e}")

    async def _apply_toggle_all(self, select_all: bool) -> None:
        """Select or clear all options across the major lists."""
        if select_all:
            self._set_selection_values(self.fabric_list, self.available_fabrics)
            self.selected_fabrics = list(self.available_fabrics)

            self._set_selection_values(self.garment_list, self.available_garments)
            if not self.current_garment_name and self.available_garments:
                self.current_garment_name = self.available_garments[0]
                self.selected_garment = self.current_garment_name
                await self.refresh_view_list()
                await self.refresh_assets_list()
            else:
                if not self.available_views:
                    await self.refresh_view_list()
                if not self.available_assets:
                    await self.refresh_assets_list()

            self._set_selection_values(self.view_list, self.available_views)
            self.selected_views = list(self.available_views)
            if self.current_garment_name:
                self.view_selection_by_garment[self.current_garment_name] = list(self.available_views)

            self._set_selection_values(self.asset_list, self.available_assets)
            self.selected_assets = list(self.available_assets)
            if self.current_garment_name:
                self.asset_selection_by_garment[self.current_garment_name] = list(self.available_assets)
        else:
            for widget in (self.fabric_list, self.garment_list, self.view_list, self.asset_list):
                self._set_selection_values(widget, [])
            self.selected_fabrics = []
            self.selected_assets = []
            self.selected_views = []
            self.selected_garment = None
            self.current_garment_name = None
            self.available_views = []
            self.view_selection_by_garment.clear()
            self.asset_selection_by_garment.clear()
            await self.refresh_view_list()
            await self.refresh_assets_list()

        await self.update_local_status()

    @on(SelectionList.SelectionHighlighted, "#garment_list")  # type: ignore[attr-defined]
    async def handle_garment_highlight(self, event):
        """Update preview selections as the focused garment row changes."""
        garment_value = getattr(getattr(event, "selection", None), "value", None)
        if not garment_value or garment_value == self.current_garment_name:
            return
        self.current_garment_name = garment_value
        display_name = self.garment_display_names.get(garment_value, garment_value)
        self.write_message(f"👗 Previewing garment: {display_name}")
        await self.refresh_view_list()
        await self.refresh_assets_list()
        await self.update_local_status()
    


    
    async def on_selection_list_selection_toggled(self, event):
        """Handle selection changes for all SelectionLists"""
        list_id = event.selection_list.id
        
        if list_id == "mode_list":
            if self.mode_list and self.mode_list.selected:
                selected = self.mode_list.selected
                mode = selected[0] if isinstance(selected, list) else selected
                self.selected_mode = mode
                self.write_message(f"✅ Mode selected: {mode}")
        elif list_id == "garment_list":
            if self.garment_list and self.garment_list.selected:
                selected = self.garment_list.selected
                garment = selected[0] if isinstance(selected, list) else selected
                self.current_garment_name = garment
                self.selected_garment = garment
                display_name = self.garment_display_names.get(garment, garment)
                self.write_message(f"✅ Garment selected: {display_name}")
                await self.refresh_view_list()
                await self.refresh_assets_list()
            else:
                self.selected_garment = None
                self.write_message("👔 Garment checkbox cleared")
        elif list_id == "fabric_list":
            if self.fabric_list:
                self.selected_fabrics = list(self.fabric_list.selected)
                fabric_count = len(self.selected_fabrics)
                if fabric_count == 0:
                    self.write_message("⚠️ No fabrics selected")
                elif fabric_count == 1:
                    fabric_label = self.fabric_display_names.get(self.selected_fabrics[0], self.selected_fabrics[0])
                    self.write_message(f"✅ Fabric selected: {fabric_label}")
                else:
                    self.write_message(f"✅ {fabric_count} fabrics selected")
        elif list_id == "asset_list":
            if not self.current_garment_name:
                self.write_message("❌ Please select a garment first")
                return
                
            if self.asset_list:
                self.selected_assets = list(self.asset_list.selected)
                self.asset_selection_by_garment[self.current_garment_name] = list(self.selected_assets)
                asset_count = len(self.selected_assets)
                if asset_count == 0:
                    self.write_message("⚠️ No assets selected")
                elif asset_count == 1:
                    self.write_message(f"✅ Asset selected: {self.selected_assets[0]}")
                else:
                    self.write_message(f"✅ {asset_count} assets selected: {', '.join(self.selected_assets)}")
        elif list_id == "view_list":
            if not self.current_garment_name:
                self.write_message("❌ Please select a garment first")
                return

            if self.view_list:
                self.selected_views = list(self.view_list.selected)
                self.view_selection_by_garment[self.current_garment_name] = list(self.selected_views)
                view_count = len(self.selected_views)
                if view_count == 0:
                    self.write_message("⚠️ No views selected")
                elif view_count == 1:
                    self.write_message(f"✅ View selected: {self.selected_views[0]}")
                else:
                    self.write_message(f"✅ {view_count} views selected: {', '.join(self.selected_views)}")
        
        await self.update_local_status()
    

    
    async def on_checkbox_changed(self, event):
        """Handle checkbox changes"""
        if event.checkbox is self.save_debug_checkbox:
            self.save_debug_files = event.value
            await self.update_local_status()
        elif event.checkbox is self.toggle_all_checkbox:
            await self._apply_toggle_all(event.value)
    
    async def update_local_status(self):
        """Update message log with current configuration status"""
        debug_status = "On" if self.save_debug_files else "Off"
        
        assets_for_selected = self._get_assets_for_garment(self.selected_garment)
        views_for_selected = self._get_views_for_garment(self.selected_garment)

        ready = all([
            self.selected_mode,
            self.selected_garment,
            self.selected_fabrics,
            assets_for_selected,
            views_for_selected,
        ])
        status = 'Ready to render' if ready else 'Configuration incomplete'
        
        fabric_status = f"{len(self.selected_fabrics)} selected" if self.selected_fabrics else "Not selected"
        asset_status = f"{len(assets_for_selected)} selected" if assets_for_selected else "Not selected"
        view_status = f"{len(views_for_selected)} selected" if views_for_selected else "Not selected"
        combinations = (
            len(self.selected_fabrics) * len(assets_for_selected) * len(views_for_selected)
            if self.selected_fabrics and assets_for_selected and views_for_selected else 0
        )
        combo_status = f" | 🎯 Will render {combinations} combinations" if combinations > 1 else ""
        
        garment_label = self._get_display_label(self.garment_display_names, self.selected_garment)
        self.write_message(
            f"🔧 Mode: {self.selected_mode or 'Not selected'} | 👔 Garment: {garment_label} | "
            f"🧵 Fabrics: {fabric_status} | 👁 Views: {view_status} | 🎨 Assets: {asset_status}{combo_status} | 🐞 Debug: {debug_status} | Status: {status}"
        )
    
    async def tail_log_file(self, log_file_path: str):
        """Tail the Blender log file and stream output to TUI"""
        last_position = 0
        
        while True:
            try:
                await asyncio.sleep(0.5)  # Check more frequently for smoother UI updates
                
                if Path(log_file_path).exists():
                    with open(log_file_path, 'r') as f:
                        f.seek(last_position)
                        new_content = f.read()
                        
                        if new_content:
                            # Split into lines and show each one
                            for line in new_content.split('\n'):
                                if line.strip():
                                    self.write_message(f"🔧 {line}")
                                    # Parse line for execution dashboard
                                    self.log_parser.handle_line(line)
                            
                            last_position = f.tell()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.write_message(f"❌ Error tailing log: {e}")
                break
    
    @on(Button.Pressed, "#render_btn")
    async def render(self):
        if self.is_rendering:
            return  # Already rendering
            
        self.is_rendering = True
        self.render_button.display = False
        self.cancel_button.display = True
        self.refresh()  # Force UI refresh to show button changes
        
        self.write_message("🎬 Starting render...")
        
        try:
            # Validate configuration - now returns list of combinations
            configs = self.validate_render_config()
            total_combinations = len(configs)
            
            if total_combinations == 1:
                single = configs[0]
                self.write_message(
                    f"✅ Configuration validated: {single['fabric']} × {single['asset']} @ {single['view']}"
                )
            else:
                self.write_message(f"✅ Will render {total_combinations} fabric × asset × view combinations:")
                for i, config in enumerate(configs, 1):
                    self.write_message(
                        f"  {i}. {config['fabric']} × {config['asset']} @ {config['view']}"
                    )
            
            self.write_message(f"🔧 DEBUG: Selected mode for render: '{self.selected_mode}'")
            
            # Check if bridge is available
            if not self.session:
                self.write_message("❌ Blender bridge not available - initializing...")
                # Try to initialize bridge
                try:
                    self.write_message("🔄 Starting Blender subprocess (this may take a moment)...")
                    self.session = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: BlenderTUISession(self.blender_exe)
                    )
                    self.write_message("✅ Blender bridge initialized")
                except Exception as e:
                    self.write_message(f"❌ Failed to initialize Blender: {e}")
                    self.write_message("💡 Make sure Blender is installed and accessible via 'blender' command")
                    self.write_message("💡 You can specify path with: python main.py --interface tui --blender-path /path/to/blender")
                    return
            
            # Pre-populate render state with planned assets
            import time
            self.render_state = RenderRunState(run_started_at=time.time())
            self.log_parser = BlenderLogParser(self.render_state)
            
            # Generate expected output filenames to seed the dashboard
            # Note: This logic duplicates some filename generation from render_session.py
            # Ideally we'd get this list from the bridge, but for now we approximate
            for config in configs:
                # Construct expected filename: {garment_prefix}-{fabric}-{asset_suffix}.png
                # We need to know the garment prefix, which might require loading the garment json
                # For now, we'll use a placeholder or try to load it if possible
                garment_name = config['garment']
                fabric_name = config['fabric'].replace(".json", "").lower().replace(" ", "_")
                
                asset_suffix = config.get('asset_suffix') or config['asset'].replace(" ", "_").lower()
                prefix = config.get('view_output_prefix') or "garment"
                if not config.get('view_output_prefix'):
                    try:
                        g_path = GARMENTS_DIR / garment_name
                        if g_path.exists():
                            with open(g_path) as f:
                                g_data = json.load(f)
                                prefix = g_data.get("output_prefix", "garment")
                    except:
                        pass

                # Try to get real fabric suffix from fabric file
                try:
                    f_path = FABRICS_DIR / config['fabric']
                    if f_path.exists():
                        with open(f_path) as f:
                            f_data = json.load(f)
                            if "suffix" in f_data:
                                fabric_name = f_data["suffix"]
                except:
                    pass
                    
                # Asset suffix logic from render_session
                expected_name = f"{prefix}-{fabric_name}-{asset_suffix}.png"
                
                # Add to state
                self.render_state.assets[expected_name] = AssetStatus(name=expected_name, status="pending")

            # Show execution screen
            exec_screen = ExecutionScreen(self.render_state, name="execution")
            self.push_screen(exec_screen)
            
            start_time = asyncio.get_event_loop().time()
            successful_renders = []
            failed_renders = []
            
            # For single combination, use detached rendering; for multiple, use synchronous
            if total_combinations == 1:
                # Single combination - use existing detached logic
                config = configs[0]
                self.write_message("🔧 Configuring Blender and rendering...")
                
                render_result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.session.render_with_config(config)
                )
                
                if not render_result.get('success'):
                    raise Exception(render_result.get('error', 'Unknown render error'))
                
                if render_result.get('detached'):
                    # Detached render started successfully
                    self.render_pid = render_result.get('pid')
                    self.write_message(f"🚀 Render started in background (PID: {self.render_pid})")
                    
                    # Start log tailing
                    log_file_path = render_result.get('log_file')
                    if log_file_path:
                        log_task = asyncio.create_task(self.tail_log_file(log_file_path))
                        self.current_log_task = log_task
                        self.write_message(f"📄 Streaming log from: {log_file_path}")
                    
                    # Start monitoring the render process
                    monitor_task = asyncio.create_task(self.monitor_render_process())
                    self.current_render_task = monitor_task
                    
                    # Don't wait for completion - return immediately
                    self.write_message("✅ Render started successfully! Use Cancel to stop.")
                    return
                else:
                    # Synchronous render completed
                    output_path = render_result.get('result')
                    end_time = asyncio.get_event_loop().time()
                    
                    self.write_message(f"⏱️  Render took {end_time - start_time:.1f} seconds")
                    self.write_message(f"🎉 Render completed: {output_path}")
            else:
                # Multiple combinations - use batch rendering in single Blender process
                self.write_message(f"🔧 Starting batch render of {total_combinations} fabric × asset × view combinations...")
                
                try:
                    # Start detached batch rendering
                    batch_result = self.session.render_multiple_configs(configs)
                    
                    if not batch_result.get('success', False):
                        raise Exception(batch_result.get('error', 'Unknown batch render error'))
                    
                    if batch_result.get('detached'):
                        # Detached batch render started successfully
                        self.render_pid = batch_result.get('pid')
                        self.write_message(f"🚀 Batch render started in background (PID: {self.render_pid})")
                        
                        # Start log tailing
                        log_file_path = batch_result.get('log_file')
                        if log_file_path:
                            log_task = asyncio.create_task(self.tail_log_file(log_file_path))
                            self.current_log_task = log_task
                            self.write_message(f"📄 Streaming batch render log from: {log_file_path}")
                        
                        # Start monitoring the render process
                        monitor_task = asyncio.create_task(self.monitor_render_process())
                        self.current_render_task = monitor_task
                        
                        # Don't wait for completion - return immediately
                        self.write_message("✅ Batch render started successfully! Use Cancel to stop.")
                        return
                    else:
                        # Synchronous batch render completed (fallback case)
                        self.write_message("⚠️  Batch render completed synchronously (unexpected)")
                        batch_data = batch_result.get('result', {})
                        
                        successful_renders = batch_data.get('successful_renders', [])
                        failed_renders = batch_data.get('failed_renders', [])
                        
                        # Summary for synchronous batch renders
                        end_time = asyncio.get_event_loop().time()
                        self.write_message(f"⏱️  Total render time: {end_time - start_time:.1f} seconds")
                        
                        if successful_renders:
                            self.write_message(f"🎉 {len(successful_renders)} renders completed successfully:")
                            for render in successful_renders:
                                fabric = render['fabric']
                                asset = render['asset']
                                view = render.get('view', 'default')
                                output_path = render['output_path']
                                self.write_message(f"  ✅ {fabric} × {asset} @ {view}: {output_path}")
                        
                        if failed_renders:
                            self.write_message(f"❌ {len(failed_renders)} renders failed:")
                            for render in failed_renders:
                                fabric = render['fabric']
                                asset = render['asset']
                                view = render.get('view', 'default')
                                error = render['error']
                                self.write_message(f"  ❌ {fabric} × {asset} @ {view}: {error}")
                        
                        if not successful_renders and not failed_renders:
                            self.write_message("🛑 No renders completed")
                        
                except Exception as e:
                    self.write_message(f"❌ Batch render failed: {e}")
                finally:
                    # Clean up for synchronous batch rendering
                    pass
            
            self.write_message("📄 Log file preserved for debugging")
            
        except ValueError as e:
            self.write_message(f"❌ Configuration error: {e}")
        except Exception as e:
            self.write_message(f"❌ Render failed: {e}")
        finally:
            # Reset render state
            self.is_rendering = False
            self.render_button.display = True
            self.cancel_button.display = False
            self.current_render_task = None
            self.current_log_task = None
            self.render_pid = None
            self.refresh()  # Force UI refresh to show button changes
    
    async def monitor_render_process(self):
        """Monitor the detached render process and update status"""
        if not self.session or not self.render_pid:
            return
        
        try:
            while True:
                # Check render status
                status = await asyncio.get_event_loop().run_in_executor(
                    None, self.session.check_render_status
                )
                
                if not status.get('running', False):
                    # Render finished
                    exit_code = status.get('exit_code', 0)
                    if exit_code == 0:
                        self.write_message("🎉 Render completed successfully!")
                        # Mark run as finished in state
                        if hasattr(self, 'render_state'):
                            self.render_state.mark_finished()
                    else:
                        self.write_message(f"❌ Render failed with exit code: {exit_code}")
                        # Mark remaining assets as error in dashboard
                        if hasattr(self, 'log_parser'):
                            self.log_parser.mark_all_pending_as_error()
                        # Also mark finished so timer stops
                        if hasattr(self, 'render_state'):
                            self.render_state.mark_finished()
                    
                    # Reset render state
                    self.is_rendering = False
                    self.render_button.display = True
                    self.cancel_button.display = False
                    self.current_render_task = None
                    self.render_pid = None
                    self.refresh()
                    break
                
                # Still running, wait before checking again
                await asyncio.sleep(10)  # Check every 10 seconds
                
        except asyncio.CancelledError:
            # Task was cancelled (user clicked cancel)
            pass
        except Exception as e:
            self.write_message(f"⚠️ Error monitoring render: {e}")
    
    @on(Button.Pressed, "#cancel_btn")
    async def cancel_render(self):
        if not self.is_rendering:
            return
            
        self.write_message("❌ Cancelling render...")
        
        try:
            # Cancel detached render process
            if self.session and self.render_pid:
                cancel_result = await asyncio.get_event_loop().run_in_executor(
                    None, self.session.cancel_render
                )
                if cancel_result.get('success'):
                    self.write_message(f"✅ {cancel_result.get('result', 'Render cancelled')}")
                else:
                    self.write_message(f"⚠️ Cancellation issue: {cancel_result.get('error', 'Unknown error')}")
            
            # Cancel monitoring and log tasks
            if self.current_render_task:
                self.current_render_task.cancel()
                try:
                    await asyncio.wait_for(self.current_render_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            if self.current_log_task:
                self.current_log_task.cancel()
                try:
                    await asyncio.wait_for(self.current_log_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Mark remaining assets as error in dashboard
            if hasattr(self, 'log_parser'):
                self.log_parser.mark_all_pending_as_error()
            
            # Mark run as finished
            if hasattr(self, 'render_state'):
                self.render_state.mark_finished()
                    
        except Exception as e:
            self.write_message(f"⚠️ Error during cancellation: {e}")
        
        # Reset state
        self.is_rendering = False
        self.render_button.display = True
        self.cancel_button.display = False
        self.current_render_task = None
        self.current_log_task = None
        self.render_pid = None
        self.refresh()  # Force UI refresh to show button changes
        
        self.write_message("🛑 Render cancelled")
    
    async def on_unmount(self):
        """Clean up when app closes"""
        self.write_message("🔄 Cleaning up...")
        
        # Cancel any active render monitoring
        if self.current_render_task:
            self.current_render_task.cancel()
        
        if self.current_log_task:
            self.current_log_task.cancel()
        
        # Note: We don't kill the render process here since it should continue
        # running independently. Use cleanup_renders.py to manage orphans.
        if self.render_pid:
            self.write_message(f"📋 Render PID {self.render_pid} will continue in background")
            self.write_message("💡 Use cleanup_renders.py to manage background renders")
        
        if self.session:
            # Clean up bridge resources but don't kill render process
            try:
                # Temporarily remove render process so cleanup() doesn't kill it
                if hasattr(self.session.bridge, 'render_process'):
                    temp_process = self.session.bridge.render_process
                    self.session.bridge.render_process = None
                    self.session.cleanup()
                    self.session.bridge.render_process = temp_process
                else:
                    self.session.cleanup()
            except Exception as e:
                self.write_message(f"⚠️ Cleanup warning: {e}")


def main():
    """Entry point for Blender TUI"""
    if not TEXTUAL_AVAILABLE:
        print("❌ Textual not available. Install with: pip install textual")
        print("💡 Or use the shell interface: python main.py --interface shell")
        sys.exit(1)
    
    print("🎨 BLENDER TUI - Bridge Mode")
    print("=" * 50)
    print("This TUI runs OUTSIDE Blender and communicates via subprocess.")
    print("Make sure Blender is installed and accessible via 'blender' command.")
    print("=" * 50)
    
    # Find Blender executable
    import subprocess
    try:
        result = subprocess.run(["blender", "--version"], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            raise Exception("Blender not found")
        print("✅ Blender found")
    except:
        print("❌ Blender not found in PATH")
        print("💡 Install Blender or add it to your PATH")
        blender_path = input("Enter Blender executable path (or press Enter to try anyway): ").strip()
        if not blender_path:
            blender_path = "blender"
    else:
        blender_path = "blender"
    
    # Add signal handler for graceful shutdown
    def signal_handler(signum, frame):
        print("\n🛑 Interrupt received, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the app with proper error handling
    try:
        app = BlenderTUIApp(blender_path)
        app.run()
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TUI error: {e}")
        print("This may happen due to terminal compatibility issues.")
        print("💡 Try the shell interface: python main.py --interface shell")
        sys.exit(1)


if __name__ == "__main__":
    main()