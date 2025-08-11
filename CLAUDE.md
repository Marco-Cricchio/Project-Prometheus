# Project Prometheus - Comprehensive Technical Memory

## Architecture Overview

Project Prometheus is an AI-powered autonomous development assistant with a hybrid architecture combining:

- **Backend**: Python Flask web application with autonomous development orchestration
- **Frontend**: Single-page HTML application with JavaScript for real-time streaming
- **Core Engine**: `Orchestrator` class that manages AI interactions and development cycles
- **AI Integration**: Multi-provider support (Gemini and Claude) with intelligent fallback
- **Interface Options**: Web interface (primary) and CLI interface (secondary)

## Directory Structure

```
Project-Prometheus/
├── core/
│   └── orchestrator.py          # Main orchestration engine
├── templates/
│   └── index.html              # Complete web interface (HTML/CSS/JS)
├── web_app.py                  # Flask backend server
├── cli.py                      # Command-line interface
├── launcher.py                 # Smart launcher with setup management
├── start_web.py               # Web server launcher
├── setup.py                   # Automated setup script
├── requirements.txt           # Python dependencies
├── conversations/             # Session storage directory
└── backup/                    # Backup storage
```

## Core Components

### 1. Orchestrator Class (`core/orchestrator.py`)

**Primary Responsibilities:**
- AI provider management and fallback handling
- Development cycle orchestration (TDD or Classic)
- Session state management and persistence
- Real-time communication via queues
- Project plan generation and execution
- Working directory management

**Key Attributes:**
```python
class Orchestrator:
    def __init__(self, session_id=None, lang='en', architect_llm='gemini'):
        # Core state
        self.lang = lang                    # 'it' or 'en'
        self.architect_llm = architect_llm  # 'gemini' or 'claude'
        self.working_directory = None       # Project directory path
        self.tdd_mode = True               # TDD vs Classic development
        self.mode = "BRAINSTORMING"        # or "DEVELOPMENT"
        
        # Development cycle control
        self.is_running = False
        self.output_queue = queue.Queue()
        self.dev_thread = None
        
        # State tracking
        self.status = StatusEnum.IDLE
        self.conversation_history = []
        self.project_plan = None
        
        # Fallback management
        self.original_architect = architect_llm
        self.current_architect = architect_llm
        self.fallback_active = False
```

**Key Methods:**
- `process_user_input()`: Main entry point for user messages
- `start_development_phase()`: Transitions from brainstorming to autonomous development
- `_development_loop()`: Core autonomous development cycle
- `handle_development_step()`: Executes single development iteration
- `_get_architect_response()`: AI provider abstraction with fallback
- `save_state()` / `load_state()`: Session persistence

### 2. Web Application (`web_app.py`)

**Flask Routes:**
```python
@app.route("/")                              # Main interface
@app.route("/api/create_chat", methods=["POST"])     # New conversation
@app.route("/api/set_directory", methods=["POST"])   # Working directory setup
@app.route("/api/chat", methods=["POST"])            # Message processing
@app.route("/api/conversations", methods=["GET"])    # List conversations
@app.route("/api/history/<session_id>", methods=["GET"])  # Load conversation
@app.route("/api/conversation_info/<session_id>", methods=["GET"])  # Metadata
@app.route("/api/rename", methods=["POST"])          # Rename conversation
@app.route("/api/delete", methods=["POST"])          # Delete conversation
```

**Key Features:**
- Streaming response handling for real-time updates
- Session management with persistent storage
- Multi-language API support
- Provider fallback coordination
- Cache-disabled headers for development

### 3. Frontend (`templates/index.html`)

**Architecture Pattern**: Single-file SPA with embedded CSS and JavaScript

**CSS Architecture:**
- CSS Variables for theming (`--bg-color`, `--text-color`, etc.)
- Dark/Light theme support via `body[data-theme="dark"]`
- Flexbox-based layout with resizable sidebar
- Status indicators with CSS animations
- Responsive design principles

