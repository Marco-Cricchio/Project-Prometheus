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
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    # Check for virtual environment and activate if available
    venv_python = project_dir / ".venv" / "bin" / "python"
    if venv_python.exists() and str(venv_python) != sys.executable:
        print("🔄 Utilizzando l'ambiente virtuale...")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)
    
    # Add the project directory to Python path
    sys.path.insert(0, str(project_dir))
    
    print("🚀 Starting Project Prometheus CLI...")
    print("⏹️  Press Ctrl+C to exit gracefully")
    print("-" * 50)
    
    try:
        from cli import main as cli_main
        cli_main()
    except KeyboardInterrupt:
        print("\n\n🛑 Alla prossima! CLI chiusa dall'utente.")
        print("👋 See you soon!")
        print("🔧 Grazie per aver usato Project Prometheus!")
    except ImportError as e:
        print(f"\n❌ Errore di importazione: {e}")
        print("💡 Suggerimento: Esegui 'python setup.py' o attiva l'ambiente virtuale:")
        print("   source .venv/bin/activate && python start_cli.py")
        print("📖 Vedi README.md per le istruzioni di installazione.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Errore nell'avvio del CLI: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()