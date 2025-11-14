"""
Simplified Textual TUI for Blender Render Automation
Fixed version that avoids compatibility issues
"""
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Static, Button, Log, ListView, ListItem, Label
from textual.screen import Screen
from textual import on
import asyncio

try:
    from render_session import RenderSession
except ImportError:
    try:
        from demo_session import RenderSession
        print("Info: Using demo session for TUI (Blender not available)")
    except ImportError:
        RenderSession = None


class SimpleRenderScreen(Screen):
    """Simplified render interface screen"""
    
    CSS = """
    .panel {
        border: solid white;
        margin: 1;
        padding: 1;
    }
    
    #status {
        dock: left;
        width: 30%;
    }
    
    #controls {
        dock: right; 
        width: 35%;
    }
    
    #log {
        dock: bottom;
        height: 30%;
    }
    
    Button {
        margin: 1 0;
        width: 100%;
    }
    
    .success {
        background: $success;
    }
    
    .warning {
        background: $warning;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.session = None
        self.current_mode = 0
        self.current_garment = 0
        self.current_fabric = 0
        self.current_asset = 0
        
        # Initialize session
        try:
            if RenderSession:
                self.session = RenderSession()
                print("[TUI] Session initialized successfully")
            else:
                print("[TUI] Warning: Running without session")
        except Exception as e:
            print(f"[TUI] Error initializing session: {e}")
    
    def compose(self) -> ComposeResult:
        """Build the interface layout"""
        yield Header(show_clock=True)
        
        # Status panel
        with Container(id="status", classes="panel"):
            yield Static("[bold]Status[/]")
            yield Static("Mode: None", id="status_mode")
            yield Static("Garment: None", id="status_garment") 
            yield Static("Fabric: None", id="status_fabric")
            yield Static("Asset: None", id="status_asset")
            yield Static("Ready: ❌", id="status_ready")
        
        # Main content area
        with Container():
            # Controls panel
            with Container(id="controls", classes="panel"):
                yield Static("[bold]Controls[/]")
                
                # Mode selection
                yield Static("1. Select Mode:")
                yield Button("Next Mode", id="next_mode")
                yield Static("", id="current_mode")
                
                # Garment selection  
                yield Static("2. Select Garment:")
                yield Button("Next Garment", id="next_garment")
                yield Static("", id="current_garment")
                
                # Fabric selection
                yield Static("3. Select Fabric:")
                yield Button("Next Fabric", id="next_fabric") 
                yield Static("", id="current_fabric")
                
                # Asset selection
                yield Static("4. Select Asset:")
                yield Button("Next Asset", id="next_asset")
                yield Static("", id="current_asset")
                
                # Render button
                yield Button("🎬 RENDER", id="render", classes="success")
                yield Button("Reset", id="reset", classes="warning")
            
            # Log panel
            with Container(id="log", classes="panel"):
                yield Static("[bold]Log[/]")
                yield Log(auto_scroll=True, id="log_content")
        
        yield Footer()
    
    def on_mount(self):
        """Called when screen is mounted"""
        self.update_display()
        self.log("Blendomatic TUI started")
        if self.session:
            self.log("Session ready - use buttons to make selections")
        else:
            self.log("No session available - running in demo mode")
    
    def log(self, message: str):
        """Add message to log"""
        log_widget = self.query_one("#log_content", Log)
        log_widget.write_line(message)
    
    def update_display(self):
        """Update all display elements"""
        if not self.session:
            return
            
        # Update current selections display
        modes = self.session.list_modes()
        if modes:
            mode_text = modes[self.current_mode % len(modes)]
            self.query_one("#current_mode", Static).update(f"→ {mode_text}")
        
        garments = self.session.list_garments()  
        if garments:
            garment_text = garments[self.current_garment % len(garments)]
            self.query_one("#current_garment", Static).update(f"→ {garment_text}")
        
        fabrics = self.session.list_fabrics()
        if fabrics:
            fabric_text = fabrics[self.current_fabric % len(fabrics)] 
            self.query_one("#current_fabric", Static).update(f"→ {fabric_text}")
        
        assets = self.session.list_assets()
        if assets:
            asset_text = assets[self.current_asset % len(assets)]
            self.query_one("#current_asset", Static).update(f"→ {asset_text}")
        
        # Update status panel
        state = self.session.get_state()
        self.query_one("#status_mode", Static).update(f"Mode: {state.get('mode', 'None')}")
        self.query_one("#status_garment", Static).update(f"Garment: {state.get('garment_name', 'None')}")
        self.query_one("#status_fabric", Static).update(f"Fabric: {state.get('fabric_name', 'None')}")
        self.query_one("#status_asset", Static).update(f"Asset: {state.get('asset_name', 'None')}")
        
        ready_icon = "✅" if state.get('ready_to_render') else "❌"
        self.query_one("#status_ready", Static).update(f"Ready: {ready_icon}")
    
    @on(Button.Pressed, "#next_mode")
    def next_mode(self):
        """Cycle to next mode and apply it"""
        if not self.session:
            return
            
        modes = self.session.list_modes()
        if modes:
            self.current_mode = (self.current_mode + 1) % len(modes)
            selected_mode = modes[self.current_mode]
            
            try:
                self.session.set_mode(selected_mode)
                self.log(f"Set mode: {selected_mode}")
                self.update_display()
            except Exception as e:
                self.log(f"Error setting mode: {e}")
    
    @on(Button.Pressed, "#next_garment") 
    def next_garment(self):
        """Cycle to next garment and apply it"""
        if not self.session:
            return
            
        garments = self.session.list_garments()
        if garments:
            self.current_garment = (self.current_garment + 1) % len(garments)
            selected_garment = garments[self.current_garment]
            
            try:
                self.log(f"Loading garment: {selected_garment}...")
                self.session.set_garment(selected_garment)
                self.log(f"Set garment: {selected_garment}")
                # Reset asset selection since garment changed
                self.current_asset = 0
                self.update_display()
            except Exception as e:
                self.log(f"Error setting garment: {e}")
    
    @on(Button.Pressed, "#next_fabric")
    def next_fabric(self):
        """Cycle to next fabric and apply it"""
        if not self.session:
            return
            
        fabrics = self.session.list_fabrics()
        if fabrics:
            self.current_fabric = (self.current_fabric + 1) % len(fabrics)
            selected_fabric = fabrics[self.current_fabric]
            
            try:
                self.session.set_fabric(selected_fabric)
                self.log(f"Set fabric: {selected_fabric}")
                self.update_display()
            except Exception as e:
                self.log(f"Error setting fabric: {e}")
    
    @on(Button.Pressed, "#next_asset")
    def next_asset(self):
        """Cycle to next asset and apply it"""
        if not self.session:
            return
            
        assets = self.session.list_assets()
        if assets:
            self.current_asset = (self.current_asset + 1) % len(assets)
            selected_asset = assets[self.current_asset]
            
            try:
                self.session.set_asset(selected_asset)
                self.log(f"Set asset: {selected_asset}")
                self.update_display()
            except Exception as e:
                self.log(f"Error setting asset: {e}")
    
    @on(Button.Pressed, "#render")
    async def render(self):
        """Start render"""
        if not self.session:
            self.log("No session available")
            return
            
        if not self.session.is_ready_to_render():
            self.log("Cannot render: Missing required selections")
            return
            
        try:
            self.log("🎬 Starting render...")
            # Run render in executor to avoid blocking UI
            loop = asyncio.get_event_loop()
            output_path = await loop.run_in_executor(None, self.session.render)
            self.log(f"✅ Render completed: {output_path}")
        except Exception as e:
            self.log(f"❌ Render failed: {e}")
    
    @on(Button.Pressed, "#reset")
    def reset(self):
        """Reset all selections"""
        if not self.session:
            return
            
        try:
            # Reinitialize session
            self.session.__init__()
            self.current_mode = 0
            self.current_garment = 0
            self.current_fabric = 0
            self.current_asset = 0
            self.update_display()
            self.log("🔄 Reset completed")
        except Exception as e:
            self.log(f"Error during reset: {e}")


class SimpleTUIApp(App):
    """Simplified Textual application"""
    
    TITLE = "Blendomatic - Simple TUI"
    
    def on_mount(self):
        """Initialize the app"""
        self.push_screen(SimpleRenderScreen())


def main():
    """Entry point for the simplified TUI"""
    print("🎨 Starting Blendomatic Simple TUI...")
    app = SimpleTUIApp()
    try:
        app.run()
    except Exception as e:
        print(f"Error running TUI: {e}")
        print("Try using the shell interface instead: python main.py --interface shell")


if __name__ == "__main__":
    main()