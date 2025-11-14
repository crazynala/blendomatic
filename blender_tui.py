"""
Blender TUI using Bridge Architecture
Runs TUI outside Blender and communicates via subprocess
"""
try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Header, Footer, Static, Button, SelectionList, Label, Log
    from textual.screen import Screen
    from textual import on
    import asyncio
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from blender_tui_bridge import BlenderTUISession
import sys
from typing import Optional

class BlenderTUIApp(App):
    """
    Textual TUI that communicates with Blender via bridge
    """
    
    CSS = """
    .status_panel {
        dock: left;
        width: 30%;
        border: solid white;
        margin: 1;
        padding: 1;
    }
    
    .controls_panel {
        dock: right;
        width: 35%;
        margin: 1;
        padding: 1;
    }
    
    .log_panel {
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
    """
    
    def __init__(self, blender_executable="blender"):
        super().__init__()
        self.title = "Blendomatic - Blender TUI"
        self.session: Optional[BlenderTUISession] = None
        self.blender_exe = blender_executable
        
        # UI components
        self.status_display: Optional[Static] = None
        self.log_display: Optional[Log] = None
        self.mode_list: Optional[SelectionList] = None
        self.garment_list: Optional[SelectionList] = None
        self.fabric_list: Optional[SelectionList] = None
        self.asset_list: Optional[SelectionList] = None
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container():
            # Status panel
            with Container(classes="status_panel"):
                yield Static("Blender Status", id="status_title")
                self.status_display = Static("Initializing...", id="status_content")
                yield self.status_display
            
            # Controls panel
            with Container(classes="controls_panel"):
                yield Static("Mode", id="mode_title")
                self.mode_list = SelectionList(id="mode_list")
                yield self.mode_list
                yield Button("Set Mode", id="set_mode_btn")
                
                yield Static("Garment", id="garment_title")  
                self.garment_list = SelectionList(id="garment_list")
                yield self.garment_list
                yield Button("Set Garment", id="set_garment_btn")
                
                yield Static("Fabric", id="fabric_title")
                self.fabric_list = SelectionList(id="fabric_list")
                yield self.fabric_list
                yield Button("Set Fabric", id="set_fabric_btn")
                
                yield Static("Asset", id="asset_title")
                self.asset_list = SelectionList(id="asset_list")
                yield self.asset_list
                yield Button("Set Asset", id="set_asset_btn")
                
                yield Button("🎬 RENDER", id="render_btn", variant="success")
            
            # Log panel
            with Container(classes="log_panel"):
                yield Static("Blender Log", id="log_title")
                self.log_display = Log(auto_scroll=True)
                yield self.log_display
        
        yield Footer()
    
    async def on_mount(self):
        """Initialize the session when app starts"""
        self.log("🚀 Initializing Blender TUI Bridge...")
        
        try:
            # Initialize session in a separate thread to avoid blocking
            self.session = await asyncio.get_event_loop().run_in_executor(
                None, lambda: BlenderTUISession(self.blender_exe)
            )
            
            self.log("✅ Bridge initialized successfully")
            await self.refresh_all_lists()
            await self.update_status()
            
        except Exception as e:
            self.log(f"❌ Failed to initialize bridge: {e}")
            self.status_display.update(f"Error: {e}")
    
    def log(self, message: str):
        """Add message to log"""
        if self.log_display:
            self.log_display.write_line(message)
        print(message)  # Also print to console
    
    async def refresh_all_lists(self):
        """Refresh all selection lists"""
        if not self.session:
            return
        
        try:
            # Get data from Blender
            modes = await asyncio.get_event_loop().run_in_executor(
                None, self.session.list_modes
            )
            garments = await asyncio.get_event_loop().run_in_executor(
                None, self.session.list_garments  
            )
            fabrics = await asyncio.get_event_loop().run_in_executor(
                None, self.session.list_fabrics
            )
            assets = await asyncio.get_event_loop().run_in_executor(
                None, self.session.list_assets
            )
            
            # Update lists
            self.mode_list.clear_options()
            for mode in modes:
                self.mode_list.add_option(mode)
            
            self.garment_list.clear_options()
            for garment in garments:
                self.garment_list.add_option(garment)
                
            self.fabric_list.clear_options()
            for fabric in fabrics:
                self.fabric_list.add_option(fabric)
                
            self.asset_list.clear_options()
            for asset in assets:
                self.asset_list.add_option(asset)
            
            self.log("📋 Lists refreshed")
            
        except Exception as e:
            self.log(f"❌ Failed to refresh lists: {e}")
    
    async def update_status(self):
        """Update status display"""
        if not self.session or not self.status_display:
            return
        
        try:
            state = await asyncio.get_event_loop().run_in_executor(
                None, self.session.get_state
            )
            
            status_text = f"""Mode: {state.get('mode', 'Not set')}
Garment: {state.get('garment_name', 'Not set')}  
Fabric: {state.get('fabric_name', 'Not set')}
Asset: {state.get('asset_name', 'Not set')}

Ready: {'✅' if state.get('ready_to_render') else '❌'}
Garment Loaded: {'✅' if state.get('garment_loaded') else '❌'}
Fabric Applied: {'✅' if state.get('fabric_applied') else '❌'}"""
            
            self.status_display.update(status_text)
            
        except Exception as e:
            self.log(f"❌ Failed to update status: {e}")
    
    @on(Button.Pressed, "#set_mode_btn")
    async def set_mode(self):
        if not self.session or not self.mode_list.selected:
            return
        
        mode = str(self.mode_list.selected)
        self.log(f"🔧 Setting mode: {mode}")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.set_mode(mode)
            )
            self.log(f"✅ Mode set: {mode}")
            await self.update_status()
        except Exception as e:
            self.log(f"❌ Failed to set mode: {e}")
    
    @on(Button.Pressed, "#set_garment_btn")  
    async def set_garment(self):
        if not self.session or not self.garment_list.selected:
            return
        
        garment = str(self.garment_list.selected)
        self.log(f"👔 Setting garment: {garment}")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.set_garment(garment)
            )
            self.log(f"✅ Garment set: {garment}")
            await self.refresh_all_lists()  # Refresh assets
            await self.update_status()
        except Exception as e:
            self.log(f"❌ Failed to set garment: {e}")
    
    @on(Button.Pressed, "#set_fabric_btn")
    async def set_fabric(self):
        if not self.session or not self.fabric_list.selected:
            return
        
        fabric = str(self.fabric_list.selected)
        self.log(f"🧵 Setting fabric: {fabric}")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.set_fabric(fabric)
            )
            self.log(f"✅ Fabric set: {fabric}")
            await self.update_status()
        except Exception as e:
            self.log(f"❌ Failed to set fabric: {e}")
    
    @on(Button.Pressed, "#set_asset_btn")
    async def set_asset(self):
        if not self.session or not self.asset_list.selected:
            return
        
        asset = str(self.asset_list.selected)
        self.log(f"🎯 Setting asset: {asset}")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.set_asset(asset)
            )
            self.log(f"✅ Asset set: {asset}")
            await self.update_status()
        except Exception as e:
            self.log(f"❌ Failed to set asset: {e}")
    
    @on(Button.Pressed, "#render_btn")
    async def render(self):
        if not self.session:
            return
        
        # Check if ready
        state = await asyncio.get_event_loop().run_in_executor(
            None, self.session.get_state
        )
        
        if not state.get('ready_to_render'):
            self.log("❌ Cannot render - missing required selections")
            return
        
        self.log("🎬 Starting render...")
        
        try:
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, self.session.render
            )
            self.log(f"🎉 Render completed: {output_path}")
            await self.update_status()
        except Exception as e:
            self.log(f"❌ Render failed: {e}")
    
    async def on_unmount(self):
        """Clean up when app closes"""
        if self.session:
            self.session.cleanup()


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
    
    # Run the app
    app = BlenderTUIApp(blender_path)
    app.run()


if __name__ == "__main__":
    main()