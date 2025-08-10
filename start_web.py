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
    if venv_python.exists() and str(venv_python) != sys.executable:
        print("🔄 Utilizzando l'ambiente virtuale...")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    
    # Add the project directory to Python path
    sys.path.insert(0, str(project_dir))

    print("🚀 Starting Project Prometheus Web Interface...")
    print("📍 Visit: http://localhost:5050")
    print("⏹️  Press Ctrl+C to stop the server")
    print("-" * 50)
    
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