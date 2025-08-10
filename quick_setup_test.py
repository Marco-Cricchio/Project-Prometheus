#!/usr/bin/env python3
"""
Quick test of the setup process without actually running it
This simulates what setup.py does to verify the logic works
"""

import sys
import os
from pathlib import Path

def test_environment_detection():
    """Test virtual environment detection logic"""
    print("🧪 Testing environment detection...")
    
    # Test if we're in a virtual environment
    in_venv = sys.prefix != sys.base_prefix
    print(f"In virtual environment: {in_venv}")
    print(f"sys.prefix: {sys.prefix}")
    print(f"sys.base_prefix: {sys.base_prefix}")
    
    # Test .venv detection
    venv_exists = Path(".venv").exists()
    print(f".venv directory exists: {venv_exists}")
    
    if venv_exists:
        venv_python = Path(".venv/bin/python")
        print(f".venv/bin/python exists: {venv_python.exists()}")
    
    # Test Python version
    version = sys.version_info
    compatible = version.major == 3 and version.minor >= 9
    print(f"Python {version.major}.{version.minor}.{version.micro} - Compatible: {compatible}")

def test_import_availability():
    """Test if dependencies are available to current Python"""
    print("\n🔍 Testing current environment imports...")
    
    required_modules = ["flask", "dotenv", "rich", "google.generativeai"]
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}: Available")
        except ImportError:
            print(f"❌ {module}: Not available")

if __name__ == "__main__":
    print("🚀 Quick Setup Environment Test")
    print("=" * 40)
    test_environment_detection()
    test_import_availability()
    print("=" * 40)
    print("✨ This helps diagnose setup.py behavior without running the full setup")