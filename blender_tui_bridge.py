#!/usr/bin/env python3
"""
Blender TUI Bridge
This script runs OUTSIDE Blender and communicates with Blender via subprocess
This allows us to have a proper TUI while still controlling Blender
"""
import subprocess
import json
import tempfile
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
import time

class BlenderBridge:
    """
    Bridge that runs TUI outside Blender and communicates with Blender via files/subprocess
    """
    
    def __init__(self, blender_executable="blender"):
        self.blender_exe = blender_executable
        self.temp_dir = Path(tempfile.mkdtemp(prefix="blendomatic_"))
        self.config_file = self.temp_dir / "config.json"
        self.result_file = self.temp_dir / "result.json"
        self.script_file = self.temp_dir / "blender_script.py"
        self.log_file = self.temp_dir / "blender.log"
        
        # Generate the Blender script that will be executed
        self._create_blender_script()
        
        # Store last execution output for debugging
        self.last_stdout = ""
        self.last_stderr = ""
        
        print(f"[BRIDGE] Temp directory: {self.temp_dir}")
    
    def _create_blender_script(self):
        """Create the Python script that will run inside Blender"""
        script_content = '''
import bpy
import json
import sys
from pathlib import Path

# Add the original project directory to path
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath("__file__")))

try:
    from render_session import RenderSession
    
    # Load configuration from temp file
    config_file = Path(sys.argv[-2])  # Second to last argument
    result_file = Path(sys.argv[-1])  # Last argument
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Initialize session and execute command
    session = RenderSession()
    
    command = config.get('command')
    args = config.get('args', {})
    
    result = {'success': False, 'error': None, 'result': None}
    
    try:
        if command == 'list_modes':
            result['result'] = session.list_modes()
        elif command == 'list_garments':
            result['result'] = session.list_garments()
        elif command == 'list_fabrics':
            result['result'] = session.list_fabrics()
        elif command == 'list_assets':
            result['result'] = session.list_assets()
        elif command == 'set_mode':
            session.set_mode(args['mode'])
            result['result'] = 'success'
        elif command == 'set_garment':
            session.set_garment(args['garment'])
            result['result'] = 'success'
        elif command == 'set_fabric':
            session.set_fabric(args['fabric'])
            result['result'] = 'success'
        elif command == 'set_asset':
            session.set_asset(args['asset'])
            result['result'] = 'success'
        elif command == 'get_state':
            result['result'] = session.get_state()
        elif command == 'render':
            output_path = session.render()
            result['result'] = output_path
        elif command == 'render_with_config':
            # Configure everything at once then render
            config_data = args
            print(f"[RENDER_CONFIG] Starting with config: {config_data}")
            
            print("[RENDER_CONFIG] Setting mode...")
            session.set_mode(config_data['mode'])
            print(f"[RENDER_CONFIG] Mode set: {config_data['mode']}")
            
            print("[RENDER_CONFIG] Setting garment...")
            session.set_garment(config_data['garment'])
            print(f"[RENDER_CONFIG] Garment set: {config_data['garment']}")
            
            print("[RENDER_CONFIG] Setting fabric...")
            session.set_fabric(config_data['fabric'])
            print(f"[RENDER_CONFIG] Fabric set: {config_data['fabric']}")
            
            print("[RENDER_CONFIG] Setting asset...")
            session.set_asset(config_data['asset'])
            print(f"[RENDER_CONFIG] Asset set: {config_data['asset']}")
            
            print("[RENDER_CONFIG] Starting render...")
            output_path = session.render()
            print(f"[RENDER_CONFIG] Render completed: {output_path}")
            result['result'] = output_path
        else:
            result['error'] = f'Unknown command: {command}'
        
        result['success'] = True
            
    except Exception as e:
        result['error'] = str(e)
    
    # Save result
    with open(result_file, 'w') as f:
        json.dump(result, f)
        
except Exception as e:
    # Save error result
    result = {'success': False, 'error': f'Script error: {str(e)}', 'result': None}
    with open(result_file, 'w') as f:
        json.dump(result, f)
'''
        
        self.script_file.write_text(script_content)
    
    def execute_command(self, command: str, args: Dict = None) -> Dict:
        """Execute a command in Blender and return the result"""
        if args is None:
            args = {}
        
        # Write configuration
        config = {
            'command': command,
            'args': args
        }
        
        with open(self.config_file, 'w') as f:
            json.dump(config, f)
        
        # Remove old result file
        if self.result_file.exists():
            self.result_file.unlink()
        
        # Execute Blender with our script
        cmd = [
            self.blender_exe,
            "--background",
            "--python", str(self.script_file),
            "--", str(self.config_file), str(self.result_file)
        ]
        
        print(f"[BRIDGE] Executing: {' '.join(cmd)}")
        
        try:
            # Use longer timeout for render operations
            timeout = 180 if command in ['render', 'render_with_config'] else 60
            print(f"[BRIDGE] Using timeout: {timeout} seconds for command: {command}")
            print(f"[BRIDGE] Logging to: {self.log_file}")
            
            # Clear/create log file
            with open(self.log_file, 'w') as f:
                f.write(f"[BRIDGE] Starting command: {command}\n")
                f.write(f"[BRIDGE] Args: {args}\n")
                f.write(f"[BRIDGE] Command: {' '.join(cmd)}\n")
                f.write("-" * 50 + "\n")
            
            # Run Blender with output streaming to log file
            with open(self.log_file, 'a') as log_f:
                result = subprocess.run(
                    cmd, 
                    stdout=log_f, 
                    stderr=subprocess.STDOUT,  # Combine stderr with stdout
                    text=True, 
                    timeout=timeout
                )
            
            print(f"[BRIDGE] Blender exit code: {result.returncode}")
            
            # Read the log file for storage
            with open(self.log_file, 'r') as f:
                log_content = f.read()
            
            self.last_stdout = log_content
            self.last_stderr = ""  # Combined into stdout
            
            print(f"[BRIDGE] Log file size: {len(log_content)} chars")
            
            # Wait for result file
            max_wait = 10  # seconds
            waited = 0
            while not self.result_file.exists() and waited < max_wait:
                time.sleep(0.1)
                waited += 0.1
            
            if not self.result_file.exists():
                return {'success': False, 'error': 'No result file created', 'result': None}
            
            # Read result
            with open(self.result_file, 'r') as f:
                return json.load(f)
                
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timed out', 'result': None}
        except Exception as e:
            return {'success': False, 'error': f'Execution error: {str(e)}', 'result': None}
    
    def get_last_output(self) -> Dict[str, str]:
        """Get the stdout/stderr from the last command execution"""
        return {
            'stdout': self.last_stdout,
            'stderr': self.last_stderr
        }
    
    def get_log_file_path(self) -> str:
        """Get the path to the current log file"""
        return str(self.log_file)
    
    def cleanup(self):
        """Clean up temporary files"""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass


class BlenderTUISession:
    """
    TUI-compatible session that uses BlenderBridge
    """
    
    def __init__(self, blender_executable="blender"):
        self.bridge = BlenderBridge(blender_executable)
        self._state = {}
        self._refresh_state()
    
    def _refresh_state(self):
        """Refresh internal state from Blender"""
        result = self.bridge.execute_command('get_state')
        if result['success']:
            self._state = result['result']
        else:
            print(f"[ERROR] Failed to get state: {result['error']}")
    
    def list_modes(self) -> List[str]:
        result = self.bridge.execute_command('list_modes')
        return result['result'] if result['success'] else []
    
    def list_garments(self) -> List[str]:
        result = self.bridge.execute_command('list_garments')
        return result['result'] if result['success'] else []
    
    def list_fabrics(self) -> List[str]:
        result = self.bridge.execute_command('list_fabrics')
        return result['result'] if result['success'] else []
    
    def list_assets(self) -> List[str]:
        result = self.bridge.execute_command('list_assets')
        return result['result'] if result['success'] else []
    
    def set_mode(self, mode: str):
        result = self.bridge.execute_command('set_mode', {'mode': mode})
        if result['success']:
            self._refresh_state()
        else:
            raise Exception(result['error'])
    
    def set_garment(self, garment: str):
        result = self.bridge.execute_command('set_garment', {'garment': garment})
        if result['success']:
            self._refresh_state()
        else:
            raise Exception(result['error'])
    
    def set_fabric(self, fabric: str):
        result = self.bridge.execute_command('set_fabric', {'fabric': fabric})
        if result['success']:
            self._refresh_state()
        else:
            raise Exception(result['error'])
    
    def set_asset(self, asset: str):
        result = self.bridge.execute_command('set_asset', {'asset': asset})
        if result['success']:
            self._refresh_state()
        else:
            raise Exception(result['error'])
    
    def get_state(self) -> Dict:
        self._refresh_state()
        return self._state
    
    def is_ready_to_render(self) -> bool:
        state = self.get_state()
        return state.get('ready_to_render', False)
    
    def render(self) -> str:
        result = self.bridge.execute_command('render')
        if result['success']:
            self._refresh_state()
            return result['result']
        else:
            raise Exception(result['error'])
    
    def render_with_config(self, config: Dict[str, str]) -> str:
        """Configure Blender and render with all settings at once"""
        result = self.bridge.execute_command('render_with_config', config)
        if result['success']:
            self._refresh_state()
            return result['result']
        else:
            raise Exception(result['error'])
    
    def get_last_output(self) -> Dict[str, str]:
        """Get the stdout/stderr from the last command execution"""
        return self.bridge.get_last_output()
    
    def get_log_file_path(self) -> str:
        """Get the path to the current log file"""
        return self.bridge.get_log_file_path()
    
    def cleanup(self):
        """Clean up resources"""
        self.bridge.cleanup()


def main():
    """Test the Blender bridge"""
    print("🔗 BLENDER TUI BRIDGE TEST")
    print("=" * 50)
    
    # Find Blender
    blender_exe = "blender"  # Assume it's in PATH
    
    try:
        session = BlenderTUISession(blender_exe)
        
        print("Testing bridge connection...")
        modes = session.list_modes()
        print(f"Available modes: {modes}")
        
        garments = session.list_garments()
        print(f"Available garments: {garments}")
        
        state = session.get_state()
        print(f"Current state: {state}")
        
        print("✅ Bridge test successful!")
        
        # Clean up
        session.cleanup()
        
    except Exception as e:
        print(f"❌ Bridge test failed: {e}")


if __name__ == "__main__":
    main()