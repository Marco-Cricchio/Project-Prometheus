#!/usr/bin/env python3
"""
Project Prometheus Setup Script

This script automates the complete setup process for Project Prometheus,
making it accessible even to non-technical users.
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_step(message: str):
    """Print a setup step with formatting"""
    print(f"{Colors.BLUE}{Colors.BOLD}📦 {message}{Colors.END}")


def print_success(message: str):
    """Print a success message with formatting"""
    print(f"{Colors.GREEN}{Colors.BOLD}✅ {message}{Colors.END}")


def print_warning(message: str):
    """Print a warning message with formatting"""
    print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  {message}{Colors.END}")


def print_error(message: str):
    """Print an error message with formatting"""
    print(f"{Colors.RED}{Colors.BOLD}❌ {message}{Colors.END}")


def check_python_version():
    """Ensure Python 3.8+ is being used"""
    print_step("Checking Python version...")
    
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_error(f"Python 3.8+ required. Found Python {version.major}.{version.minor}")
        print("Please install Python 3.8 or newer and try again.")
        sys.exit(1)
    
    print_success(f"Python {version.major}.{version.minor}.{version.micro} detected")


def check_uv_installed():
    """Check if UV is installed, offer to install if not"""
    print_step("Checking for UV package manager...")
    
    if shutil.which("uv") is None:
        print_warning("UV not found. UV is required for fast package management.")
        print("Installing UV automatically...")
        
        try:
            # Install UV using the official installer
            import urllib.request
            installer_script = urllib.request.urlopen("https://astral.sh/uv/install.sh").read()
            
            # Write and execute installer
            with open("/tmp/uv_install.sh", "wb") as f:
                f.write(installer_script)
            
            subprocess.run(["sh", "/tmp/uv_install.sh"], check=True)
            
            # Add UV to PATH for this session
            uv_bin = Path.home() / ".cargo" / "bin"
            os.environ["PATH"] = f"{uv_bin}:{os.environ['PATH']}"
            
            print_success("UV installed successfully!")
            
        except Exception as e:
            print_error(f"Failed to install UV: {e}")
            print("Please install UV manually:")
            print("  curl -LsSf https://astral.sh/uv/install.sh | sh")
            sys.exit(1)
    else:
        print_success("UV found!")


def check_claude_cli():
    """Check if Claude Code CLI is available"""
    print_step("Checking for Claude Code CLI...")
    
    if shutil.which("claude") is None:
        print_warning("Claude Code CLI not found!")
        print("Claude Code CLI is required for the autonomous development features.")
        print("Please install it from: https://www.anthropic.com/claude-code")
        print("")
        
        response = input("Continue setup without Claude Code CLI? (y/N): ").strip().lower()
        if response not in ['y', 'yes']:
            print("Setup cancelled. Please install Claude Code CLI first.")
            sys.exit(1)
        
        print_warning("Continuing without Claude Code CLI (limited functionality)")
    else:
        print_success("Claude Code CLI found!")


def setup_virtual_environment():
    """Create and configure virtual environment using UV"""
    print_step("Setting up virtual environment...")
    
    try:
        # Remove existing venv if present
        if Path(".venv").exists():
            print("Removing existing virtual environment...")
            shutil.rmtree(".venv")
        
        # Create new virtual environment
        subprocess.run(["uv", "venv"], check=True, capture_output=True)
        print_success("Virtual environment created!")
        
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        sys.exit(1)


def install_dependencies():
    """Install project dependencies using UV"""
    print_step("Installing dependencies...")
    
    try:
        # Install the project in editable mode with all dependencies
        subprocess.run(["uv", "pip", "install", "-e", "."], check=True, capture_output=True)
        print_success("Dependencies installed successfully!")
        
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install dependencies: {e}")
        sys.exit(1)


def setup_environment_file():
    """Set up the .env file for configuration"""
    print_step("Setting up environment configuration...")
    
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if not env_file.exists():
        if env_example.exists():
            # Copy .env.example to .env
            shutil.copy(env_example, env_file)
            print_success(".env file created from template!")
        else:
            # Create basic .env file
            with open(env_file, "w") as f:
                f.write("# Google Gemini API Key (optional)\n")
                f.write("GEMINI_API_KEY=\n")
            print_success("Basic .env file created!")
        
        print("")
        print(f"{Colors.YELLOW}{Colors.BOLD}🔑 API Key Configuration{Colors.END}")
        print("To use Gemini AI features, you need a Google AI API key:")
        print("1. Go to: https://makersuite.google.com/app/apikey")
        print("2. Create an API key")
        print("3. Edit the .env file and paste your API key")
        print("")
        print("Note: If you don't configure Gemini, Prometheus will use Claude as fallback.")
        
    else:
        print_success(".env file already exists!")


def create_launch_scripts():
    """Create convenient launch scripts"""
    print_step("Creating launch scripts...")
    
    # Web launcher
    web_script = """#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

# Ensure we're in the project directory
os.chdir(Path(__file__).parent)

# Activate venv and run web app
try:
    subprocess.run([".venv/bin/python", "web_app.py"], check=True)
except KeyboardInterrupt:
    print("\\nShutting down Prometheus Web App...")
except FileNotFoundError:
    print("Virtual environment not found. Please run setup.py first.")
    sys.exit(1)
"""
    
    # CLI launcher  
    cli_script = """#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path
import os

# Ensure we're in the project directory
os.chdir(Path(__file__).parent)

# Activate venv and run CLI
try:
    subprocess.run([".venv/bin/python", "cli.py"], check=True)
except KeyboardInterrupt:
    print("\\nShutting down Prometheus CLI...")
except FileNotFoundError:
    print("Virtual environment not found. Please run setup.py first.")
    sys.exit(1)
"""
    
    # Write launch scripts
    with open("start_web.py", "w") as f:
        f.write(web_script)
    
    with open("start_cli.py", "w") as f:
        f.write(cli_script)
    
    # Make them executable
    os.chmod("start_web.py", 0o755)
    os.chmod("start_cli.py", 0o755)
    
    print_success("Launch scripts created!")


def main():
    """Main setup function"""
    print(f"{Colors.BLUE}{Colors.BOLD}")
    print("=" * 60)
    print("🚀 PROJECT PROMETHEUS SETUP")
    print("=" * 60)
    print(f"{Colors.END}")
    print()
    
    try:
        check_python_version()
        check_uv_installed()
        check_claude_cli()
        setup_virtual_environment()
        install_dependencies()
        setup_environment_file()
        create_launch_scripts()
        
        print()
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 Setup Complete!{Colors.END}")
        print()
        print("Next steps:")
        print(f"  • Configure API keys in {Colors.BOLD}.env{Colors.END} (optional)")
        print(f"  • Run {Colors.BOLD}python start_web.py{Colors.END} for web interface")
        print(f"  • Run {Colors.BOLD}python start_cli.py{Colors.END} for command line interface")
        print(f"  • Visit {Colors.BOLD}http://localhost:5050{Colors.END} for web app")
        print()
        print("Need help? Check the README.md file!")
        
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Setup cancelled by user.{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error during setup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()