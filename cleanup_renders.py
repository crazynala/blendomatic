#!/usr/bin/env python3
"""
Utility to find and clean up orphaned Blender render processes
"""
import subprocess
import tempfile
import sys
from pathlib import Path
import signal
import os

def find_blender_processes():
    """Find all running Blender processes"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "blender.*background"],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            pids = [int(pid.strip()) for pid in result.stdout.strip().split('\n') if pid.strip()]
            return pids
        else:
            return []
    except Exception as e:
        print(f"Error finding processes: {e}")
        return []

def find_orphaned_renders():
    """Find orphaned render processes by checking temp directories"""
    temp_base = Path(tempfile.gettempdir())
    orphaned = []
    
    for temp_dir in temp_base.glob("blendomatic_*"):
        if temp_dir.is_dir():
            for pid_file in temp_dir.glob("render_*.pid"):
                try:
                    with open(pid_file, 'r') as f:
                        lines = f.readlines()
                        if lines:
                            pid = int(lines[0].strip())
                            
                            # Check if process is still running
                            try:
                                os.kill(pid, 0)  # Signal 0 just checks if process exists
                                orphaned.append({
                                    'pid': pid,
                                    'pid_file': pid_file,
                                    'temp_dir': temp_dir,
                                    'config': lines[1].strip() if len(lines) > 1 else 'Unknown'
                                })
                            except OSError:
                                # Process doesn't exist, clean up PID file
                                pid_file.unlink()
                                
                except (ValueError, IndexError, FileNotFoundError):
                    pass
    
    return orphaned

def kill_process(pid, force=False):
    """Kill a process by PID"""
    try:
        if force:
            os.kill(pid, signal.SIGKILL)
            print(f"✅ Force killed process {pid}")
        else:
            os.kill(pid, signal.SIGTERM)
            print(f"✅ Terminated process {pid}")
        return True
    except OSError as e:
        print(f"❌ Failed to kill process {pid}: {e}")
        return False

def main():
    print("🔍 BLENDER RENDER CLEANUP UTILITY")
    print("=" * 50)
    
    # Find all Blender processes
    blender_pids = find_blender_processes()
    print(f"Found {len(blender_pids)} running Blender processes: {blender_pids}")
    
    # Find orphaned renders
    orphaned = find_orphaned_renders()
    
    if not orphaned:
        print("✅ No orphaned render processes found")
        return
    
    print(f"\n🚨 Found {len(orphaned)} orphaned render processes:")
    
    for i, proc in enumerate(orphaned, 1):
        print(f"\n{i}. PID: {proc['pid']}")
        print(f"   Config: {proc['config']}")
        print(f"   Temp dir: {proc['temp_dir']}")
        print(f"   PID file: {proc['pid_file']}")
    
    print("\nOptions:")
    print("1. Kill all orphaned renders")
    print("2. Kill specific render (by number)")
    print("3. List only (no action)")
    print("4. Force kill all (SIGKILL)")
    
    try:
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            print("\n🛑 Terminating all orphaned renders...")
            for proc in orphaned:
                kill_process(proc['pid'])
                
        elif choice == "2":
            num = int(input(f"Enter process number (1-{len(orphaned)}): "))
            if 1 <= num <= len(orphaned):
                proc = orphaned[num-1]
                print(f"\n🛑 Terminating process {proc['pid']}...")
                kill_process(proc['pid'])
            else:
                print("❌ Invalid process number")
                
        elif choice == "3":
            print("📋 List only - no action taken")
            
        elif choice == "4":
            print("\n💥 Force killing all orphaned renders...")
            for proc in orphaned:
                kill_process(proc['pid'], force=True)
                
        else:
            print("❌ Invalid choice")
            
    except (ValueError, KeyboardInterrupt):
        print("\n🚫 Cancelled")

if __name__ == "__main__":
    main()