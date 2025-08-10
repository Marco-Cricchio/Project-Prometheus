#!/usr/bin/env python3
"""
Test script to verify Project Prometheus installation
Run this to check if all dependencies are correctly installed
"""

import sys
import os
from pathlib import Path

def test_imports():
    """Test that all required modules can be imported"""
    print("🧪 Testing Project Prometheus Installation...")
    print("-" * 50)
    
    # Test standard library imports
    try:
        import os
        import sys
        from pathlib import Path
        print("✅ Standard library imports: OK")
    except ImportError as e:
        print(f"❌ Standard library error: {e}")
        return False
    
    # Test Flask
    try:
        import flask
        print(f"✅ Flask {flask.__version__}: OK")
    except ImportError:
        print("❌ Flask: NOT INSTALLED")
        return False
    
    # Test python-dotenv
    try:
        import dotenv
        print("✅ python-dotenv: OK")
    except ImportError:
        print("❌ python-dotenv: NOT INSTALLED") 
        return False
    
    # Test Rich
    try:
        import rich
        print(f"✅ Rich {rich.__version__}: OK")
    except ImportError:
        print("❌ Rich: NOT INSTALLED")
        return False
    
    # Test Google Generative AI (optional)
    try:
        import google.generativeai
        print("✅ Google Generative AI: OK")
    except ImportError:
        print("⚠️  Google Generative AI: NOT INSTALLED (optional)")
    
    return True

def test_project_structure():
    """Test that project files exist"""
    print("\n🗂️  Testing project structure...")
    
    required_files = [
        "cli.py",
        "web_app.py", 
        "start_web.py",
        "start_cli.py",
        "core/orchestrator.py",
        "templates/index.html",
        ".env.example",
        "README.md"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
        else:
            print(f"✅ {file_path}")
    
    if missing_files:
        print(f"\n❌ Missing files: {', '.join(missing_files)}")
        return False
    
    return True

def test_python_version():
    """Test Python version compatibility"""
    print(f"\n🐍 Testing Python version...")
    version = sys.version_info
    
    if version.major == 3 and version.minor >= 9:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro}: Compatible")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro}: Requires Python 3.9+")
        return False

def main():
    """Run all tests"""
    print("🚀 Project Prometheus Installation Test")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 3
    
    if test_python_version():
        tests_passed += 1
    
    if test_imports():
        tests_passed += 1
    
    if test_project_structure():
        tests_passed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {tests_passed}/{total_tests} passed")
    
    if tests_passed == total_tests:
        print("🎉 Installation test PASSED! Project Prometheus is ready to use.")
        print("\nNext steps:")
        print("  • Run: python start_web.py (for web interface)")
        print("  • Run: python start_cli.py (for command line)")
        print("  • Visit: http://localhost:5050 (after starting web interface)")
        return True
    else:
        print("❌ Installation test FAILED. Please check the errors above.")
        print("\nRecommended fixes:")
        print("  • Ensure you're using Python 3.9+")
        print("  • Install missing dependencies with: pip install -r requirements.txt")
        print("  • Or run the setup script: python setup.py")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)