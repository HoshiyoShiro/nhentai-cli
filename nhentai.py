#!/usr/bin/env python3
"""
NHentai CLI - Standalone entry point
Run this directly: python nhentai.py [command]
"""

import sys
import os

# Add the parent directory to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nhentai_cli.cli import main

if __name__ == "__main__":
    main()