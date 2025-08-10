#!/usr/bin/env python3
"""
Project Prometheus Smart Launcher

This intelligent launcher automatically handles setup, dependency management,
and provides an easy interface for users to choose how to run Prometheus.
"""

import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    PURPLE = '\033[95m'
    BOLD = '\033[1m'
    END = '\033[0m'


class PrometheusLauncher:
    """Smart launcher for Project Prometheus"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.venv_path = self.project_root / ".venv"
        self.env_file = self.project_root / ".env"
        
    def print_banner(self):
        """Display the Prometheus banner"""
        banner = f"""
{Colors.PURPLE}{Colors.BOLD}
╔══════════════════════════════════════════════════════════╗
║                   🚀 PROJECT PROMETHEUS                   ║
║              AI-Powered Development Assistant            ║
╚══════════════════════════════════════════════════════════╝
{Colors.END}
"""
        print(banner)
    
    def print_status(self, message: str, status: str = "info"):
        """Print formatted status message"""
        icons = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌",
            "working": "⚙️"
        }
        
        colors = {
            "info": Colors.BLUE,
            "success": Colors.GREEN,
            "warning": Colors.YELLOW,
            "error": Colors.RED,
            "working": Colors.PURPLE
        }
        
        icon = icons.get(status, "")
        color = colors.get(status, "")
        print(f"{color}{icon} {message}{Colors.END}")
    
    def check_prerequisites(self):
        """Check if all prerequisites are met"""
        self.print_status("Checking prerequisites...", "working")
        
        issues = []
        
        # Check Python version
        if sys.version_info < (3, 8):
            issues.append("Python 3.8+ required")
        
        # Check if UV is available
        if not shutil.which("uv"):
            issues.append("UV package manager not found")
        
        # Check if setup has been run
        if not self.venv_path.exists():
            issues.append("Virtual environment not found - run setup.py first")
        
        if issues:
            self.print_status("Prerequisites not met:", "error")
            for issue in issues:
                print(f"  • {issue}")
            return False
        
        self.print_status("All prerequisites met!", "success")
        return True
    
    def check_optional_components(self):
        """Check optional components and provide guidance"""
        warnings = []
        
        # Check Claude Code CLI
        if not shutil.which("claude"):
            warnings.append("Claude Code CLI not found - autonomous development will be limited")
        
        # Check .env file
        if not self.env_file.exists():
            warnings.append("No .env file found - Gemini AI features won't be available")
        elif self.env_file.exists():
            # Check if Gemini API key is configured
            with open(self.env_file) as f:
                content = f.read()
                if "GEMINI_API_KEY=" in content and not "your_gemini_api_key_here" in content:
                    # API key seems to be configured
                    pass
                else:
                    warnings.append("Gemini API key not configured - using Claude fallback")
        
        if warnings:
            self.print_status("Optional components missing:", "warning")
            for warning in warnings:
                print(f"  • {warning}")
            print()
    
    def get_user_choice(self):
        """Get user's preferred way to run Prometheus"""
        print(f"{Colors.BOLD}Choose how to run Prometheus:{Colors.END}")
        print()
        print("1. 🌐 Web Interface (Recommended)")
        print("   Modern browser-based interface with real-time streaming")
        print("   Access at: http://localhost:5050")
        print()
        print("2. 💻 Command Line Interface")
        print("   Rich terminal interface with full features")
        print()
        print("3. 🔧 Run Setup (if something is broken)")
        print()
        print("4. ❌ Exit")
        print()
        
        while True:
            try:
                choice = input(f"{Colors.BOLD}Your choice (1-4): {Colors.END}").strip()
                if choice in ['1', '2', '3', '4']:
                    return int(choice)
                print("Please enter 1, 2, 3, or 4")
            except KeyboardInterrupt:
                print(f"\n{Colors.YELLOW}Goodbye!{Colors.END}")
                sys.exit(0)
    
    def run_web_interface(self):
        """Launch the web interface"""
        self.print_status("Starting Prometheus Web Interface...", "working")
        
        try:
            python_exe = self.venv_path / "bin" / "python"
            if not python_exe.exists():
                python_exe = self.venv_path / "Scripts" / "python.exe"  # Windows
            
            web_app_path = self.project_root / "web_app.py"
            
            # Change to project directory
            os.chdir(self.project_root)
            
            # Add instructions
            print()
            self.print_status("🌐 Web interface starting...", "success")
            print(f"   📍 URL: {Colors.BOLD}http://localhost:5050{Colors.END}")
            print(f"   🛑 Press Ctrl+C to stop the server")
            print()
            
            # Run the web app
            subprocess.run([str(python_exe), str(web_app_path)], check=True)
            
        except KeyboardInterrupt:
            self.print_status("Web interface stopped by user", "info")
        except subprocess.CalledProcessError as e:
            self.print_status(f"Failed to start web interface: {e}", "error")
            return False
        except FileNotFoundError:
            self.print_status("Python executable not found in virtual environment", "error")
            self.print_status("Try running: python setup.py", "info")
            return False
        
        return True
    
    def run_cli_interface(self):
        """Launch the CLI interface"""
        self.print_status("Starting Prometheus CLI...", "working")
        
        try:
            python_exe = self.venv_path / "bin" / "python"
            if not python_exe.exists():
                python_exe = self.venv_path / "Scripts" / "python.exe"  # Windows
            
            cli_path = self.project_root / "cli.py"
            
            # Change to project directory
            os.chdir(self.project_root)
            
            print()
            self.print_status("💻 CLI interface starting...", "success")
            print(f"   🛑 Press Ctrl+C anytime to exit")
            print()
            
            # Run the CLI
            subprocess.run([str(python_exe), str(cli_path)], check=True)
            
        except KeyboardInterrupt:
            self.print_status("CLI stopped by user", "info")
        except subprocess.CalledProcessError as e:
            self.print_status(f"Failed to start CLI: {e}", "error")
            return False
        except FileNotFoundError:
            self.print_status("Python executable not found in virtual environment", "error")
            self.print_status("Try running: python setup.py", "info")
            return False
        
        return True
    
    def run_setup(self):
        """Run the setup script"""
        self.print_status("Running setup script...", "working")
        
        try:
            setup_path = self.project_root / "setup.py"
            subprocess.run([sys.executable, str(setup_path)], check=True)
            return True
        except subprocess.CalledProcessError as e:
            self.print_status(f"Setup failed: {e}", "error")
            return False
    
    def main(self):
        """Main launcher logic"""
        self.print_banner()
        
        # Parse command line arguments
        parser = argparse.ArgumentParser(description="Project Prometheus Launcher")
        parser.add_argument("--web", action="store_true", help="Launch web interface directly")
        parser.add_argument("--cli", action="store_true", help="Launch CLI interface directly")
        parser.add_argument("--setup", action="store_true", help="Run setup directly")
        args = parser.parse_args()
        
        # Handle direct launches
        if args.setup:
            return self.run_setup()
        
        if args.web or args.cli:
            if not self.check_prerequisites():
                self.print_status("Run 'python launcher.py --setup' first", "error")
                return False
            
            self.check_optional_components()
            
            if args.web:
                return self.run_web_interface()
            else:
                return self.run_cli_interface()
        
        # Interactive mode
        while True:
            # Check prerequisites (but don't exit, offer setup)
            prereqs_ok = self.check_prerequisites()
            
            if prereqs_ok:
                self.check_optional_components()
            
            choice = self.get_user_choice()
            
            if choice == 1:  # Web Interface
                if not prereqs_ok:
                    self.print_status("Please run setup first", "error")
                    continue
                self.run_web_interface()
                break
                
            elif choice == 2:  # CLI Interface
                if not prereqs_ok:
                    self.print_status("Please run setup first", "error")
                    continue
                self.run_cli_interface()
                break
                
            elif choice == 3:  # Setup
                if self.run_setup():
                    self.print_status("Setup completed! Choose an interface to launch:", "success")
                    print()
                    continue
                else:
                    break
                    
            elif choice == 4:  # Exit
                self.print_status("Goodbye!", "info")
                break
        
        return True


def main():
    """Entry point"""
    launcher = PrometheusLauncher()
    success = launcher.main()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()