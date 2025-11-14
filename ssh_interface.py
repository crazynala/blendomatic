#!/usr/bin/env python3
"""
Blender SSH Interface
Optimized for SSH/headless environments where TUI may not work properly
"""
import os
import sys

def main():
    """Entry point optimized for SSH environments"""
    
    print("🔗 BLENDOMATIC - SSH/HEADLESS MODE")
    print("=" * 50)
    
    # Check environment
    is_ssh = 'SSH_CLIENT' in os.environ or 'SSH_TTY' in os.environ
    no_display = 'DISPLAY' not in os.environ
    
    if is_ssh:
        print("📡 SSH session detected")
    if no_display:
        print("🖥️  No display environment")
    
    print("\n🎯 RECOMMENDED INTERFACES FOR THIS ENVIRONMENT:")
    print("=" * 50)
    print("1. Interactive Shell - Full featured, works great over SSH")
    print("2. Blender Direct - Run shell inside Blender")
    print("3. TUI (risky) - May not work properly over SSH")
    print("4. Exit")
    
    while True:
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == "1":
            print("\n🚀 Starting Interactive Shell...")
            try:
                from shell import main as shell_main
                shell_main()
            except ImportError as e:
                print(f"❌ Error: {e}")
                print("💡 Make sure all files are in the same directory")
            break
            
        elif choice == "2":
            print("\n🔧 Blender Direct Mode")
            print("Run this command:")
            print("  blender --background --python main.py")
            print("")
            print("Or with a specific blend file:")
            print("  blender your_file.blend --background --python main.py")
            break
            
        elif choice == "3":
            print("\n⚠️  Warning: TUI may not work over SSH!")
            confirm = input("Continue anyway? (y/N): ").lower().strip()
            if confirm in ['y', 'yes']:
                try:
                    from blender_tui import main as tui_main
                    tui_main()
                except Exception as e:
                    print(f"❌ TUI failed: {e}")
                    print("🔄 Falling back to shell...")
                    try:
                        from shell import main as shell_main
                        shell_main()
                    except ImportError:
                        print("Shell also not available")
            break
            
        elif choice == "4":
            print("👋 Goodbye!")
            break
            
        else:
            print("Invalid choice. Please select 1-4.")

if __name__ == "__main__":
    main()