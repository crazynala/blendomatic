"""
Fixed Blender TUI that properly handles Textual's logging system
This version avoids all conflicts with Textual's internal log property
"""
import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Header, Footer, Static, Button, SelectionList, Label, Log, Checkbox, Input
    from textual.screen import Screen
    from textual import on
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
    class Checkbox: pass
    class Input: pass
    
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
        height: 6;
        margin: 0 0 1 0;
        padding: 1;
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
        self.timeout_checkbox: Optional[Checkbox] = None
        self.timeout_input: Optional[Input] = None
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
        
        # Timeout configuration
        self.timeout_enabled: bool = True
        self.timeout_seconds: int = 600  # Default 10 minutes
        
        # Rendering state
        self.is_rendering: bool = False
        self.current_render_task: Optional[asyncio.Task] = None
        self.current_log_task: Optional[asyncio.Task] = None
        self.render_pid: Optional[int] = None
    
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
    

    
    def validate_render_config(self) -> List[Dict[str, str]]:
        """Validate all selections and return list of render configurations (fabric x asset combinations)"""
        errors = []
        
        if not self.selected_mode:
            errors.append("Mode not selected")
            
        if not self.selected_garment:
            errors.append("Garment not selected") 
            
        if not self.selected_fabrics:
            errors.append("No fabrics selected")
            
        if not self.selected_assets:
            errors.append("No assets selected")
        
        if errors:
            raise ValueError(f"Missing selections: {', '.join(errors)}")
        
        # Generate all fabric x asset combinations
        configs = []
        for fabric in self.selected_fabrics:
            for asset in self.selected_assets:
                config = {
                    'mode': self.selected_mode,
                    'garment': self.selected_garment,
                    'fabric': fabric,
                    'asset': asset
                }
                
                # Add timeout configuration if enabled
                if self.timeout_enabled:
                    config['timeout_seconds'] = self.timeout_seconds
                
                configs.append(config)
        
        return configs
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Container():
            # Three-column main layout
            with Horizontal():
                # Left column: Mode & Fabric
                with Vertical(classes="left_column"):
                    yield Static("� Mode", id="mode_title")
                    self.mode_list = SelectionList(id="mode_list")
                    yield self.mode_list
                    
                    yield Static("🧵 Fabric", id="fabric_title")
                    self.fabric_list = SelectionList(id="fabric_list")
                    yield self.fabric_list
                
                # Middle column: Garments
                with Vertical(classes="middle_column"):
                    yield Static("👔 Garment", id="garment_title")  
                    self.garment_list = SelectionList(id="garment_list")
                    yield self.garment_list
                
                # Right column: Assets
                with Vertical(classes="right_column"):
                    yield Static("🎯 Asset", id="asset_title")
                    self.asset_list = SelectionList(id="asset_list")
                    yield self.asset_list
            
            # Bottom section: Timeout config and render controls
            with Horizontal(classes="controls_row"):
                with Horizontal(classes="timeout_config"):
                    self.timeout_checkbox = Checkbox("Use timeout", value=True, id="timeout_checkbox")
                    yield self.timeout_checkbox
                    self.timeout_input = Input(value="600", placeholder="Timeout (s)", id="timeout_input")
                    yield self.timeout_input
                
                self.render_button = Button("🎬 RENDER", id="render_btn", variant="success")
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
                    with open("render_config.json", 'r') as f:
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
                self.write_message(f"🔧 DEBUG: Loaded modes: {modes}")
            
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
                self.write_message(f"✅ Garment selected: {garment}")
                await self.refresh_assets_list()
        elif list_id == "fabric_list":
            if self.fabric_list and self.fabric_list.selected:
                self.selected_fabrics = list(self.fabric_list.selected)
                fabric_count = len(self.selected_fabrics)
                if fabric_count == 1:
                    self.write_message(f"✅ Fabric selected: {self.selected_fabrics[0]}")
                else:
                    self.write_message(f"✅ {fabric_count} fabrics selected: {', '.join(self.selected_fabrics)}")
        elif list_id == "asset_list":
            if not self.current_garment_name:
                self.write_message("❌ Please select a garment first")
                return
                
            if self.asset_list and self.asset_list.selected:
                self.selected_assets = list(self.asset_list.selected)
                asset_count = len(self.selected_assets)
                if asset_count == 1:
                    self.write_message(f"✅ Asset selected: {self.selected_assets[0]}")
                else:
                    self.write_message(f"✅ {asset_count} assets selected: {', '.join(self.selected_assets)}")
        
        await self.update_local_status()
    

    
    async def on_checkbox_changed(self, event):
        """Handle timeout checkbox changes"""
        if event.checkbox is self.timeout_checkbox:
            self.timeout_enabled = event.value
            if hasattr(self, 'timeout_input'):
                self.timeout_input.disabled = not self.timeout_enabled
            await self.update_local_status()
    
    async def on_input_changed(self, event):
        """Handle timeout input changes"""
        if hasattr(event, 'input') and event.input is self.timeout_input:
            try:
                value = int(event.value)
                if value > 0:
                    self.timeout_seconds = value
                    await self.update_local_status()
            except ValueError:
                pass  # Invalid input, ignore
    
    async def update_local_status(self):
        """Update message log with current configuration status"""
        timeout_status = f"{self.timeout_seconds}s" if self.timeout_enabled else "Disabled"
        
        ready = all([self.selected_mode, self.selected_garment, self.selected_fabrics, self.selected_assets])
        status = 'Ready to render' if ready else 'Configuration incomplete'
        
        fabric_status = f"{len(self.selected_fabrics)} selected" if self.selected_fabrics else "Not selected"
        asset_status = f"{len(self.selected_assets)} selected" if self.selected_assets else "Not selected"
        combinations = len(self.selected_fabrics) * len(self.selected_assets) if self.selected_fabrics and self.selected_assets else 0
        combo_status = f" | 🎯 Will render {combinations} combinations" if combinations > 1 else ""
        
        self.write_message(f"🔧 Mode: {self.selected_mode or 'Not selected'} | 👔 Garment: {self.selected_garment or 'Not selected'} | 🧵 Fabrics: {fabric_status} | 🎨 Assets: {asset_status}{combo_status} | ⏱️ Timeout: {timeout_status} | Status: {status}")
    
    async def tail_log_file(self, log_file_path: str):
        """Tail the Blender log file and stream output to TUI"""
        last_position = 0
        
        while True:
            try:
                await asyncio.sleep(1.0)  # Check every 1 second
                
                if Path(log_file_path).exists():
                    with open(log_file_path, 'r') as f:
                        f.seek(last_position)
                        new_content = f.read()
                        
                        if new_content:
                            # Split into lines and show each one
                            for line in new_content.split('\n'):
                                if line.strip():
                                    self.write_message(f"🔧 {line}")
                            
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
                self.write_message(f"✅ Configuration validated: {configs[0]}")
            else:
                self.write_message(f"✅ Will render {total_combinations} fabric x asset combinations:")
                for i, config in enumerate(configs, 1):
                    self.write_message(f"  {i}. {config['fabric']} × {config['asset']}")
            
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
                self.write_message(f"🔧 Rendering {total_combinations} fabric x asset combinations in batch...")
                
                # Start log streaming for batch rendering
                log_file_path = self.session.bridge.get_log_file_path()
                if log_file_path:
                    # Clear existing log content and start tailing
                    try:
                        open(log_file_path, 'w').close()  # Clear log file
                    except:
                        pass
                    log_task = asyncio.create_task(self.tail_log_file(log_file_path))
                    self.current_log_task = log_task
                    self.write_message(f"📄 Streaming batch render log from: {log_file_path}")
                
                try:
                    # Execute all combinations in a single Blender process
                    batch_result = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self.session.render_multiple_configs(configs)
                    )
                    
                    successful_renders = batch_result.get('successful_renders', [])
                    failed_renders = batch_result.get('failed_renders', [])
                    
                    # Summary for batch renders
                    end_time = asyncio.get_event_loop().time()
                    self.write_message(f"⏱️  Total render time: {end_time - start_time:.1f} seconds")
                    
                    if successful_renders:
                        self.write_message(f"🎉 {len(successful_renders)} renders completed successfully:")
                        for render in successful_renders:
                            fabric = render['fabric']
                            asset = render['asset']
                            output_path = render['output_path']
                            self.write_message(f"  ✅ {fabric} × {asset}: {output_path}")
                    
                    if failed_renders:
                        self.write_message(f"❌ {len(failed_renders)} renders failed:")
                        for render in failed_renders:
                            fabric = render['fabric']
                            asset = render['asset']
                            error = render['error']
                            self.write_message(f"  ❌ {fabric} × {asset}: {error}")
                    
                    if not successful_renders and not failed_renders:
                        self.write_message("🛑 No renders completed")
                        
                except Exception as e:
                    self.write_message(f"❌ Batch render failed: {e}")
                finally:
                    # Stop log streaming for batch rendering
                    if self.current_log_task:
                        self.current_log_task.cancel()
                        self.current_log_task = None
            
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
                    else:
                        self.write_message(f"❌ Render failed with exit code: {exit_code}")
                    
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