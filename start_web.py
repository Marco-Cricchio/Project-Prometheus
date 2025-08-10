#!/usr/bin/env python3
"""
Project Prometheus - Web Interface Launcher
Starts the web interface on http://localhost:5050
"""

import os
import sys
from pathlib import Path

# Change to the project directory
os.chdir(Path(__file__).parent)

# Add the project directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    print("🚀 Starting Project Prometheus Web Interface...")
    print("📍 Visit: http://localhost:5050")
    print("⏹️  Press Ctrl+C to stop the server")
    print("-" * 50)
    
    try:
        from web_app import app
        app.run(debug=False, host='0.0.0.0', port=5050, threaded=True)
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting web server: {e}")
        sys.exit(1)