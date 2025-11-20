"""
Textual TUI for Blender Render Automation
Beautiful, interactive interface using the Textual framework
"""
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header, Footer, Static, Button, SelectionList, 
    Label, Log
)
from textual.screen import Screen
from textual import on
import asyncio
from typing import Optional
import json, time, threading, queue, traceback
from pathlib import Path

try:
    from render_session import RenderSession
except ImportError:
    try:
        from demo_session import RenderSession
        print("Info: Using demo session for TUI (Blender not available)")
    except ImportError:
        # Fallback for when running outside Blender
        RenderSession = None

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    USE_WATCHDOG = True
except ImportError:
    USE_WATCHDOG = False

WATCH_DIRS = [Path("fabrics"), Path("garments")]
DEBOUNCE_MS = 300

class _ChangeEvent:
    def __init__(self, path: Path):
        self.path = path
        self.ts = time.time()

class JsonWatcher:
    def __init__(self, on_reload, on_error):
        self.on_reload = on_reload
        self.on_error = on_error
        self.q = queue.Queue()
        self.stop_flag = threading.Event()
        self.last_processed: dict[Path,float] = {}
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        for d in WATCH_DIRS:
            d.mkdir(exist_ok=True)
        if USE_WATCHDOG:
            self._start_watchdog()
        else:
            self._start_poll()
        self.thread.start()
        print("[WATCH] Started JSON watch")

    def stop(self):
        self.stop_flag.set()
        print("[WATCH] Stopping JSON watch")

    def _start_watchdog(self):
        class Handler(FileSystemEventHandler):
            def on_modified(_, event):
                if not event.is_directory and event.src_path.endswith(".json"):
                    self.q.put(_ChangeEvent(Path(event.src_path)))
            def on_created(_, event):
                if not event.is_directory and event.src_path.endswith(".json"):
                    self.q.put(_ChangeEvent(Path(event.src_path)))
            def on_deleted(_, event):
                if not event.is_directory and event.src_path.endswith(".json"):
                    self.q.put(_ChangeEvent(Path(event.src_path)))
        self.observer = Observer()
        h = Handler()
        for d in WATCH_DIRS:
            self.observer.schedule(h, str(d), recursive=False)
        self.observer.start()

    def _start_poll(self):
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _poll_loop(self):
        mtimes: dict[Path,float] = {}
        while not self.stop_flag.is_set():
            for d in WATCH_DIRS:
                for p in d.glob("*.json"):
                    m = p.stat().st_mtime
                    if mtimes.get(p) != m:
                        mtimes[p] = m
                        self.q.put(_ChangeEvent(p))
            time.sleep(1.0)

    def _loop(self):
        pending: dict[Path,_ChangeEvent] = {}
        while not self.stop_flag.is_set():
            try:
                evt = self.q.get(timeout=0.2)
                pending[evt.path] = evt
            except queue.Empty:
                pass
            now = time.time()
            to_process = [p for p,e in pending.items() if (now - e.ts)*1000 >= DEBOUNCE_MS]
            for p in to_process:
                del pending[p]
                self._process(p)

    def _process(self, path: Path):
        if not path.exists():
            # deletion: trigger reload of listing
            self.on_reload(None, deleted=path)
            return
        try:
            raw = path.read_text()
            data = json.loads(raw)
            self.on_reload(data, file=path)
        except Exception as e:
            err = "".join(traceback.format_exception_only(type(e), e)).strip()
            detail = traceback.format_exc()
            self.on_error(path, err, detail)

# ---- Integration points in TUI application ----
# Assume TUI class name App; adjust as needed.

class StatusPanel(Static):
    """Widget showing current render session status"""
    
    def __init__(self, session: Optional[RenderSession] = None):
        super().__init__()
        self.session = session
        
    def update_status(self, state: dict):
        """Update the status display with current state"""
        if not state:
            self.update("No session loaded")
            return
            
        status_lines = [
            f"Mode: {state.get('mode', 'Not set')}",
            f"Garment: {state.get('garment_name', 'Not set')}",
            f"Fabric: {state.get('fabric_name', 'Not set')}",
            f"Asset: {state.get('asset_name', 'Not set')}",
        ]
        
        # Add status indicators
        ready = "🟢" if state.get('ready_to_render') else "🔴"
        garment_loaded = "✅" if state.get('garment_loaded') else "❌"
        fabric_applied = "✅" if state.get('fabric_applied') else "❌"
        
        status_lines.extend([
            "",
            f"Ready to Render: {ready}",
            f"Garment Loaded: {garment_loaded}",
            f"Fabric Applied: {fabric_applied}"
        ])
        
        self.update("\n".join(status_lines))


