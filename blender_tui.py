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
        height: 8;
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
        
        # Local selections (work without Blender bridge)
        self.selected_mode: Optional[str] = None
        self.selected_garment: Optional[str] = None  
        self.selected_fabric: Optional[str] = None
        self.selected_asset: Optional[str] = None
    
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
    

    
    def validate_render_config(self) -> Dict[str, str]:
        """Validate all selections and return render configuration"""
        config = {}
        errors = []
        
        if not self.selected_mode:
            errors.append("Mode not selected")
        else:
            config['mode'] = self.selected_mode
            
        if not self.selected_garment:
            errors.append("Garment not selected") 
        else:
            config['garment'] = self.selected_garment
            
        if not self.selected_fabric:
            errors.append("Fabric not selected")
        else:
            config['fabric'] = self.selected_fabric
            
        if not self.selected_asset:
            errors.append("Asset not selected")
        else:
            config['asset'] = self.selected_asset
        
        if errors:
            raise ValueError(f"Missing selections: {', '.join(errors)}")
            
        return config
    
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
                
                yield Static("Garment", id="garment_title")  
                self.garment_list = SelectionList(id="garment_list")
                yield self.garment_list
                
                yield Static("Fabric", id="fabric_title")
                self.fabric_list = SelectionList(id="fabric_list")
                yield self.fabric_list
                
                yield Static("Asset", id="asset_title")
                self.asset_list = SelectionList(id="asset_list")
                yield self.asset_list
                
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
            await self.update_local_status()
            
        except Exception as e:
            self.write_message(f"⚠️  Blender bridge unavailable: {e}")
            self.write_message("📁 Running in file-only mode (no rendering)")
            if self.status_display:
                self.status_display.update("File-only mode - Blender bridge unavailable")
        
        self.write_message("✅ TUI ready - click on items to select them")
    
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
        self.write_message(f"🔍 DEBUG: refresh_assets_list called, current_garment_name: {self.current_garment_name}")
        
        if not self.asset_list:
            self.write_message("🔍 DEBUG: asset_list is None")
            return
        
        try:
            # Get assets from local garment file (no bridge needed)
            assets = []
            if self.current_garment_name:
                self.write_message(f"🔍 DEBUG: Getting assets for garment: {self.current_garment_name}")
                assets = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._get_garment_assets(self.current_garment_name)
                )
                self.write_message(f"🔍 DEBUG: Found {len(assets)} assets: {assets}")
            
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
            import traceback
            self.write_message(f"🔍 DEBUG: Traceback: {traceback.format_exc()}")
    


    
    @on(SelectionList.SelectedChanged, "#mode_list")
    async def on_mode_selection_changed(self, event: SelectionList.SelectedChanged):
        if self.mode_list and self.mode_list.selected:
            selected = self.mode_list.selected
            mode = selected[0] if isinstance(selected, list) else selected
            self.selected_mode = mode
            self.write_message(f"✅ Mode selected: {mode}")
            await self.update_local_status()
    
    @on(SelectionList.SelectedChanged, "#garment_list")
    async def on_garment_selection_changed(self, event: SelectionList.SelectedChanged):
        if self.garment_list and self.garment_list.selected:
            selected = self.garment_list.selected
            garment = selected[0] if isinstance(selected, list) else selected
            self.current_garment_name = garment
            self.selected_garment = garment
            self.write_message(f"✅ Garment selected: {garment}")
            await self.refresh_assets_list()
            await self.update_local_status()
    
    @on(SelectionList.SelectedChanged, "#fabric_list")
    async def on_fabric_selection_changed(self, event: SelectionList.SelectedChanged):
        if self.fabric_list and self.fabric_list.selected:
            selected = self.fabric_list.selected
            fabric = selected[0] if isinstance(selected, list) else selected
            self.selected_fabric = fabric
            self.write_message(f"✅ Fabric selected: {fabric}")
            await self.update_local_status()
    
    @on(SelectionList.SelectedChanged, "#asset_list")
    async def on_asset_selection_changed(self, event: SelectionList.SelectedChanged):
        if not self.current_garment_name:
            self.write_message("❌ Please select a garment first")
            return
            
        if self.asset_list and self.asset_list.selected:
            selected = self.asset_list.selected
            asset = selected[0] if isinstance(selected, list) else selected
            self.selected_asset = asset
            self.write_message(f"✅ Asset selected: {asset}")
            await self.update_local_status()
    
    async def update_local_status(self):
        """Update status display with local selections"""
        if not self.status_display:
            return
        
        status_text = f"""Mode: {self.selected_mode or 'Not selected'}
Garment: {self.selected_garment or 'Not selected'}  
Fabric: {self.selected_fabric or 'Not selected'}
Asset: {self.selected_asset or 'Not selected'}

Status: {'Ready to render' if all([self.selected_mode, self.selected_garment, self.selected_fabric, self.selected_asset]) else 'Configuration incomplete'}"""
        
        self.status_display.update(status_text)
    
    @on(Button.Pressed, "#render_btn")
    async def render(self):
        self.write_message("🎬 Starting render...")
        
        try:
            # Validate configuration
            config = self.validate_render_config()
            self.write_message(f"✅ Configuration validated: {config}")
            
            # Check if bridge is available
            if not self.session:
                self.write_message("❌ Blender bridge not available - initializing...")
                # Try to initialize bridge
                try:
                    self.session = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: BlenderTUISession(self.blender_exe)
                    )
                    self.write_message("✅ Blender bridge initialized")
                except Exception as e:
                    self.write_message(f"❌ Failed to initialize Blender: {e}")
                    return
            
            # Execute render with all configuration at once
            self.write_message("🔧 Configuring Blender and rendering...")
            output_path = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.session.render_with_config(config)
            )
            self.write_message(f"🎉 Render completed: {output_path}")
            
        except ValueError as e:
            self.write_message(f"❌ Configuration error: {e}")
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