#!/usr/bin/env python3
"""
Blendomatic Launcher
Helps users understand how to run the script properly
"""
import sys
import os
import subprocess
from pathlib import Path

def main():
    print("🎯 BLENDOMATIC LAUNCHER")
    print("=" * 50)
    
    # Check if Blender is available
    blender_path = None
    for possible_path in [
        "/Applications/Blender.app/Contents/MacOS/Blender",  # macOS
        "/usr/bin/blender",  # Linux
        "C:\\Program Files\\Blender Foundation\\Blender\\blender.exe",  # Windows
        "blender",  # System PATH
    ]:
        if os.path.exists(possible_path) or possible_path == "blender":
            try:
                result = subprocess.run([possible_path, "--version"], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    blender_path = possible_path
                    print(f"✅ Blender found: {possible_path}")
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    
    if not blender_path:
        print("⚠️  Blender not found in common locations")
        print("   You can still use demo mode or specify Blender path manually")
    
    print("\n🚀 LAUNCH OPTIONS")
    print("=" * 50)
    print("1. Demo Mode (Shell) - Test without Blender")
    print("2. Demo Mode (TUI) - Visual interface without Blender")
    print("3. Blender Shell - Interactive shell in Blender")
    print("4. Blender Wizard - Original step-by-step in Blender")
    print("5. Manual command help")
    print("6. Exit")
    
    while True:
        choice = input("\nSelect option (1-6): ").strip()
        
        if choice == "1":
            print("\n🖥️  Launching demo shell...")
            os.system("python3 main.py --interface shell")
            break
            
        elif choice == "2":
            print("\n🎨 Launching demo TUI...")
            print("Note: Requires 'pip install textual'")
            os.system("python3 main.py --interface tui")
            break
            
        elif choice == "3":
            if not blender_path:
                print("❌ Blender not found. Please install Blender or specify path manually.")
                continue
            print(f"\n🔧 Launching Blender shell with {blender_path}...")
            cmd = f'"{blender_path}" --background --python main.py'
            print(f"Command: {cmd}")
            os.system(cmd)
            break
            
        elif choice == "4":
            if not blender_path:
                print("❌ Blender not found. Please install Blender or specify path manually.")
                continue
            print(f"\n🧙‍♂️ Launching Blender wizard with {blender_path}...")
            cmd = f'"{blender_path}" --background --python main.py -- --interface wizard'
            print(f"Command: {cmd}")
            os.system(cmd)
            break
            
        elif choice == "5":
            print("\n📚 MANUAL COMMANDS")
            print("=" * 50)
            print("Demo/Testing (no Blender required):")
            print("  python3 main.py --interface shell")
            print("  python3 main.py --interface tui")
            print("")
            print("With Blender (for actual rendering):")
            print("  blender --background --python main.py")
            print("  blender --background --python main.py -- --interface wizard")
            print("  blender your_file.blend --python main.py")
            print("")
            print("From Blender Script Editor:")
            print("  1. Open Blender")
            print("  2. Go to Scripting workspace")
            print("  3. Open main.py")
            print("  4. Click 'Run Script'")
            print("")
            print("Legacy interface (original):")
            print("  blender --background --python render_automation.py")
            break
            
        elif choice == "6":
            print("👋 Goodbye!")
            break
            
        else:
            print("Invalid choice. Please select 1-6.")

if __name__ == "__main__":
    main()