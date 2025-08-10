# 🚀 Project Prometheus

**An AI-powered autonomous development assistant that brings your ideas to life through intelligent brainstorming and automated TDD (Test-Driven Development) cycles.**

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.9+-green)
![License](https://img.shields.io/badge/license-MPL%202.0%20+%20CLA-blue)

## ✨ Features

- 🧠 **AI-Powered Brainstorming**: Interactive conversations with Gemini or Claude to refine your project ideas
- 🔄 **Autonomous TDD Cycle**: Automated Test-Driven Development with continuous improvement
- 🌐 **Dual Interface**: Choose between modern web interface or feature-rich CLI
- 🎯 **Multi-Language Support**: Italian and English interfaces
- 🔧 **Flexible AI Backend**: Switch between Gemini (creative) and Claude (analytical) architects
- 📁 **Smart Project Management**: Automatic project setup and directory management

## 🚦 Quick Start (3 Steps!)

### Prerequisites
- **Python 3.9+** (required by Google Gemini AI dependencies)
- **Claude Code CLI** (for autonomous development) - [Install here](https://www.anthropic.com/claude-code)

### Installation

1. **Clone and Setup**
   ```bash
   git clone https://github.com/Marco-Cricchio/Project-Prometheus.git
   cd Project-Prometheus
   python setup.py
   ```

2. **Alternative Installation** (if setup.py fails)
   ```bash
   # Option A: Using UV (recommended)
   uv venv
   uv pip install -e .
   
   # Option B: Using Python virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   
   # Option C: Manual dependency installation with virtual environment
   python -m venv .venv
   source .venv/bin/activate
   pip install flask python-dotenv rich google-generativeai
   ```

3. **Configure API Keys** (Optional)
   ```bash
   # Edit .env file with your API keys
   nano .env  # or use any text editor
   ```

4. **Launch Prometheus**
   ```bash
   # Web Interface (Recommended)
   python start_web.py
   # Then visit: http://localhost:5050
   
   # OR Command Line Interface
   python start_cli.py
   ```

That's it! 🎉

## 🖥️ Interfaces

### Web Interface
- **Modern UI**: Responsive design with dark/light theme
- **Real-time Streaming**: Watch development progress live
- **Conversation Management**: Save and resume projects
- **Visual Progress**: Status indicators and progress bars

### CLI Interface
- **Rich Terminal UI**: Colored output and formatting
- **Multiline Input**: Complex prompts support
- **Status Monitoring**: Development cycle visualization
- **Session Management**: Resume previous conversations

## 🤖 AI Architects

Choose your preferred AI assistant:

- **🔷 Gemini (Creative)**: Google's latest model, excellent for innovative solutions
- **🧠 Claude (Analytical)**: Anthropic's Claude, perfect for structured development

*Note: Gemini requires an API key. Claude works through the CLI and requires installation.*

## 📋 How It Works

### 1. Brainstorming Phase
- Share your project idea with Prometheus
- Receive intelligent questions and suggestions
- Refine requirements through interactive dialogue

### 2. Development Trigger
- Say **"ACCENDI I MOTORI!"** (IT) or **"START THE ENGINES!"** (EN)
- Prometheus creates a detailed Project Plan (PRP)
- Autonomous development cycle begins

### 3. Autonomous TDD Cycle
- **RED**: Creates failing tests for new features
- **GREEN**: Implements code to pass tests  
- **REFACTOR**: Improves code quality and structure
- **REPEAT**: Continues until project completion

### 4. Project Management
- Specify your working directory
- All code is created in your chosen location
- No unwanted subdirectories or files

## ⚙️ Configuration

### Environment Variables (.env)
```bash
# Google Gemini API Key (Optional)
# Get from: https://makersuite.google.com/app/apikey
GEMINI_API_KEY=your_api_key_here

# Optional settings
LOG_LEVEL=INFO
MAX_CONVERSATION_HISTORY=100
```

### API Keys Setup
1. **Gemini**: Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. **Claude**: Install [Claude Code CLI](https://www.anthropic.com/claude-code) and authenticate

## 🛠️ Advanced Usage

### UV Package Manager
This project uses [UV](https://astral.sh/uv/) for ultra-fast dependency management:

```bash
# Manual installation with UV
uv venv
uv pip install -e .

# Run specific components
uv run prometheus-web  # Web interface
uv run prometheus-cli  # CLI interface
```

### Development Mode
```bash
# Install with development dependencies
uv pip install -e .[dev]

# Run tests
pytest

# Code formatting
black .
```

## 🔧 Troubleshooting

### Common Issues

**"Claude Code CLI not found"**
- Install from: https://www.anthropic.com/claude-code
- Ensure it's in your PATH

**"UV not found"**
- The setup script installs UV automatically
- Manual install: `curl -LsSf https://astral.sh/uv/install.sh | sh`

**"Permission denied on port 5050"**
- Port might be in use, check with: `lsof -i :5050`
- Change port in `web_app.py` if needed

**"API key not working"**
- Verify your Gemini API key in `.env`
- Check API quotas at Google AI Studio
- Prometheus falls back to Claude if Gemini fails

## 📁 Project Structure

```
project-prometheus/
├── core/                 # Core orchestration logic
│   └── orchestrator.py   # Main AI coordination engine
├── templates/            # Web interface templates
│   └── index.html       # Single-page web application
├── conversations/        # Saved chat sessions
├── cli.py               # Command-line interface
├── web_app.py           # Web server and API
├── setup.py             # Automated setup script
├── start_web.py         # Web app launcher
├── start_cli.py         # CLI launcher
├── pyproject.toml       # UV/Python configuration
├── .env.example         # Environment template
└── README.md            # This file
```

## 🤝 Contributing

We welcome contributions! Please read and sign our Contributor License Agreement before submitting any changes.

### How to Contribute
1. **Sign the CLA**: Before your first contribution, you must sign our [Contributor License Agreement (CLA)](CLA.md)
2. **Fork the repository**
3. **Create your feature branch**: `git checkout -b feature/amazing-feature`
4. **Commit your changes**: `git commit -m 'Add amazing feature'`
5. **Push to the branch**: `git push origin feature/amazing-feature`
6. **Open a Pull Request**

### Signing the CLA
See [CLA.md](CLA.md) for detailed instructions on how to sign the Contributor License Agreement.

## 📜 License

This project is licensed under **Mozilla Public License 2.0 + Contributor License Agreement**.

### What this means:

**📖 For Users:**
- ✅ **Free to use**: You can use Project Prometheus for any purpose, including commercial use
- ✅ **Modify freely**: You can modify the code to fit your needs
- ✅ **Distribute**: You can share the software with others
- ✅ **Combine with proprietary code**: You can integrate Project Prometheus into larger proprietary works

**📝 For Developers:**
- 📤 **Share improvements**: If you modify MPL-licensed files, you must share those modifications under MPL 2.0
- 🔒 **Keep proprietary parts private**: You can add proprietary components in separate files
- ⚖️ **File-based copyleft**: Only modified MPL files need to remain open source, not your entire project

**👥 For Contributors:**
- ✍️ **CLA required**: Contributors must sign a Contributor License Agreement
- 🤝 **Rights granted**: The CLA ensures the project can continue to be developed and distributed
- 🛡️ **Legal clarity**: Provides clear legal framework for contributions

### License Files
- **[LICENSE](LICENSE)**: Complete licensing terms
- **[CLA.md](CLA.md)**: Contributor License Agreement details

*This licensing approach balances open source collaboration with practical flexibility for both individual users and commercial adopters.*

## 🙏 Acknowledgments

- **Anthropic** for Claude AI and Claude Code CLI tools
- **Google** for Gemini AI capabilities  
- **Astral** for the UV package manager
- The open-source community for inspiration and tools

## 💡 Support

- 📖 **Documentation**: This README covers most use cases
- 🐛 **Issues**: Report bugs on GitHub Issues
- 💬 **Discussions**: Share ideas in GitHub Discussions
- 📧 **Contact**: Reach out to the maintainers

---

**Made with ❤️ by the Project Prometheus team**

*Bringing AI-powered autonomous development to everyone, from beginners to experts.*