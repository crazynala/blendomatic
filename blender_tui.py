"""
Fixed Blender TUI that properly handles Textual's logging system
This version avoids all conflicts with Textual's internal log property
"""
try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Header, Footer, Static, Button, SelectionList, Label, Log
    from textual.screen import Screen
    from textual import on
    import asyncio
    import json
    from pathlib import Path
    from typing import Optional, List, Dict, Any
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
    class SelectionList: pass
    class Label: pass
    class Log: pass
    
    def on(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

# Constants for file paths
GARMENTS_DIR = Path("garments")
FABRICS_DIR = Path("fabrics")
RENDER_CONFIG_PATH = Path("render_config.json")

from blender_tui_bridge import BlenderTUISession
import sys

class BlenderTUIApp(App):
    """
    Textual TUI that communicates with Blender via bridge
    Properly handles Textual's logging system without conflicts
    """
    
    TITLE = "Blendomatic - Blender TUI"
    
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
    
    .message_panel {
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
        self.session: Optional[BlenderTUISession] = None
        self.blender_exe = blender_executable
        
        # UI components - avoid 'log' in names to prevent conflicts
        self.status_display: Optional[Static] = None
        self.message_display: Optional[Log] = None  # Renamed from log_display
        self.mode_list: Optional[SelectionList] = None
        self.garment_list: Optional[SelectionList] = None
        self.fabric_list: Optional[SelectionList] = None
        self.asset_list: Optional[SelectionList] = None
        
        # Local data caches
        self.garment_data: Dict[str, Any] = {}
        self.current_garment_name: Optional[str] = None
    
    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """Load a JSON file safely"""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.write_message(f"❌ Error loading {file_path}: {e}")
            return {}
    
    def _get_local_garments(self) -> List[str]:
        """Get list of available garment files"""
        if not GARMENTS_DIR.exists():
            return []
        return [f.name for f in GARMENTS_DIR.glob("*.json")]
    
    def _get_local_fabrics(self) -> List[str]:
        """Get list of available fabric files"""
        if not FABRICS_DIR.exists():
            return []
        return [f.name for f in FABRICS_DIR.glob("*.json")]
    
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
            
            # Message panel (renamed from log panel)
            with Container(classes="message_panel"):
                yield Static("Messages", id="message_title")
                self.message_display = Log(auto_scroll=True)
                yield self.message_display
        
        yield Footer()
    
    async def on_mount(self):
        """Initialize the session when app starts"""
        self.write_message("🚀 Initializing Blender TUI...")
        
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
            await self.update_status()
            
        except Exception as e:
            self.write_message(f"⚠️  Blender bridge unavailable: {e}")
            self.write_message("📁 Running in file-only mode (no rendering)")
            if self.status_display:
                self.status_display.update("File-only mode - Blender bridge unavailable")
    
    def write_message(self, message: str):
        """Write message to the message display (avoiding 'log' method name)"""
        if self.message_display:
            self.message_display.write_line(message)
        # Also use Textual's built-in logging properly
        if hasattr(self, 'log') and hasattr(self.log, 'info'):
            self.log.info(message)
        print(message)  # Also print to console for debugging
    
    async def refresh_all_lists(self):
        """Refresh all selection lists"""
        try:
            # Get modes from Blender bridge (only modes need Blender)
            modes = []
            if self.session:
                modes = await asyncio.get_event_loop().run_in_executor(
                    None, self.session.list_modes
                )
            
            # Get garments and fabrics from local files (no Blender needed)
            garments = await asyncio.get_event_loop().run_in_executor(
                None, self._get_local_garments
            )
            fabrics = await asyncio.get_event_loop().run_in_executor(
                None, self._get_local_fabrics
            )
            
            # Get assets for current garment (if any)
            assets = []
            if self.current_garment_name:
                assets = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._get_garment_assets(self.current_garment_name)
                )
            
            # Update lists
            if self.mode_list:
                self.mode_list.clear_options()
                for mode in modes:
                    self.mode_list.add_option((mode, mode))
            
            if self.garment_list:
                self.garment_list.clear_options()
                for garment in garments:
                    self.garment_list.add_option((garment, garment))
                
            if self.fabric_list:
                self.fabric_list.clear_options()
                for fabric in fabrics:
                    self.fabric_list.add_option((fabric, fabric))
                
            if self.asset_list:
                self.asset_list.clear_options()
                for asset in assets:
                    self.asset_list.add_option((asset, asset))
            
            # Debug info about loaded data
            self.write_message(f"📋 Lists refreshed - Modes: {len(modes)}, Garments: {len(garments)}, Fabrics: {len(fabrics)}, Assets: {len(assets)}")
            if assets:
                self.write_message(f"Available assets: {', '.join(assets)}")
            else:
                self.write_message("No assets loaded (garment must be selected first)")
            
        except Exception as e:
            self.write_message(f"❌ Failed to refresh lists: {e}")
    
    async def refresh_assets_list(self):
        """Refresh only the assets list (called after garment selection)"""
        if not self.asset_list:
            return
        
        try:
            # Get assets from local garment file (no bridge needed)
            assets = []
            if self.current_garment_name:
                assets = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._get_garment_assets(self.current_garment_name)
                )
            
            self.asset_list.clear_options()
            for asset in assets:
                self.asset_list.add_option((asset, asset))
            
            # Debug info
            if assets:
                self.write_message(f"🎯 Assets refreshed ({len(assets)} available): {', '.join(assets)}")
            else:
                self.write_message("🎯 No assets available (select a garment first)")
            
        except Exception as e:
            self.write_message(f"❌ Failed to refresh assets: {e}")
    
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
            self.write_message(f"❌ Failed to update status: {e}")
    
    @on(Button.Pressed, "#set_mode_btn")
    async def set_mode(self):
        if not self.session or not self.mode_list or not self.mode_list.selected:
            return
        
        # Handle both single value and list selection
        selected = self.mode_list.selected
        mode = selected[0] if isinstance(selected, list) else selected
        self.write_message(f"🔧 Setting mode: {mode}")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.set_mode(mode)
            )
            self.write_message(f"✅ Mode set: {mode}")
            await self.update_status()
        except Exception as e:
            self.write_message(f"❌ Failed to set mode: {e}")
    
    @on(Button.Pressed, "#set_garment_btn")
    async def set_garment(self):
        if not self.session or not self.garment_list or not self.garment_list.selected:
            return
        
        # Handle both single value and list selection
        selected = self.garment_list.selected
        garment = selected[0] if isinstance(selected, list) else selected
        self.write_message(f"👔 Setting garment: {garment}")
        
        try:
            # Update current garment name for asset loading
            self.current_garment_name = garment
            
            # Set garment in Blender bridge (if available)
            if self.session:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.session.set_garment(garment)
                )
            
            self.write_message(f"✅ Garment set: {garment}")
            await self.update_status()
            # Refresh assets list since it depends on the selected garment
            await self.refresh_assets_list()
        except Exception as e:
            self.write_message(f"❌ Failed to set garment: {e}")
    
    @on(Button.Pressed, "#set_fabric_btn")
    async def set_fabric(self):
        if not self.session or not self.fabric_list or not self.fabric_list.selected:
            return
        
        # Handle both single value and list selection
        selected = self.fabric_list.selected
        fabric = selected[0] if isinstance(selected, list) else selected
        self.write_message(f"🧵 Setting fabric: {fabric}")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.set_fabric(fabric)
            )
            self.write_message(f"✅ Fabric set: {fabric}")
            await self.update_status()
        except Exception as e:
            self.write_message(f"❌ Failed to set fabric: {e}")
    
    @on(Button.Pressed, "#set_asset_btn")
    async def set_asset(self):
        if not self.session or not self.asset_list or not self.asset_list.selected:
            return
        
        # Handle both single value and list selection
        selected = self.asset_list.selected
        asset = selected[0] if isinstance(selected, list) else selected
        self.write_message(f"🎯 Setting asset: {asset}")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.set_asset(asset)
            )
            self.write_message(f"✅ Asset set: {asset}")
            await self.update_status()
        except Exception as e:
            self.write_message(f"❌ Failed to set asset: {e}")
    
    @on(Button.Pressed, "#render_btn")
    async def render(self):
        if not self.session:
            return
        
        # Check if ready
        state = await asyncio.get_event_loop().run_in_executor(
            None, self.session.get_state
        )
        
        if not state.get('ready_to_render'):
            self.write_message("❌ Cannot render - missing required selections")
            return
        
        self.write_message("🎬 Starting render...")
        
        try:
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, self.session.render
            )
            self.write_message(f"🎉 Render completed: {output_path}")
            await self.update_status()
        except Exception as e:
            self.write_message(f"❌ Render failed: {e}")
    
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
    
    # Run the app with proper error handling
    try:
        app = BlenderTUIApp(blender_path)
        app.run()
    except Exception as e:
        print(f"\n❌ TUI error: {e}")
        print("This may happen due to terminal compatibility issues.")
        print("💡 Try the shell interface: python main.py --interface shell")
        sys.exit(1)


if __name__ == "__main__":
    main()