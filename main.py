"""
Updated Blender Render Automation Entry Point
Now supports multiple UI modes: CLI wizard, shell, and TUI
"""
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="Blendomatic - Blender Render Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available interfaces:
  wizard  - Original step-by-step wizard (default)
  shell   - Interactive shell with commands (recommended)  
  tui     - Full TUI interface (requires textual package)

Examples:
  python render_automation.py                    # Run wizard
  python render_automation.py --interface shell  # Run shell
  python render_automation.py --interface tui    # Run TUI
        """
    )
    
    parser.add_argument(
        '--interface', '-i',
        choices=['wizard', 'shell', 'tui'],
        default='wizard',
        help='Interface type to use (default: wizard)'
    )
    
    args = parser.parse_args()
    
    if args.interface == 'shell':
        try:
            from shell import main as shell_main
            shell_main()
        except ImportError as e:
            print(f"Error importing shell interface: {e}")
            sys.exit(1)
    
    elif args.interface == 'tui':
        try:
            from simple_tui import main as simple_tui_main
            simple_tui_main()
        except ImportError as e:
            print(f"Error: TUI interface requires 'textual' package.")
            print("Install with: pip install textual")
            print("Or use --interface shell for a simpler interface")
            print("\nFalling back to shell interface...")
            try:
                from shell import main as shell_main
                shell_main()
            except ImportError:
                print("Shell interface also not available. Using wizard.")
                run_wizard()
        except Exception as e:
            print(f"TUI error: {e}")
            print("Falling back to shell interface...")
            try:
                from shell import main as shell_main
                shell_main()
            except ImportError:
                run_wizard()
    
    else:  # wizard (default)
        # Run original wizard interface
        run_wizard()


def run_wizard():
    """Original wizard-style interface for backward compatibility"""
    import bpy
    import json
    import os
    from pathlib import Path
    
    # Import the new render session
    try:
        from render_session import RenderSession
    except ImportError:
        print("Error: Could not import render_session module")
        sys.exit(1)
    
    def select_from_list(items, prompt="Select an option:"):
        """Interactive selection helper"""
        for i, item in enumerate(items):
            print(f"{i}: {item}")
        while True:
            try:
                choice = input(f"{prompt} (number) > ")
                if choice.isdigit() and 0 <= int(choice) < len(items):
                    return items[int(choice)]
                print("[ERROR] Invalid selection, try again.")
            except (KeyboardInterrupt, EOFError):
                print("\nAborted by user")
                sys.exit(0)
    
    print("="*60)
    print("         BLENDOMATIC RENDER WIZARD")
    print("="*60)
    
    try:
        # Initialize session
        session = RenderSession()
        print("[INFO] Render session initialized")
        
        # Select mode
        modes = session.list_modes()
        mode = select_from_list(modes, "Choose render mode")
        session.set_mode(mode)
        
        # Select garment
        garments = session.list_garments()
        garment = select_from_list(garments, "Choose a garment")
        print("[INFO] Loading garment blend file... (this may take a moment)")
        session.set_garment(garment)
        
        # Select fabric
        fabrics = session.list_fabrics()
        fabric = select_from_list(fabrics, "Choose a fabric")
        session.set_fabric(fabric)
        
        # Select asset
        assets = session.list_assets()
        if not assets:
            print("[ERROR] No assets found in garment")
            return
        
        asset = select_from_list(assets, "Choose an asset")
        session.set_asset(asset)
        
        # Show final status
        print("\n" + "="*60)
        print("         RENDER CONFIGURATION")
        print("="*60)
        state = session.get_state()
        print(f"Mode:    {state['mode']}")
        print(f"Garment: {state['garment_name']}")
        print(f"Fabric:  {state['fabric_name']}")
        print(f"Asset:   {state['asset_name']}")
        print("="*60)
        
        # Confirm render
        confirm = input("\nStart render? (y/N): ").lower().strip()
        if confirm in ['y', 'yes']:
            print("[RENDER] Starting render...")
            output_path = session.render()
            print(f"[RENDER] ✅ Render completed!")
            print(f"[RENDER] Output: {output_path}")
        else:
            print("Render cancelled")
            
    except KeyboardInterrupt:
        print("\n\nAborted by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()