**Key CSS Classes:**
```css
:root {
    --sidebar-width: 260px;
    --bg-color: #f0f2f5;
    --main-bg-color: #ffffff;
    --text-color: #333;
    /* Theme colors */
    --status-idle: #6c757d;
    --status-running: #007bff;
    --status-paused: #ffc107;
    --status-completed: #28a745;
    --status-error: #dc3545;
}
```

**JavaScript Architecture:**

**Global State Management:**
```javascript
let currentSessionId = null;           // Active conversation
let currentLang = 'it';               // UI language
let currentArchitect = 'gemini';      // Selected AI provider
let currentTddMode = true;            // Development methodology
let workingDirectorySet = false;      // Directory configuration status
let isProcessingRequest = false;      // Request state
let currentAbortController = null;    // Request cancellation
```

**Core Functions:**

1. **Message Handling:**
   - `addMessage(speaker, content, isThinking, thinkingMessage)`: UI message rendering
   - `appendToStream(markdownContent, immediate)`: Real-time content streaming
   - `updateStreamContent()`: Buffered content updates

2. **Communication:**
   - Form submission handler with streaming response processing
   - Abort request functionality
   - Signal parsing for special messages (`[THINKING]`, `[CLAUDE_PROMPT]`, etc.)

3. **Session Management:**
   - `loadConversationHistory()`: Conversation list loading
   - `loadChat(sessionId)`: Conversation restoration
   - Automatic session persistence

4. **UI State:**
   - `updateProviderStatus()`: AI provider indicator
   - `updateDevStatus()`: Development phase tracking
   - `showToast()`: Notification system
   - `setLanguage()`: Internationalization

## Key Features

### 1. Chat Interface and Messaging System

**Message Types:**
- User messages with markdown support
- AI responses with real-time streaming
- System messages for status updates
- Thinking indicators during processing

**Streaming Implementation:**
```javascript
const reader = response.body.getReader();
const decoder = new TextDecoder();
// Processes chunks with special signal detection
// Handles [THINKING], [CLAUDE_PROMPT], [STREAM_END] signals
```

### 2. Conversation Management

**Features:**
- Create new conversations instantly
- Load/resume existing conversations
- Rename conversations with conflict detection
- Delete conversations with confirmation
- Persistent storage in JSON format
- Conversation status indicators (idle/running/paused/completed/error)

**Storage Format** (`conversations/{session_id}.json`):
```json
{
    "session_id": "20241211_143022",
    "mode": "BRAINSTORMING",
    "project_plan": null,
    "lang": "it",
    "architect_llm": "gemini",
    "tdd_mode": true,
    "working_directory": "/path/to/project",
    "display_history": [],
    "gemini_history": [],
    "status": "IDLE",
    "fallback_active": false
}
```

### 3. Language Switching (IT/EN)

**Implementation:**
- Client-side language state with localStorage persistence
- UI text localization via `UI_TEXT` object
- API language parameter propagation
- Dynamic content updates without page reload

### 4. Theme Switching (Light/Dark)

**CSS Variables Approach:**
```css
body[data-theme="dark"] {
    --bg-color: #121212;
    --main-bg-color: #1e1e1e;
    --text-color: #e0e0e0;
}
```

### 5. Welcome Screen Functionality

**Logic:**
- Displays when no conversations exist
- Hides automatically when first conversation is created
- Provides onboarding guidance
- Language-aware content

### 6. TDD Mode and Architect LLM Selection

**TDD Mode:**
- Toggle between Test-Driven Development and Classic development
- Affects development cycle methodology in orchestrator
- Visual toggle switch with state persistence

**Architect Selection:**
- Gemini (Creative) vs Claude (Analytical)
- Dropdown selection with provider icons
- Real-time provider status indicator
- Intelligent fallback between providers

## API Endpoints

### Core Endpoints

1. **POST /api/create_chat**
   - Creates new conversation immediately
   - Returns: `{success: true, session_id: "...", message: "..."}`
   - Parameters: `{lang, architect, tdd_mode}`

2. **POST /api/set_directory**
   - Sets working directory for development
   - Validates/creates directory
   - Returns success/error message
   - Parameters: `{session_id, path, lang}`

3. **POST /api/chat**
   - Main message processing endpoint
   - Returns streaming response
   - Parameters: `{message, session_id, lang, architect, tdd_mode}`

