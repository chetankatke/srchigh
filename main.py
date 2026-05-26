#!/usr/bin/env python3
"""
Convenience runner — use `python3 main.py` directly from the project root.
Installed via pip as `srchigh` command for system-wide use.
"""
import sys
import os

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from srchigh.main import run_cli

if __name__ == "__main__":
    run_cli()
