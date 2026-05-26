import os
import pytest
from unittest.mock import MagicMock

def test_gui_controller_default_state():
    """Verify that the GUI controller initializes with correct default values."""
    from srchigh.gui import GuiController
    
    ctrl = GuiController()
    assert ctrl.search_term == ""
    assert ctrl.count == 5
    assert ctrl.court == ""
    assert ctrl.from_date == ""
    assert ctrl.to_date == ""
    assert ctrl.is_running is False

def test_gui_controller_validation():
    """Verify that input parameters validation works correctly."""
    from srchigh.gui import GuiController
    
    ctrl = GuiController()
    
    # Empty search term should fail validation
    assert ctrl.validate() is False
    assert "search term" in ctrl.error_message.lower()
    
    # Valid search term should pass validation
    ctrl.search_term = "divorce"
    assert ctrl.validate() is True
    
    # Invalid date format should fail validation
    ctrl.from_date = "2024/01/01"
    assert ctrl.validate() is False
    assert "date" in ctrl.error_message.lower()
    
    # Valid date format should pass validation
    ctrl.from_date = "01-01-2024"
    assert ctrl.validate() is True

def test_gui_controller_output_redirection():
    """Verify that controller correctly handles and routes status message logs."""
    from srchigh.gui import GuiController
    
    ctrl = GuiController()
    log_messages = []
    
    def dummy_logger(msg):
        log_messages.append(msg)
        
    ctrl.on_log = dummy_logger
    ctrl.log("Test message")
    assert log_messages == ["Test message"]

def test_gui_controller_run_scraper_triggers_background():
    """Verify that run_scraper sets is_running, runs in background, and calls on_complete."""
    from srchigh.gui import GuiController
    
    ctrl = GuiController()
    ctrl.search_term = "test"
    
    # We mock the actual session run method to avoid hitting the network in tests
    mock_run = MagicMock()
    ctrl._run_core = mock_run
    
    completed = False
    def on_complete():
        nonlocal completed
        completed = True
        
    ctrl.run_scraper(on_complete=on_complete)
    
    # Since it runs in a background thread, let's wait for it to finish
    if ctrl._thread:
        ctrl._thread.join(timeout=2.0)
        
    assert completed is True
    assert ctrl.is_running is False
    assert mock_run.called is True
