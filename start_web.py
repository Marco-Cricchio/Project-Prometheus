#!/usr/bin/env python3
"""
Project Prometheus - Web Interface Launcher
Starts the web interface on http://localhost:5050
"""

import os
import sys
from pathlib import Path

def main():
    """Main launcher function"""
    # Change to the project directory
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    # Check for virtual environment and activate if available
    venv_python = project_dir / ".venv" / "bin" / "python"
    print(f"🔧 Debug: venv_python = {venv_python}")
    print(f"🔧 Debug: sys.executable = {sys.executable}")
    print(f"🔧 Debug: venv exists = {venv_python.exists()}")
    print(f"🔧 Debug: same executable = {str(venv_python) == sys.executable}")
    
    if venv_python.exists() and str(venv_python) != sys.executable:
        print("🔄 Utilizzando l'ambiente virtuale...")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    
    # Add the project directory to Python path
    sys.path.insert(0, str(project_dir))

    print("🚀 Starting Project Prometheus Web Interface...")
    print("📍 Visit: http://localhost:5050")
    print("⏹️  Press Ctrl+C to stop the server")
    print("-" * 50)
    
    # Initialize debug logging (after venv switch)
    print("🐛 Debug logging attivo: ~/prometheus_debug.log")
    print("🧪 Testing debug log initialization...")
    
    try:
        # Force orchestrator import to create log file
        from core.orchestrator import Orchestrator
        log_file_path = os.path.expanduser('~/prometheus_debug.log')
        
        if os.path.exists(log_file_path):
            print(f"✅ Debug log file exists and has {os.path.getsize(log_file_path)} bytes")
        else:
            print("🔄 Creating debug log file...")
            test_orchestrator = Orchestrator(session_id="test_startup", lang='en')
            print("✅ Orchestrator created successfully - debug log should be active")
            if os.path.exists(log_file_path):
                print(f"✅ Debug log file created with {os.path.getsize(log_file_path)} bytes")
        
        print("-" * 30)
    except Exception as e:
        print(f"❌ Error initializing debug logging: {e}")
        print("-" * 30)
    
    try:
        from web_app import app
        app.run(debug=False, host='0.0.0.0', port=5050, threaded=True)
    except KeyboardInterrupt:
        print("\n\n🛑 Alla prossima! Il server è stato fermato.")
        print("👋 See you soon!")
    except ImportError as e:
        print(f"\n❌ Errore di importazione: {e}")
        print("💡 Suggerimento: Esegui 'python setup.py' o attiva l'ambiente virtuale:")
        print("   source .venv/bin/activate && python start_web.py")
        print("📖 Vedi README.md per le istruzioni di installazione alternative.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Errore nell'avvio del server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()