4. **GET /api/conversations**
   - Returns list of all saved conversations
   - Format: `["session_id1", "session_id2", ...]`

5. **GET /api/history/{session_id}**
   - Returns conversation history without initializing orchestrator
   - Returns: `{history: [], session_id: "...", architect_llm: "..."}`

### Management Endpoints

6. **GET /api/conversation_info/{session_id}**
   - Returns conversation metadata
   - Includes fallback status and development state
   - Returns: `{session_id, architect_llm, mode, status, lang, ...}`

7. **POST /api/rename**
   - Renames conversation with validation
   - Parameters: `{old_id, new_name}`
   - Handles orchestrator instance updates

8. **POST /api/delete**
   - Deletes conversation and cleans up
   - Parameters: `{session_id}`
   - Removes from cache and filesystem

## AI Provider Management

### Multi-Provider Architecture

**Provider Abstraction:**
```python
def _get_architect_response(self, prompt):
    # Tries current architect (Gemini or Claude)
    # Automatic fallback on failures
    # Error type detection and user-friendly messages
    # Fallback state management
```

**Error Handling:**
```python
class ProviderErrorHandler:
    ERROR_TYPES = {
        'RATE_LIMIT': 'rate_limit',
        'QUOTA_EXCEEDED': 'quota_exceeded',
        'CONNECTION_ERROR': 'connection_error',
        'USAGE_LIMIT': 'usage_limit',
        'API_KEY_INVALID': 'api_key_invalid'
    }
```

**Fallback Logic:**
1. Detect error type from response
2. Show user-friendly message in appropriate language
3. Switch to alternative provider transparently
4. Update UI provider indicator
5. Continue conversation seamlessly
6. Log fallback reason for debugging

## Development Cycle Engine

### TDD Methodology Implementation

**Decision Tree Logic:**
```python
# Orchestrator analyzes current state and decides next action:
# 1. Empty directory → Setup framework
# 2. Existing files → Analyze compatibility with PRP
# 3. Setup complete → Install test framework
# 4. Test framework ready → Create failing tests (RED)
# 5. Tests failing → Implement code (GREEN)
# 6. Tests passing → Next feature or refactor
# 7. Compilation errors → Fix errors first
```

**Development Loop:**
```python
def _development_loop(self):
    while self.is_running:
        # Execute development step
        # Detect user questions (pause if found)
        # Detect project completion
        # Manage completion signals counter
        # Apply failsafe limits
        # Continue or stop based on conditions
```

**Completion Detection:**
Advanced pattern matching for:
- Direct completion phrases
- Repetition detection (loop prevention)
- Project status analysis
- User question detection for interactive pauses

### Classic Development Mode

Alternative to TDD with direct implementation approach:
- Analysis → Implementation → Verification → Iteration
- Focus on rapidly usable functionality
- Optional testing or final verification
- Simplified decision tree

## Recent Improvements and Fixes

### UI/UX Enhancements (Recent Session)
1. **Welcome Screen Internationalization**
   - Added English language support for welcome screen
   - Dynamic text switching based on user language preference
   - Consistent language experience throughout application

2. **Immediate Chat Creation**
   - New `/api/create_chat` endpoint for instant conversation file creation
   - Eliminates delay between "New Chat" click and file persistence
   - Improved user feedback with immediate session availability

3. **Language Toggle Fix**
   - Fixed language switching not working immediately in welcome screen
   - Added safe element update functions to prevent DOM errors
   - Enhanced welcome screen regeneration on language change

4. **Message Duplication Fix**
   - Resolved duplicate Prometheus welcome messages in new chats
   - Fixed by removing manual message addition (orchestrator handles automatically)
   - Cleaner conversation initialization

5. **Rename Error Resolution**
   - Fixed 404 errors when renaming conversations
   - Added `isRenaming` flag to prevent double API calls
   - Improved event listener management with proper cleanup

6. **Typing Indicator Cleanup**
   - Ensured typing indicator (bouncing dots) disappears after responses
   - Added `removeTypingIndicator()` to finally block for guaranteed cleanup
   - Eliminated persistent UI artifacts

