#!/usr/bin/env python3
"""
Demo script showing the complete Blendomatic workflow
"""

import subprocess
import sys
import time

def run_shell_commands():
    """Demonstrate the shell interface with a complete workflow"""
    
    commands = [
        "help",
        "modes",
        "mode fast",
        "garments", 
        "garment mock_garment.json",
        "fabrics",
        "fabric mock_fabric.json",
        "assets",
        "asset Mock Asset",
        "status",
        "render",
        "quit"
    ]
    
    print("🚀 BLENDOMATIC DEMO - Shell Interface")
    print("=" * 50)
    print("This demo shows a complete render workflow using the shell interface.")
    print("Commands will be executed automatically with pauses for readability.\n")
    
    input("Press Enter to start the demo...")
    
    # Create input string
    command_input = "\n".join(commands) + "\n"
    
    try:
        # Run the shell with input
        process = subprocess.Popen(
            [sys.executable, "shell.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(input=command_input, timeout=30)
        
        print("DEMO OUTPUT:")
        print("-" * 50)
        print(stdout)
        
        if stderr:
            print("ERRORS:")
            print("-" * 50)
            print(stderr)
            
    except subprocess.TimeoutExpired:
        print("Demo timed out")
        process.kill()
    except Exception as e:
        print(f"Demo failed: {e}")

def show_architecture_info():
    """Display information about the new architecture"""
    
    print("\n🏗️  BLENDOMATIC ARCHITECTURE")
    print("=" * 50)
    print("""
The new architecture separates concerns into:

📁 Core Files:
  • render_session.py  - Main engine (all business logic)
  • shell.py           - CMD-based interactive shell
  • tui.py             - Textual TUI interface  
  • main.py            - Entry point with interface selection
  • demo_session.py    - Mock version for testing

📁 Legacy:
  • render_automation.py - Original wizard (backward compatibility)

🔄 Key Improvements:
  ✅ Stateful session management
  ✅ Non-linear workflow (change settings in any order)
  ✅ Multiple render without restart
  ✅ Better error handling and validation
  ✅ Multiple UI options
  ✅ Testable without Blender

🖥️  Interface Options:
  • Wizard: python main.py --interface wizard
  • Shell:  python main.py --interface shell  (recommended)
  • TUI:    python main.py --interface tui    (requires textual)
    """)

def main():
    """Main demo function"""
    
    show_architecture_info()
    
    print("\n🎮 DEMO OPTIONS")
    print("=" * 50)
    print("1. Run shell workflow demo")
    print("2. Show help information")
    print("3. Exit")
    
    while True:
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == "1":
            run_shell_commands()
            break
        elif choice == "2":
            print("\n📚 HELP")
            print("=" * 50)
            print("To use the real application:")
            print("  python main.py --interface shell")
            print("  python main.py --interface tui")
            print("  python main.py --interface wizard")
            print("\nFor Blender integration:")
            print("  1. Copy all .py files to your project directory")
            print("  2. Run from within Blender's script editor")
            print("  3. Or run as external script: blender --python main.py")
            break
        elif choice == "3":
            print("👋 Goodbye!")
            break
        else:
            print("Invalid choice. Please select 1, 2, or 3.")

if __name__ == "__main__":
    main()