class SelectionPanel(Container):
    """Panel for making selections (modes, garments, fabrics, assets)"""
    
    def __init__(self, title: str, items: list, session=None):
        super().__init__()
        self.title = title
        self.items = items
        self.session = session
        self.selection_list = None
    
    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self.title}[/]", classes="panel_title")
        self.selection_list = SelectionList(*self.items)
        yield self.selection_list
        yield Button(f"Set {self.title}", id=f"set_{self.title.lower()}")
    
    def get_selected(self):
        """Get currently selected item"""
        if self.selection_list and hasattr(self.selection_list, 'highlighted'):
            try:
                return self.items[self.selection_list.highlighted] if self.selection_list.highlighted is not None else None
            except (IndexError, AttributeError):
                pass
        return None


class LogPanel(Log):
    """Enhanced log panel for render output"""
    
    def __init__(self):
        super().__init__(auto_scroll=True, max_lines=1000)
        
    def log_info(self, message: str):
        """Log info message with formatting"""
        self.write_line(f"[bold green][INFO][/] {message}")
        
    def log_warning(self, message: str):
        """Log warning message with formatting"""
        self.write_line(f"[bold yellow][WARN][/] {message}")
        
    def log_error(self, message: str):
        """Log error message with formatting"""
        self.write_line(f"[bold red][ERROR][/] {message}")
        
    def log_render(self, message: str):
        """Log render message with special formatting"""
        self.write_line(f"[bold blue][RENDER][/] {message}")


