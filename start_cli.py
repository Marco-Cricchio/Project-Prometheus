#!/usr/bin/env python3
"""
Project Prometheus - CLI Interface Launcher
Starts the command-line interface for Project Prometheus
"""

import os
import sys
from pathlib import Path

def main():
    """Main launcher function"""
    # Change to the project directory
    os.chdir(Path(__file__).parent)
    
    # Add the project directory to Python path
    sys.path.insert(0, str(Path(__file__).parent))
    
    try:
        from cli import main as cli_main
        cli_main()
    except KeyboardInterrupt:
        print("\n\nShutting down Prometheus CLI...")
    except Exception as e:
        print(f"\n❌ Error starting CLI: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()