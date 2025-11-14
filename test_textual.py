#!/usr/bin/env python3

"""Test what SelectionList.selected returns in Textual"""

try:
    from textual.widgets import SelectionList
    
    # Create a selection list and add some options
    selection_list = SelectionList()
    selection_list.add_option(("Option 1", "value1"))
    selection_list.add_option(("Option 2", "value2"))
    
    print("SelectionList created successfully")
    print(f"Options: {len(selection_list._options)}")
    
    # Test selection (this won't work without running in a Textual app)
    print("Note: This test shows that SelectionList works, but selection testing requires a running Textual app")
    
except ImportError as e:
    print(f"Textual not available: {e}")
    print("This explains why the TUI isn't working - install with: pip install textual")
