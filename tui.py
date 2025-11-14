"""
Textual TUI for Blender Render Automation
Beautiful, interactive interface using the Textual framework
"""
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header, Footer, Static, Button, SelectionList, 
    Label, DataTable, Collapsible, Log, LoadingIndicator
)
from textual.screen import Screen
from textual.reactive import reactive
from textual.message import Message
from textual import on
from rich.text import Text
from rich.panel import Panel
import asyncio
from typing import Optional

try:
    from render_session import RenderSession
except ImportError:
    # Fallback for when running outside Blender
    RenderSession = None


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
    
    def __init__(self, title: str, items: list, session: Optional[RenderSession] = None):
        super().__init__()
        self.title = title
        self.items = items
        self.session = session
        self.selection_list: Optional[SelectionList] = None
    
    def compose(self) -> ComposeResult:
        with Collapsible(title=self.title, collapsed=False):
            self.selection_list = SelectionList(*self.items)
            yield self.selection_list
            yield Button(f"Set {self.title}", id=f"set_{self.title.lower()}")
    
    def get_selected(self) -> Optional[str]:
        """Get currently selected item"""
        if self.selection_list and self.selection_list.selected:
            return str(self.selection_list.selected)
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
        self.session: Optional[RenderSession] = None
        self.status_panel: Optional[StatusPanel] = None
        self.mode_panel: Optional[SelectionPanel] = None
        self.garment_panel: Optional[SelectionPanel] = None
        self.fabric_panel: Optional[SelectionPanel] = None
        self.asset_panel: Optional[SelectionPanel] = None
        self.log_panel: Optional[LogPanel] = None
        
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
                # Show loading indicator while loading blend file
                with LoadingIndicator():
                    self.session.set_garment(selected)
                
                self.log(f"Set garment: {selected}")
                
                # Update asset list after garment is loaded
                if self.asset_panel and self.asset_panel.selection_list:
                    assets = self.session.list_assets()
                    self.asset_panel.selection_list.clear_options()
                    for asset in assets:
                        self.asset_panel.selection_list.add_option(asset)
                
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