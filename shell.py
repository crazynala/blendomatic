"""
Simple CMD-based shell interface for Blender Render Automation
No external dependencies - uses Python stdlib only
"""
import cmd
import os
import sys
from typing import Optional

try:
    from render_session import RenderSession
except ImportError:
    try:
        from demo_session import RenderSession
        print("Info: Using demo session (Blender not available)")
    except ImportError:
        print("Warning: Neither render_session nor demo_session found.")
        RenderSession = None


class BlendomaticShell(cmd.Cmd):
    """Interactive shell for Blender render automation"""
    
    intro = """
╔════════════════════════════════════════════════╗
║              BLENDOMATIC SHELL                 ║
║          Blender Render Automation             ║
╚════════════════════════════════════════════════╝

Type 'help' or '?' to list commands.
Type 'status' to see current session state.
    """
    
    prompt = "(blendomatic) "
    
    def __init__(self, session: Optional['RenderSession'] = None):
        super().__init__()
        self.session = session
        if not self.session and RenderSession:
            try:
                self.session = RenderSession()
                print("[INFO] Render session initialized successfully")
            except Exception as e:
                print(f"[ERROR] Failed to initialize render session: {e}")
                print("Some commands may not work properly.")
    
    def do_status(self, arg):
        """Show current render session status"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        state = self.session.get_state()
        print("\n" + "="*50)
        print("           RENDER SESSION STATUS")
        print("="*50)
        print(f"Mode:           {state.get('mode', 'Not set')}")
        print(f"Garment:        {state.get('garment_name', 'Not set')}")
        print(f"Fabric:         {state.get('fabric_name', 'Not set')}")
        print(f"Asset:          {state.get('asset_name', 'Not set')}")
        print("-"*50)
        
        ready_icon = "✅" if state.get('ready_to_render') else "❌"
        garment_icon = "✅" if state.get('garment_loaded') else "❌"
        fabric_icon = "✅" if state.get('fabric_applied') else "❌"
        
        print(f"Ready to Render: {ready_icon}")
        print(f"Garment Loaded:  {garment_icon}")
        print(f"Fabric Applied:  {fabric_icon}")
        print("="*50 + "\n")
    
    # ----- Mode Commands -----
    
    def do_modes(self, arg):
        """List available render modes"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        modes = self.session.list_modes()
        print("\nAvailable render modes:")
        for i, mode in enumerate(modes, 1):
            current = " (CURRENT)" if mode == self.session.mode else ""
            print(f"  {i}. {mode}{current}")
        print()
    
    def do_mode(self, arg):
        """Set render mode: mode <name>"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        if not arg:
            print("Usage: mode <mode_name>")
            self.do_modes("")
            return
            
        try:
            self.session.set_mode(arg.strip())
            print(f"[INFO] Set render mode: {arg.strip()}")
        except Exception as e:
            print(f"[ERROR] {e}")
    
    # ----- Garment Commands -----
    
    def do_garments(self, arg):
        """List available garments"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        garments = self.session.list_garments()
        print("\nAvailable garments:")
        for i, garment in enumerate(garments, 1):
            current = " (CURRENT)" if (self.session.garment and 
                                     garment == f"{self.session.garment['name']}.json") else ""
            print(f"  {i}. {garment}{current}")
        print()
    
    def do_garment(self, arg):
        """Set garment: garment <filename.json>"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        if not arg:
            print("Usage: garment <filename.json>")
            self.do_garments("")
            return
            
        try:
            print(f"[INFO] Loading garment blend file... (this may take a moment)")
            self.session.set_garment(arg.strip())
            print(f"[INFO] Set garment: {arg.strip()}")
        except Exception as e:
            print(f"[ERROR] {e}")
    
    # ----- Fabric Commands -----
    
    def do_fabrics(self, arg):
        """List available fabrics"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        fabrics = self.session.list_fabrics()
        print("\nAvailable fabrics:")
        for i, fabric in enumerate(fabrics, 1):
            current = " (CURRENT)" if (self.session.fabric and 
                                     fabric == f"{self.session.fabric['name']}.json") else ""
            print(f"  {i}. {fabric}{current}")
        print()
    
    def do_fabric(self, arg):
        """Set fabric: fabric <filename.json>"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        if not arg:
            print("Usage: fabric <filename.json>")
            self.do_fabrics("")
            return
            
        try:
            self.session.set_fabric(arg.strip())
            print(f"[INFO] Set fabric: {arg.strip()}")
        except Exception as e:
            print(f"[ERROR] {e}")
    
    # ----- Asset Commands -----
    
    def do_assets(self, arg):
        """List available assets for current garment"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        if not self.session.garment:
            print("[ERROR] Select a garment first")
            return
            
        assets = self.session.list_assets()
        if not assets:
            print("[WARN] No assets found for current garment")
            return
            
        print("\nAvailable assets:")
        for i, asset in enumerate(assets, 1):
            current = " (CURRENT)" if (self.session.asset and 
                                     asset == self.session.asset['name']) else ""
            print(f"  {i}. {asset}{current}")
        print()
    
    def do_asset(self, arg):
        """Set asset: asset <name>"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        if not arg:
            print("Usage: asset <asset_name>")
            self.do_assets("")
            return
            
        try:
            self.session.set_asset(arg.strip())
            print(f"[INFO] Set asset: {arg.strip()}")
        except Exception as e:
            print(f"[ERROR] {e}")
    
    # ----- Render Commands -----
    
    def do_render(self, arg):
        """Perform render with current settings"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        if not self.session.is_ready_to_render():
            print("[ERROR] Cannot render: Missing required selections")
            self.do_status("")
            return
            
        try:
            print("[RENDER] Starting render... (this may take several minutes)")
            output_path = self.session.render()
            print(f"[RENDER] ✅ Render completed successfully!")
            print(f"[RENDER] Output saved to: {output_path}")
        except Exception as e:
            print(f"[RENDER] ❌ Render failed: {e}")
    
    # ----- Utility Commands -----
    
    def do_clear(self, arg):
        """Clear the screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def do_refresh(self, arg):
        """Refresh configuration (reload JSON files)"""
        if not self.session:
            print("[ERROR] No render session available")
            return
            
        try:
            # Reinitialize session to reload configs
            old_selections = {
                'mode': self.session.mode,
                'garment': self.session.garment,
                'fabric': self.session.fabric,
                'asset': self.session.asset
            }
            
            self.session.__init__()
            print("[INFO] Configuration refreshed")
            
            # Show what was reset
            if any(old_selections.values()):
                print("[WARN] Previous selections have been reset")
                
        except Exception as e:
            print(f"[ERROR] Failed to refresh: {e}")
    
    def do_help(self, arg):
        """Show help for commands"""
        if arg:
            # Show help for specific command
            super().do_help(arg)
        else:
            # Show custom help overview
            print("\n" + "="*60)
            print("                    COMMAND HELP")
            print("="*60)
            print("SETUP COMMANDS:")
            print("  modes                 - List available render modes")
            print("  mode <name>           - Set render mode")
            print("  garments              - List available garments")
            print("  garment <file.json>   - Set garment")
            print("  fabrics               - List available fabrics")
            print("  fabric <file.json>    - Set fabric")
            print("  assets                - List assets for current garment")
            print("  asset <name>          - Set asset")
            print()
            print("RENDER COMMANDS:")
            print("  render                - Start rendering")
            print("  status                - Show current session status")
            print()
            print("UTILITY COMMANDS:")
            print("  refresh               - Reload configuration files")
            print("  clear                 - Clear screen")
            print("  help [command]        - Show help")
            print("  quit / exit           - Exit the shell")
            print("="*60)
            print("\nTIP: Use TAB for command completion")
            print("TIP: Use UP/DOWN arrows for command history\n")
    
    def do_quit(self, arg):
        """Exit the shell"""
        print("\n👋 Thanks for using Blendomatic!")
        return True
    
    def do_exit(self, arg):
        """Exit the shell"""
        return self.do_quit(arg)
    
    def do_EOF(self, arg):
        """Handle Ctrl+D"""
        print()  # New line for cleaner exit
        return True
    
    def emptyline(self):
        """Do nothing on empty line (override default repeat behavior)"""
        pass
    
    def default(self, line):
        """Handle unknown commands"""
        print(f"Unknown command: {line}")
        print("Type 'help' to see available commands.")


def main():
    """Entry point for the shell interface"""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(__doc__)
        return
    
    try:
        shell = BlendomaticShell()
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()