#!/usr/bin/env python3
"""
Quick test for the fixed Blender TUI
Tests that it can import and initialize without the log conflict
"""

def test_tui_import():
    """Test that the TUI can be imported without errors"""
    print("🧪 Testing TUI Import...")
    
    try:
        # This should work even without textual installed (due to dummy classes)
        from blender_tui import BlenderTUIApp
        print("✅ TUI import successful")
        return True
    except Exception as e:
        print(f"❌ TUI import failed: {e}")
        return False

def test_textual_available():
    """Test if textual is available"""
    print("🧪 Testing Textual Availability...")
    
    try:
        import textual
        print("✅ Textual is available")
        return True
    except ImportError:
        print("❌ Textual not installed (pip install textual)")
        return False

def test_app_creation():
    """Test that the app can be created without log conflicts"""
    print("🧪 Testing App Creation...")
    
    try:
        from blender_tui import BlenderTUIApp
        app = BlenderTUIApp("blender")
        
        # Test that the app has proper attributes
        if hasattr(app, 'write_message'):
            print("✅ App has write_message method")
        else:
            print("❌ App missing write_message method")
            return False
            
        # Test that Textual's log is not interfered with
        if hasattr(app, 'log'):
            print("✅ App has Textual log attribute")
        else:
            print("⚠️  App missing log attribute (may be OK)")
        
        print("✅ App creation successful")
        return True
        
    except Exception as e:
        print(f"❌ App creation failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔬 BLENDER TUI FIX VERIFICATION")
    print("=" * 50)
    
    tests = [
        test_tui_import,
        test_textual_available, 
        test_app_creation
    ]
    
    results = []
    for test in tests:
        results.append(test())
        print()
    
    passed = sum(results)
    total = len(results)
    
    print("📊 RESULTS")
    print("=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! TUI should work over SSH now.")
    elif passed > 0:
        print("⚠️  Some tests passed. May work with textual installed.")
    else:
        print("❌ Tests failed. Check error messages above.")
    
    print("\n💡 TO USE:")
    print("  pip install textual")
    print("  python blender_tui.py")

if __name__ == "__main__":
    main()