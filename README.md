# Blendomatic - Blender Render Automation

A rearchitected Blender automation tool with multiple interface options for efficient 3D rendering workflows.

## 🏗️ Architecture Overview

The application is now built with a clean separation of concerns:

- **`render_session.py`** - Core engine with all business logic
- **`shell.py`** - CMD-based interactive shell (recommended)
- **`tui.py`** - Full TUI interface using Textual framework
- **`main.py`** - Entry point with interface selection
- **`render_automation.py`** - Legacy wizard interface (backward compatibility)

## 🚀 Quick Start

### Option 1: Interactive Shell (Recommended)

```bash
python main.py --interface shell
```

The shell provides a command-line interface with:

- Tab completion
- Command history
- Flexible workflow (change settings in any order)
- Status tracking
- Built-in help system

### Option 2: Full TUI Interface

```bash
# First install Textual
pip install textual

# Then run TUI
python main.py --interface tui
```

The TUI provides:

- Visual panels and selections
- Real-time status updates
- Mouse and keyboard navigation
- Collapsible sections
- Integrated logging

### Option 3: Original Wizard

```bash
python main.py --interface wizard
# or
python render_automation.py
```

## 💻 Installation

### For Blender Users

1. Copy all files to your project directory
2. For TUI interface, install Textual in Blender's Python:
   ```bash
   /path/to/blender/python/bin/pip install textual
   ```

### Standalone Usage (Development/Testing)

```bash
git clone <repository>
cd blendomatic
pip install -r requirements.txt
```

## 📋 Shell Commands Reference

```
SETUP COMMANDS:
  modes                 - List available render modes
  mode <name>           - Set render mode
  garments              - List available garments
  garment <file.json>   - Set garment
  fabrics               - List available fabrics
  fabric <file.json>    - Set fabric
  assets                - List assets for current garment
  asset <name>          - Set asset

RENDER COMMANDS:
  render                - Start rendering
  status                - Show current session status

UTILITY COMMANDS:
  refresh               - Reload configuration files
  clear                 - Clear screen
  help [command]        - Show help
  quit / exit           - Exit the shell
```

## 🔧 Configuration Files

The system uses the same JSON configuration files as before:

- **`render_config.json`** - Render modes and settings
- **`garments/*.json`** - Garment definitions with blend files and assets
- **`fabrics/*.json`** - Fabric materials and textures

## 🎯 Usage Examples

### Shell Workflow

```bash
(blendomatic) modes
- fast
- prod
- preview

(blendomatic) mode prod
[INFO] Set render mode: prod

(blendomatic) garments
- service_shirt_m.json

(blendomatic) garment service_shirt_m.json
[INFO] Loading garment blend file... (this may take a moment)
[INFO] Set garment: service_shirt_m.json

(blendomatic) fabrics
- hera_white.json

(blendomatic) fabric hera_white.json
[INFO] Set fabric: hera_white.json

(blendomatic) assets
- Band Collar Variant
- Regular Collar Variant

(blendomatic) asset "Band Collar Variant"
[INFO] Set asset: Band Collar Variant

(blendomatic) status
==================================================
           RENDER SESSION STATUS
==================================================
Mode:           prod
Garment:        Service Shirt (M)
Fabric:         Hera White
Asset:          Band Collar Variant
--------------------------------------------------
Ready to Render: ✅
Garment Loaded:  ✅
Fabric Applied:  ✅
==================================================

(blendomatic) render
[RENDER] Starting render... (this may take several minutes)
[RENDER] ✅ Render completed successfully!
[RENDER] Output saved to: renders/service_shirt_M/service_shirt_M-hera_white-band_collar.png
```

## 🎨 Interface Comparison

| Feature              | Wizard      | Shell      | TUI            |
| -------------------- | ----------- | ---------- | -------------- |
| **Ease of Use**      | Simple      | Moderate   | Easy           |
| **Flexibility**      | Linear only | Full       | Full           |
| **Multiple Renders** | No          | Yes        | Yes            |
| **Visual Feedback**  | Minimal     | Text-based | Rich visual    |
| **Dependencies**     | None        | None       | Textual        |
| **Batch Operations** | No          | Possible   | Future feature |

## 🛠️ Development

### Key Components

1. **RenderSession Class**

   - Manages all state (mode, garment, fabric, asset)
   - Provides validation and error handling
   - Encapsulates all Blender operations
   - UI-agnostic design

2. **Interface Layers**
   - Shell: cmd.Cmd-based REPL
   - TUI: Textual framework widgets
   - Wizard: Original linear flow

### Adding New Features

To add new functionality:

1. Add methods to `RenderSession` class
2. Expose via shell commands in `BlendomaticShell`
3. Add TUI widgets/screens as needed
4. Update help and documentation

## 🐛 Troubleshooting

### Common Issues

**Import errors when running in Blender:**

- Ensure all .py files are in Blender's script path
- Use absolute imports if necessary

**TUI not working:**

- Install textual: `pip install textual`
- Check terminal compatibility
- Fall back to shell interface

**Blend file not loading:**

- Verify file paths in garment JSON files
- Ensure Blender has read permissions
- Check for missing texture files

### Debug Mode

Use the shell interface with verbose error reporting for debugging:

```bash
python main.py --interface shell
(blendomatic) status  # Check current state
(blendomatic) refresh # Reload configurations
```

## 📈 Future Enhancements

- Batch rendering support
- Configuration validation
- Render queue management
- Web-based interface
- Plugin system for custom processors
- Advanced material node setups
- Animation rendering support

## 🤝 Contributing

1. All new features should be added to `RenderSession` first
2. UI implementations should be thin wrappers around session methods
3. Maintain backward compatibility with existing JSON configs
4. Add comprehensive error handling and user feedback