class RenderScreen(Screen):
    """Main render interface screen"""
    
    CSS = """
    #status_panel {
        dock: left;
        width: 30%;
        border: solid white;
        margin: 1;
        padding: 1;
    }
    
    #controls_panel {
        dock: right;
        width: 35%;
        margin: 1;
        padding: 1;
    }
    
    #log_panel {
        dock: bottom;
        height: 30%;
        border: solid white;
        margin: 1;
        padding: 1;
    }
    
    SelectionList {
        height: 6;
        border: solid gray;
        margin: 0 0 1 0;
    }
    
    Button {
        margin: 0 0 1 0;
        width: 100%;
    }
    
    .render_button {
        background: $success;
    }
    
    .disabled_button {
        background: $error;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.session = None
        self.status_panel = None
        self.mode_panel = None
        self.garment_panel = None
        self.fabric_panel = None
        self.asset_panel = None
        self.log_panel = None
        
        # Initialize session
        try:
            if RenderSession:
                self.session = RenderSession()
                self.log("Session initialized successfully")
            else:
                self.log("Warning: Running in demo mode (Blender not available)")
        except Exception as e:
            self.log(f"Error initializing session: {e}")
    
    def compose(self) -> ComposeResult:
        """Build the interface layout"""
        yield Header(show_clock=True)
        
        with Container():
            # Status panel (left)
            with Container(id="status_panel"):
                yield Static("Render Status", classes="panel_title")
                self.status_panel = StatusPanel(self.session)
                yield self.status_panel
            
            # Main content (center)
            with Container():
                # Selection panels (right)
                with Container(id="controls_panel"):
                    if self.session:
                        self.mode_panel = SelectionPanel("Mode", self.session.list_modes(), self.session)
                        self.garment_panel = SelectionPanel("Garment", self.session.list_garments(), self.session)
                        self.fabric_panel = SelectionPanel("Fabric", self.session.list_fabrics(), self.session)
                        self.asset_panel = SelectionPanel("Asset", [], self.session)  # Populated after garment selection
                        
                        yield self.mode_panel
                        yield self.garment_panel
                        yield self.fabric_panel
                        yield self.asset_panel
                    else:
                        yield Static("Demo Mode - Blender session not available")
                    
                    yield Button("🎬 RENDER", id="render_button", classes="render_button")
                    yield Button("🔄 Refresh", id="refresh_button")
                
                # Log panel (bottom)
                with Container(id="log_panel"):
                    yield Static("Render Log", classes="panel_title")
                    self.log_panel = LogPanel()
                    yield self.log_panel
        
        yield Footer()
    
    def on_mount(self):
        """Called when screen is mounted"""
        self.update_status()
        if self.log_panel:
            self.log_panel.log_info("Blendomatic TUI started")
    
    def log(self, message: str):
        """Log a message to both the log panel and console"""
        print(message)  # Console logging
        if self.log_panel:
            if "ERROR" in message.upper():
                self.log_panel.log_error(message)
            elif "WARN" in message.upper():
                self.log_panel.log_warning(message)
            elif "RENDER" in message.upper():
                self.log_panel.log_render(message)
            else:
                self.log_panel.log_info(message)
    
    def update_status(self):
        """Update the status panel with current session state"""
        if self.session and self.status_panel:
            state = self.session.get_state()
            self.status_panel.update_status(state)
    
    @on(Button.Pressed, "#set_mode")
    async def set_mode(self):
        """Handle mode selection"""
        if not self.session or not self.mode_panel:
            return
            
        selected = self.mode_panel.get_selected()
        if selected:
            try:
                self.session.set_mode(selected)
                self.log(f"Set mode: {selected}")
                self.update_status()
            except Exception as e:
                self.log(f"Error setting mode: {e}")
    
    @on(Button.Pressed, "#set_garment")
    async def set_garment(self):
        """Handle garment selection"""
        if not self.session or not self.garment_panel:
            return
            
        selected = self.garment_panel.get_selected()
        if selected:
            try:
                # Show loading message while loading blend file
                self.log("Loading garment blend file... (this may take a moment)")
                self.session.set_garment(selected)
                
                self.log(f"Set garment: {selected}")
                
                # Update asset list after garment is loaded
                if self.asset_panel and self.asset_panel.selection_list:
                    assets = self.session.list_assets()
                    # Update the items list for the selection panel
                    self.asset_panel.items = assets
                    # Create new selection list with updated items
                    new_selection = SelectionList(*assets)
                    # Replace the old selection list (simplified approach)
                    self.asset_panel.selection_list = new_selection
                
                self.update_status()
            except Exception as e:
                self.log(f"Error setting garment: {e}")
    
    @on(Button.Pressed, "#set_fabric")
    async def set_fabric(self):
        """Handle fabric selection"""
        if not self.session or not self.fabric_panel:
            return
            
        selected = self.fabric_panel.get_selected()
        if selected:
            try:
                self.session.set_fabric(selected)
                self.log(f"Set fabric: {selected}")
                self.update_status()
            except Exception as e:
                self.log(f"Error setting fabric: {e}")
    
    @on(Button.Pressed, "#set_asset")
    async def set_asset(self):
        """Handle asset selection"""
        if not self.session or not self.asset_panel:
            return
            
        selected = self.asset_panel.get_selected()
        if selected:
            try:
                self.session.set_asset(selected)
                self.log(f"Set asset: {selected}")
                self.update_status()
            except Exception as e:
                self.log(f"Error setting asset: {e}")
    
    @on(Button.Pressed, "#render_button")
    async def start_render(self):
        """Handle render button press"""
        if not self.session:
            self.log("No session available")
            return
        
        if not self.session.is_ready_to_render():
            self.log("Cannot render: Missing required selections")
            return
        
        try:
            self.log("Starting render...")
            # Run render in a separate thread to avoid blocking UI
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, self.session.render
            )
            self.log(f"Render completed: {output_path}")
        except Exception as e:
            self.log(f"Render failed: {e}")
    
    @on(Button.Pressed, "#refresh_button")
    async def refresh(self):
        """Refresh all data"""
        if not self.session:
            return
            
        try:
            # Reload configuration
            self.session.__init__()  # Reinitialize
            
            # Update all panels
            if self.mode_panel and self.mode_panel.selection_list:
                modes = self.session.list_modes()
                self.mode_panel.selection_list.clear_options()
                for mode in modes:
                    self.mode_panel.selection_list.add_option(mode)
            
            if self.garment_panel and self.garment_panel.selection_list:
                garments = self.session.list_garments()
                self.garment_panel.selection_list.clear_options()
                for garment in garments:
                    self.garment_panel.selection_list.add_option(garment)
            
            if self.fabric_panel and self.fabric_panel.selection_list:
                fabrics = self.session.list_fabrics()
                self.fabric_panel.selection_list.clear_options()
                for fabric in fabrics:
                    self.fabric_panel.selection_list.add_option(fabric)
            
            self.update_status()
            self.log("Refreshed configuration")
            
        except Exception as e:
            self.log(f"Error refreshing: {e}")
    
    def _init_watcher(self):
        def on_reload(data, file=None, deleted=None):
            if file:
                print(f"[WATCH] Reloaded {file}")
            if deleted:
                print(f"[WATCH] Deleted {deleted}")
            self._refresh_json_cache()
            self._refresh_lists()

        def on_error(path, err, detail):
            print(f"[WATCH] Parse error in {path}: {err}")
            self.show_json_error_modal(path, err, detail)

        self.json_watcher = JsonWatcher(on_reload, on_error)
        self.json_watcher.start()

    def show_json_error_modal(self, path: Path, err: str, detail: str):
        # Replace with real modal implementation for your TUI framework
        print(f"[MODAL][JSON ERROR] {path.name}\n{err}")

    def _refresh_json_cache(self):
        # Re-scan directories and rebuild internal representation
        self.fabrics = self._load_dir_json(Path("fabrics"))
        self.garments = self._load_dir_json(Path("garments"))

    def _load_dir_json(self, d: Path):
        out = {}
        for f in d.glob("*.json"):
            try:
                out[f.name] = json.loads(f.read_text())
            except Exception as e:
                self.show_json_error_modal(f, str(e), "")
        return out

    def _refresh_lists(self):
        # Update TUI list widgets from self.fabrics/self.garments
        pass

    def on_exit(self):
        if hasattr(self, "json_watcher"):
            self.json_watcher.stop()


class BlendomaticApp(App):
    """Main Textual application"""
    
    TITLE = "Blendomatic - Blender Render Automation"
    
    def on_mount(self):
        """Initialize the app"""
        self.push_screen(RenderScreen())


def main():
    """Entry point for the TUI application"""
    app = BlendomaticApp()
    app.run()


if __name__ == "__main__":
    main()