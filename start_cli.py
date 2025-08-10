#!/usr/bin/env python3
"""
Project Prometheus - CLI Interface Launcher
Starts the command-line interface for Project Prometheus
"""

import os
import sys
from pathlib import Path

# Change to the project directory
os.chdir(Path(__file__).parent)

# Add the project directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    try:
        from cli import main
        main()
    except KeyboardInterrupt:
        print("\n\nShutting down Prometheus CLI...")
    except Exception as e:
        print(f"\n❌ Error starting CLI: {e}")
        sys.exit(1)