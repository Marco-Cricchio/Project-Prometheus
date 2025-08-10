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
    
    # Check if we're already in the venv to avoid re-exec
    venv_python = project_dir / ".venv" / "bin" / "python"
    # FIX: Better venv detection using sys.prefix
    already_in_venv = sys.prefix != sys.base_prefix and str(project_dir / ".venv") in sys.prefix
    
    # Check for virtual environment and activate if available (only if not already in venv)
    if venv_python.exists() and not already_in_venv:
        print("🔄 Utilizzando l'ambiente virtuale...")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    
    # Add the project directory to Python path
    sys.path.insert(0, str(project_dir))
    
    print("🚀 Starting Project Prometheus Web Interface...")
    print("📍 Visit: http://localhost:5050")
    print("⏹️  Press Ctrl+C to stop the server")
    print("-" * 50)
    
    # Debug environment details - SEMPRE
    print(f"🔧 Current Python: {sys.executable}")
    print(f"🔧 Virtual env path: {venv_python}")  
    print(f"🔧 Already in venv: {already_in_venv}")
    print("-" * 20)
    
    # FORCE debug logging SEMPRE - no conditions
    print("🐛 FORCING Debug logging initialization...")
    try:
        from core.orchestrator import Orchestrator
        log_file_path = os.path.expanduser('~/prometheus_debug.log')
        print(f"🐛 Log file path: {log_file_path}")
        
        if os.path.exists(log_file_path):
            print(f"✅ Debug log file EXISTS with {os.path.getsize(log_file_path)} bytes")
        else:
            print("🔄 Creating debug log file NOW...")
            test_orchestrator = Orchestrator(session_id="test_startup_force", lang='en')
            print("✅ Orchestrator created successfully")
            if os.path.exists(log_file_path):
                print(f"✅ Debug log file CREATED with {os.path.getsize(log_file_path)} bytes")
            else:
                print("❌ Debug log file STILL NOT FOUND after orchestrator creation!")
        
        print("-" * 30)
    except Exception as e:
        print(f"❌ EXCEPTION in debug logging: {e}")
        import traceback
        traceback.print_exc()
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