7. **Textarea Layout Revolution**
   - **Problem Solved**: Textarea width and send button positioning
   - **Final Solution**: Internal floating button design
   - **Implementation**: 
     - Added `#input-container` wrapper with `position: relative`
     - Positioned send button absolutely inside textarea (`position: absolute; right: 5px; top: 50%; transform: translateY(-50%)`)
     - Added right padding to textarea to prevent text overlap
     - Vertically centered button regardless of textarea height
   - **Result**: Modern, WhatsApp-like interface with perfect responsiveness

### CSS Architecture Improvements
- **Grid Layout Attempt**: Tried CSS Grid for form layout (partially successful)
- **Flexbox Refinement**: Multiple iterations to solve positioning issues  
- **Final Internal Button Pattern**: Clean, modern approach eliminating layout conflicts
- **Responsive Design**: Button stays centered during textarea expansion
- **Cross-browser Compatibility**: Uses standard CSS positioning techniques

### Error Handling Enhancements
- Request abortion functionality for better user control
- Comprehensive error catching in API calls
- Toast notification system for user feedback
- Graceful degradation when network issues occur

## Technical Debt and Known Issues

### Fixed in Recent Session
- ✅ Textarea width and button positioning completely resolved
- ✅ Language switching works immediately without page refresh
- ✅ Duplicate messages eliminated from new chat creation
- ✅ Rename functionality stable with proper error handling
- ✅ Typing indicators properly cleaned up after responses

### Current State
- ✅ **UI/UX**: Modern, responsive design with internal button pattern
- ✅ **Functionality**: All core features working correctly
- ✅ **Error Handling**: Robust with proper cleanup and user feedback
- ✅ **Performance**: Smooth real-time streaming and interaction
- ✅ **Cross-browser**: Standard CSS and JavaScript for maximum compatibility

## Configuration Files

### Dependencies (`requirements.txt`)
```
flask>=2.3.0              # Web framework
python-dotenv>=1.0.0       # Environment configuration
rich>=13.0.0               # CLI formatting
google-generativeai>=0.8.0 # Gemini integration
```

### Environment Configuration (`.env`)
```
GEMINI_API_KEY=your_gemini_api_key_here
```

### Setup Script Features
- Automatic virtual environment creation
- UV package manager support
- Dependency installation with fallbacks
- Environment file template creation
- Installation verification

## Security Considerations

- No file system access beyond configured working directory
- API key environment variable management
- Input sanitization for directory paths
- Conversation data isolated per session
- No executable code evaluation (delegates to Claude CLI)

## Performance Characteristics

### Memory Usage
- Conversation history stored in memory during active sessions
- JSON persistence for long-term storage
- Queue-based communication for streaming
- Efficient session cleanup

### Scalability
- Single-user design with session isolation
- Thread-based development cycle execution
- Stateless API design where possible
- Configurable timeout and cycle limits

## Development Guidelines

### When Working with UI Components
1. **CSS Variables**: Use existing theme variables for consistency
2. **Responsive Design**: Test layouts at different screen sizes
3. **Event Management**: Always clean up event listeners to prevent memory leaks
4. **State Synchronization**: Keep JavaScript state in sync with DOM state
5. **Error Handling**: Provide user feedback for all operations

### When Modifying Backend
1. **Session Management**: Always call `save_state()` after state changes
2. **Error Handling**: Use try-catch blocks and provide meaningful error messages
3. **Provider Management**: Consider fallback scenarios when adding AI provider features
4. **Threading**: Be careful with thread-safe operations in development loop
5. **API Consistency**: Maintain consistent request/response formats

### When Adding New Features
1. **Multi-language**: Add text to `UI_TEXT` object for both IT and EN
2. **Persistence**: Consider what state needs to be saved across sessions
3. **Real-time Updates**: Use the existing streaming infrastructure where appropriate
4. **Testing**: Test with both TDD and Classic modes
5. **Provider Agnostic**: Ensure features work with both Gemini and Claude

This comprehensive technical memory provides complete understanding of Project Prometheus's architecture, recent improvements, and development patterns, enabling efficient future development sessions.