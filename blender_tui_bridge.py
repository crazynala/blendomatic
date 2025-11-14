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
import signal
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
        
        # Track render process for cancellation
        self.render_process = None
        self.render_pid = None
        
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
    print("[BRIDGE_SCRIPT] 🚀 Bridge script starting execution", flush=True)
    import sys
    sys.stdout.flush()
    
    from render_session import RenderSession
    print("[BRIDGE_SCRIPT] ✅ RenderSession imported", flush=True)
    sys.stdout.flush()
    
    # Load configuration from temp file
    config_file = Path(sys.argv[-2])  # Second to last argument
    result_file = Path(sys.argv[-1])  # Last argument
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    print(f"[BRIDGE_SCRIPT] 📋 Loaded config: {config}", flush=True)
    sys.stdout.flush()
    
    # Initialize session and execute command
    print("[BRIDGE_SCRIPT] 🔧 Initializing RenderSession...", flush=True)
    sys.stdout.flush()
    session = RenderSession()
    print("[BRIDGE_SCRIPT] ✅ RenderSession initialized", flush=True)
    sys.stdout.flush()
    
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
            print(f"[RENDER_CONFIG] 🚀 Starting render with full config", flush=True)
            print(f"[RENDER_CONFIG] Config keys: {list(config_data.keys())}", flush=True)
            print(f"[RENDER_CONFIG] Full config: {json.dumps(config_data, indent=2)}", flush=True)
            
            print(f"[RENDER_CONFIG] � Setting garment: {config_data['garment']}", flush=True)
            session.set_garment(config_data['garment'])
            print(f"[RENDER_CONFIG] ✅ Garment '{config_data['garment']}' loaded", flush=True)
            
            print(f"[RENDER_CONFIG] 🧵 Setting fabric: {config_data['fabric']}", flush=True)
            session.set_fabric(config_data['fabric'])
            print(f"[RENDER_CONFIG] ✅ Fabric '{config_data['fabric']}' applied", flush=True)
            
            print(f"[RENDER_CONFIG] 🎯 Setting asset: {config_data['asset']}", flush=True)
            session.set_asset(config_data['asset'])
            print(f"[RENDER_CONFIG] ✅ Asset '{config_data['asset']}' loaded", flush=True)
            
            print(f"[RENDER_CONFIG] 🔧 Setting mode: {config_data['mode']} (AFTER scene load)", flush=True)
            session.set_mode(config_data['mode'])
            print(f"[RENDER_CONFIG] ✅ Mode '{config_data['mode']}' applied AFTER scene load", flush=True)
            
            print("[RENDER_CONFIG] 🎬 Starting render process...", flush=True)
            output_path = session.render()
            print(f"[RENDER_CONFIG] 🎉 Render completed successfully: {output_path}", flush=True)
            result['result'] = output_path
        elif command == 'render_multiple_configs':
            # Render multiple fabric x asset combinations sequentially
            configs = args.get('configs', [])
            total_configs = len(configs)
            
            # Initialize log for batch rendering
            import sys
            import os
            
            # Write to both console and log file
            def log_and_print(msg):
                print(msg, flush=True)
                # Also write to log file if available
                log_file = args.get('log_file')
                if log_file:
                    try:
                        with open(log_file, 'a') as f:
                            f.write(f"{msg}\\n")
                    except:
                        pass  # Continue if log file write fails
            
            log_and_print(f"[MULTI_RENDER] 🚀 Starting batch render of {total_configs} configurations")
            
            successful_renders = []
            failed_renders = []
            
            for i, config_data in enumerate(configs, 1):
                try:
                    log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] Starting: {config_data['fabric']} × {config_data['asset']}")
                    
                    # Load garment (only needed for first render if same garment)
                    if i == 1 or config_data['garment'] != configs[i-2]['garment']:
                        log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] Loading garment: {config_data['garment']}")
                        session.set_garment(config_data['garment'])
                    
                    # Apply fabric
                    log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] Applying fabric: {config_data['fabric']}")
                    session.set_fabric(config_data['fabric'])
                    
                    # Configure asset
                    log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] Configuring asset: {config_data['asset']}")
                    session.set_asset(config_data['asset'])
                    
                    # Apply mode settings (only if changed)
                    if i == 1 or config_data['mode'] != configs[i-2]['mode']:
                        log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] Setting mode: {config_data['mode']}")
                        session.set_mode(config_data['mode'])
                    
                    # Render
                    log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] Rendering...")
                    output_path = session.render()
                    
                    successful_renders.append({
                        'fabric': config_data['fabric'],
                        'asset': config_data['asset'],
                        'output_path': output_path
                    })
                    log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] ✅ Completed: {output_path}")
                    
                except Exception as e:
                    error_msg = str(e)
                    failed_renders.append({
                        'fabric': config_data['fabric'],
                        'asset': config_data['asset'],
                        'error': error_msg
                    })
                    log_and_print(f"[MULTI_RENDER] [{i}/{total_configs}] ❌ Failed: {error_msg}")
            
            result['result'] = {
                'successful_renders': successful_renders,
                'failed_renders': failed_renders,
                'total_attempted': total_configs
            }
            log_and_print(f"[MULTI_RENDER] 🎉 Batch complete: {len(successful_renders)} successful, {len(failed_renders)} failed")
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
            # Use detached execution for render operations unless explicitly disabled
            if command in ['render', 'render_with_config', 'render_multiple_configs']:
                # Check if synchronous execution is requested
                force_sync = args.get('force_synchronous', False)
                if force_sync:
                    timeout = args.get('timeout_seconds', 3600)  # Default 1 hour for renders
                    print(f"[BRIDGE] Force synchronous mode - timeout: {timeout} seconds")
                else:
                    return self._execute_render_detached(cmd, command, args)
            else:
                timeout = 60
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
    
    def _execute_render_detached(self, cmd: List[str], command: str, args: Dict) -> Dict:
        """Execute render command in detached subprocess"""
        print(f"[BRIDGE] Starting detached render process")
        
        # Create dedicated config and result files for render to avoid conflicts
        render_config_file = self.temp_dir / "render_config.json"
        render_result_file = self.temp_dir / "render_result.json" 
        render_log_file = self.temp_dir / "render.log"
        
        # Write render configuration to dedicated file
        config = {
            'command': command,
            'args': args
        }
        with open(render_config_file, 'w') as f:
            json.dump(config, f)
        
        # Create dedicated command for render
        render_cmd = [
            self.blender_exe,
            "--background", 
            "--python", str(self.script_file),
            "--", str(render_config_file), str(render_result_file)
        ]
        
        # Clear/create log file
        with open(render_log_file, 'w') as f:
            f.write(f"[BRIDGE] Starting detached command: {command}\n")
            f.write(f"[BRIDGE] Args: {args}\n")
            f.write(f"[BRIDGE] Command: {' '.join(render_cmd)}\n")
            f.write("-" * 50 + "\n")
        
        # Start subprocess in detached mode
        with open(render_log_file, 'a') as log_f:
            process = subprocess.Popen(
                render_cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
                # Detach from parent process
                start_new_session=True
            )
        
        # Store process info for potential cancellation
        self.render_process = process
        self.render_pid = process.pid
        
        # Write PID file for tracking orphaned processes
        pid_file = self.temp_dir / f"render_{process.pid}.pid"
        with open(pid_file, 'w') as f:
            f.write(f"{process.pid}\n{args}\n")
        
        print(f"[BRIDGE] Render started with PID: {process.pid}")
        print(f"[BRIDGE] PID file: {pid_file}")
        print(f"[BRIDGE] Logging to: {render_log_file}")
        
        # Return immediately - render runs in background
        return {
            "success": True, 
            "result": f"Render started (PID: {process.pid})",
            "pid": process.pid,
            "log_file": str(render_log_file),
            "pid_file": str(pid_file),
            "detached": True
        }
    
    def cancel_render(self) -> Dict:
        """Cancel the currently running render process"""
        if not hasattr(self, 'render_process') or not self.render_process:
            return {"success": False, "error": "No render process to cancel"}
        
        try:
            # Try graceful shutdown first
            self.render_process.terminate()
            
            # Wait a bit for graceful shutdown
            try:
                self.render_process.wait(timeout=5)
                return {"success": True, "result": "Render cancelled gracefully"}
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                self.render_process.kill()
                return {"success": True, "result": "Render force-cancelled"}
                
        except Exception as e:
            return {"success": False, "error": "Failed to cancel render: " + str(e)}
    
    def check_render_status(self) -> Dict:
        """Check if render process is still running"""
        if not hasattr(self, 'render_process') or not self.render_process:
            return {"running": False, "pid": None}
        
        poll_result = self.render_process.poll()
        if poll_result is None:
            # Still running
            return {"running": True, "pid": self.render_pid}
        else:
            # Process finished
            return {"running": False, "pid": self.render_pid, "exit_code": poll_result}
    
    def cleanup(self):
        """Clean up temporary files and processes"""
        try:
            # Cancel any running render process
            if hasattr(self, 'render_process') and self.render_process:
                try:
                    print(f"[BRIDGE] Terminating render process PID: {self.render_pid}")
                    self.render_process.terminate()
                    self.render_process.wait(timeout=5)
                    print(f"[BRIDGE] Render process terminated gracefully")
                except subprocess.TimeoutExpired:
                    try:
                        print(f"[BRIDGE] Force killing render process PID: {self.render_pid}")
                        self.render_process.kill()
                        print(f"[BRIDGE] Render process killed")
                    except:
                        print(f"[BRIDGE] Warning: Could not kill render process PID: {self.render_pid}")
                except Exception as e:
                    print(f"[BRIDGE] Warning: Error terminating render process: {e}")
            
            # Clean up PID files for orphan tracking
            try:
                for pid_file in self.temp_dir.glob("render_*.pid"):
                    pid_file.unlink()
            except Exception as e:
                print(f"[BRIDGE] Warning: Error cleaning PID files: {e}")
            
            # Remove temporary directory
            import shutil
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                print(f"[BRIDGE] Cleaned up temp directory: {self.temp_dir}")
        except Exception as e:
            print(f"[BRIDGE] Warning: Cleanup error: {e}")
    
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
    
    def render_multiple_configs(self, configs: List[Dict]) -> Dict:
        """Render multiple fabric x asset combinations sequentially in the same Blender process (detached)"""
        # Pass the log file path so batch rendering can write to it
        log_file_path = self.bridge.get_log_file_path()
        result = self.bridge.execute_command('render_multiple_configs', {
            'configs': configs,
            'log_file': log_file_path
        })
        if result['success']:
            self._refresh_state()
            return result  # Return full result dict for detached rendering
        else:
            raise Exception(result['error'])

    def render_multiple_configs_sync(self, configs: List[Dict]) -> Dict:
        """Render multiple fabric x asset combinations sequentially synchronously (waits for completion)"""
        # Add flag to force synchronous execution
        log_file_path = self.bridge.get_log_file_path()
        sync_args = {
            'configs': configs,
            'log_file': log_file_path,
            'force_synchronous': True
        }
        result = self.bridge.execute_command('render_multiple_configs', sync_args)
        if result['success']:
            self._refresh_state()
            return result['result']
        else:
            raise Exception(result['error'])
    
    def render_with_config(self, config: Dict[str, str]) -> Dict:
        """Configure Blender and render with all settings at once"""
        result = self.bridge.execute_command('render_with_config', config)
        if result['success']:
            self._refresh_state()
            return result  # Return full result dict for detached rendering
        else:
            raise Exception(result['error'])
    
    def render_with_config_sync(self, config: Dict[str, str]) -> Dict:
        """Configure Blender and render synchronously (waits for completion)"""
        # Add flag to force synchronous execution
        sync_config = config.copy()
        sync_config['force_synchronous'] = True
        
        result = self.bridge.execute_command('render_with_config', sync_config)
        if result['success']:
            self._refresh_state()
            return result
        else:
            raise Exception(result['error'])
    
    def get_last_output(self) -> Dict[str, str]:
        """Get the stdout/stderr from the last command execution"""
        return self.bridge.get_last_output()
    
    def get_log_file_path(self) -> str:
        """Get the path to the current log file"""
        return self.bridge.get_log_file_path()
    
    def cancel_render(self) -> Dict:
        """Cancel the currently running render process"""
        return self.bridge.cancel_render()
    
    def check_render_status(self) -> Dict:
        """Check if render process is still running"""
        return self.bridge.check_render_status()
    
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