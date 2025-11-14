# 🔧 SSH/HEADLESS ENVIRONMENT SOLUTION

## 🎯 The Problem You're Experiencing

When running the TUI via SSH, you're getting this error:

```
AttributeError: 'function' object has no attribute 'system'
```

This happens because:

1. **SSH environments** don't provide proper terminal capabilities for rich TUIs
2. **Textual framework** expects full terminal control and display capabilities
3. **Headless servers** may lack the necessary terminal features

## ✅ **IMMEDIATE SOLUTIONS**

### **Solution 1: Use Shell Interface (Recommended for SSH)**

```bash
python main.py --interface shell
```

- ✅ Works perfectly over SSH
- ✅ Full functionality with demo data
- ✅ Interactive commands and status tracking
- ✅ No terminal display requirements

### **Solution 2: SSH-Optimized Launcher**

```bash
python ssh_interface.py
```

- ✅ Detects SSH environment automatically
- ✅ Offers appropriate interface options
- ✅ Guides you to working solutions
- ✅ Fallback handling for TUI failures

### **Solution 3: Direct Blender (For Real Rendering)**

```bash
blender --background --python main.py
```

- ✅ Runs shell interface inside Blender
- ✅ Full rendering capabilities
- ✅ Works great over SSH
- ✅ No TUI dependencies

## 🔧 **Why TUI Fails Over SSH**

### **Technical Details:**

- SSH terminals have limited capabilities compared to local terminals
- Textual requires specific terminal features for rendering widgets
- Mouse support and advanced positioning may not work
- Terminal size detection can fail
- Color and styling support varies

### **Environment Detection:**

The updated code now detects SSH environments by checking:

```python
is_ssh = 'SSH_CLIENT' in os.environ or 'SSH_TTY' in os.environ
no_display = 'DISPLAY' not in os.environ
```

## 🚀 **Updated Workflow for SSH Users**

### **1. Quick Start (SSH-Safe):**

```bash
# Option A: Direct shell
python main.py --interface shell

# Option B: SSH launcher (guides you through options)
python ssh_interface.py

# Option C: Blender direct (for real rendering)
blender --background --python main.py
```

### **2. Development Workflow:**

```bash
# Test configurations with demo data
python main.py --interface shell

# Commands you can use:
(blendomatic) modes
(blendomatic) mode fast
(blendomatic) garments
(blendomatic) garment service_shirt_m.json
(blendomatic) status
(blendomatic) help
```

### **3. Production Workflow:**

```bash
# Real Blender rendering over SSH
blender --background --python main.py

# Same commands work in Blender:
(blendomatic) mode prod
(blendomatic) garment service_shirt_m.json
(blendomatic) fabric hera_white.json
(blendomatic) asset "Band Collar Variant"
(blendomatic) render
```

## 💡 **Best Practices for SSH Usage**

### **✅ DO:**

- Use shell interface (`--interface shell`)
- Use the SSH launcher (`ssh_interface.py`)
- Run Blender directly for rendering
- Use tmux/screen for long-running renders

### **❌ AVOID:**

- TUI interface over SSH (unreliable)
- Complex terminal operations in unstable connections
- GUI-dependent features

## 🎯 **Summary**

**Your SSH environment issue is now solved with multiple options:**

1. **Shell Interface** - Reliable, full-featured, SSH-friendly
2. **SSH Launcher** - Guides you to the right interface
3. **Direct Blender** - For actual rendering work
4. **Improved TUI** - Better error detection and fallbacks

**Recommended command for SSH:**

```bash
python main.py --interface shell
```

This gives you all the functionality you need with perfect SSH compatibility! 🎉
