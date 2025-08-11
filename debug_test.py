#!/usr/bin/env python3
"""
Test diretto per debug logging di Prometheus
"""
import os
import sys
from pathlib import Path

# Change to project directory
project_dir = Path(__file__).parent
os.chdir(project_dir)
sys.path.insert(0, str(project_dir))

print("🧪 DEBUG TEST SCRIPT")
print(f"📁 Working directory: {os.getcwd()}")
print(f"🐍 Python executable: {sys.executable}")
print("-" * 40)

try:
    print("📦 Importing Orchestrator...")
    from core.orchestrator import Orchestrator
    print("✅ Orchestrator imported successfully!")
    
    # Check debug log file
    log_file = os.path.expanduser('~/prometheus_debug.log')
    print(f"🔍 Checking debug log: {log_file}")
    
    if os.path.exists(log_file):
        size = os.path.getsize(log_file)
        print(f"✅ Debug log exists: {size} bytes")
        print("📄 Recent log entries:")
        with open(log_file, 'r') as f:
            lines = f.readlines()
            for line in lines[-10:]:  # Last 10 lines
                print(f"   {line.strip()}")
    else:
        print("🔄 Creating Orchestrator to initialize logging...")
        test_orchestrator = Orchestrator(session_id="debug_test", lang='en')
        print("✅ Orchestrator created!")
        
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            print(f"✅ Debug log created: {size} bytes")
        else:
            print("❌ Debug log still not found!")

except Exception as e:
    print(f"❌ EXCEPTION: {e}")
    import traceback
    traceback.print_exc()

print("-" * 40)
print("🏁 Test completed")