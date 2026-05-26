#!/usr/bin/env python3
"""
Convenience runner for the GUI — use `python3 gui.py` directly from the project root.
"""
import sys
import os

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from srchigh.gui import run_gui

if __name__ == "__main__":
    run_gui()
