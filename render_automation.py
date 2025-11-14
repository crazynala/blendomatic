"""
Blender Render Automation - Legacy Entry Point
DEPRECATED: Use main.py for the new interface options

This file maintains the original wizard-style interface for backward compatibility.
For the new architecture with multiple UI options, use:
  python main.py --interface wizard  # This same interface
  python main.py --interface shell   # Interactive shell (recommended)
  python main.py --interface tui     # Full TUI (requires textual package)
"""

import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Run the original wizard interface"""
    print("=" * 60)
    print("         BLENDOMATIC (LEGACY INTERFACE)")
    print("=" * 60)
    print("ℹ️  This is the legacy interface.")
    print("🚀 For better experience, try:")
    print("   python main.py --interface shell")
    print("   python main.py --interface tui")
    print("=" * 60)
    
    # Import and run the new main with wizard interface
    try:
        from main import run_wizard
        run_wizard()
    except ImportError as e:
        print(f"Error importing new interface: {e}")
        print("Please ensure all files are in the same directory")
        sys.exit(1)

# Keep original functions for reference/compatibility
# These are now implemented in render_session.py with better architecture

if __name__ == "__main__":
    main()
