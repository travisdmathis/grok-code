# grokCode

A powerful CLI coding assistant powered by [Grok](https://x.ai) (xAI's API). An AI pair programmer that lives in your terminal.

![grokCode](https://img.shields.io/badge/grokCode-v0.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.11+-yellow)

## What is grokCode?

grokCode is a command-line AI coding assistant that helps you understand, write, and modify code through natural conversation inspired by Cluade Code. It can read your files, make edits, run commands, search your codebase, and spawn specialized agents for complex tasks—all from your terminal.

### Key Features

- **Natural Conversation** - Chat with Grok about your code in plain English
- **File Operations** - Read, write, and edit files with intelligent diff previews
- **Code Search** - Find files with glob patterns, search contents with regex
- **Command Execution** - Run shell commands and see results inline
- **Custom Agents** - Create specialized agents for code review, testing, documentation, and more
- **Session History** - Save and restore conversations across sessions
- **Rich Terminal UI** - Full-screen interface with syntax highlighting and markdown rendering
- **Project Context** - Customize behavior per-project with `.grok/GROK.md`

## Quick Start

### 1. Install

```bash
# Clone the repository
git clone https://github.com/yourusername/grokCode.git
cd grokCode

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install
pip install -e .
```

### 2. Configure API Key

Get your API key from [console.x.ai](https://console.x.ai), then:

```bash
export XAI_API_KEY="your-api-key-here"
```

Or create a `.env` file in your project:

```
XAI_API_KEY=your-api-key-here
```

### 3. Run

```bash
cd your-project
grok
```

### 4. Initialize Project (Optional)

```
> /init
```

This creates a `.grok/` folder with project configuration and an example agent.

## Usage

### Basic Interaction

Just type naturally:

```
> What does the authenticate function in src/auth.py do?

> Add input validation to the login endpoint

> Find all files that import the database module

> Run the tests for the user module
```

### File Mentions

Use `@` to reference files:

```
> @src/auth.py explain how this authentication works

> @package.json what dependencies are installed?
```

Tab completion is available for file paths.

### Direct Commands

Use `!` to run shell commands:

```
> !npm test
> !git status
> !python -m pytest tests/
```

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help and available commands |
| `/init` | Initialize `.grok/` in current project |
| `/agents` | List available agents |
| `/agents new` | Create a new custom agent (interactive wizard) |
| `/save history` | Save conversation to `.grok/history/` |
| `/load history` | List or load saved conversations |
| `/plugins` | List loaded plugins |
| `/tools` | List available tools |
| `/tasks` | Show task list |
| `/plan` | Enter planning mode |
| `/config` | Show current configuration |
| `/clear` | Clear conversation history |
| `/exit` | Exit grokCode |

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Submit message |
| `Ctrl+C` | Cancel current operation |
| `Ctrl+C Ctrl+C` | Exit (press twice quickly) |
| `Esc Esc` | Interrupt thinking / clear input |
| `Ctrl+D` | Exit |
| `Shift+Tab` | Cycle permission mode |
| `PageUp/Down` | Scroll chat history |
| `Tab` | Autocomplete files and commands |

## Agents

Agents are specialized AI assistants that can be invoked for specific tasks.

### Built-in Agents

- **explore** - Fast codebase exploration and search
- **plan** - Design implementation approaches before coding
- **general** - General-purpose multi-step tasks

### Invoking Agents

Use `@agent:name` to directly invoke an agent:

```
> @agent:explore find all API endpoints in this project

> @agent:plan design a caching layer for the database

> @agent:code-reviewer review the changes in src/auth.py
```

### Creating Custom Agents

Run `/agents new` for an interactive wizard, or create a file in `.grok/agents/`:

```markdown
---
name: my-agent
description: What this agent does
color: "#e06c75"
---

# My Agent

Instructions for the agent go here...
```

**That's it!** Agents get access to ALL tools by default. No need to list them.

#### Restricting Tools (Optional)

If you want to create a read-only agent (like a code reviewer that shouldn't modify files), specify which tools it can use:

```markdown
---
name: code-reviewer
description: Reviews code for best practices and security
color: "#e06c75"
tools: read_file, glob, grep, bash
---

# Code Reviewer Agent

You are a thorough code reviewer...
```

Available tool names: `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `bash`, `task_create`, `task_update`, `task_list`, `task_get`, `web_fetch`, `web_search`

### Agent Colors

When creating agents, you can specify a color for the UI:

- `cyan`, `purple`, `blue`, `red`, `green`
- `orange`, `yellow`, `teal`, `pink`, `gray`
- Or any hex code: `#ff79c6`

## Planning & Tasks

### Creating Plans

Use the plan agent to design implementation approaches:

```
> @agent:plan add user authentication with JWT tokens
```

This creates a plan file in `.grok/plans/` with:
- Overview of the approach
- Files to create/modify
- Task checklist

### Referencing Plans

Use `@plan:` to include plan files in your prompt:

```
> @plan:auth-implementation.md implement this plan
```

Tab completion is available for plan files.

### Task Tracking

Tasks from plans are tracked and displayed live as agents work:

```
> /tasks
```

Shows all tasks with status:
- Pending tasks
- In-progress tasks (with spinner)
- Completed tasks (with checkmark and strikethrough)

### Implementation Workflow

1. Create a plan: `@agent:plan add feature X`
2. Review the plan file in `.grok/plans/`
3. Implement with an engineer agent: `@agent:engineer @plan:feature-x.md implement this`
4. Watch tasks complete in real-time

## Project Configuration

### .grok/GROK.md

Customize how Grok responds in your project:

```markdown
# Project Instructions

## Response Style
- Be concise and technical
- Reference file paths with line numbers
- Follow existing code patterns

## Project Context
- Language: Python
- Framework: FastAPI
- Test Framework: pytest

## Conventions
- Use type hints on all functions
- Docstrings in Google format
- Max line length: 100
```

### Directory Structure

After `/init`, your project will have:

```
.grok/
├── GROK.md          # Project instructions
├── agents/          # Custom agent definitions
│   └── engineer.md  # Example: implementation agent
├── plans/           # Plan files created by @agent:plan
├── history/         # Saved conversations
└── handoffs/        # Session handoff files
```

## Session Management

### Save Conversation

```
> /save history
```

Saves to `.grok/history/conversation_YYYYMMDD_HHMMSS.md`

### Load Conversation

```
> /load history
```

Lists available saved conversations.

```
> /load history conversation_20240115_143022.md
```

Restores a specific conversation.

## Available Tools

### File Operations
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with line numbers |
| `write_file` | Create or overwrite files |
| `edit_file` | Edit via exact string replacement |

### Search
| Tool | Description |
|------|-------------|
| `glob` | Find files by pattern (`**/*.py`) |
| `grep` | Search contents with regex |

### Execution
| Tool | Description |
|------|-------------|
| `bash` | Run shell commands with timeout |

### Agents
| Tool | Description |
|------|-------------|
| `task` | Spawn sub-agents |
| `task_output` | Get background agent results |

### Tasks
| Tool | Description |
|------|-------------|
| `task_create` | Create a task |
| `task_update` | Update task status |
| `task_list` | List all tasks |
| `task_get` | Get task details |

### Web
| Tool | Description |
|------|-------------|
| `web_fetch` | Fetch content from URLs |
| `web_search` | Search the web |

## Architecture

```
grok_code/
├── main.py              # CLI entry point and main loop
├── client.py            # xAI API client with streaming
├── conversation.py      # Message history and system prompt
├── agents/              # Agent system
│   ├── base.py          # Base agent class
│   ├── explore.py       # Codebase exploration agent
│   ├── plan.py          # Planning agent
│   ├── plugin_agent.py  # Custom plugin agents
│   └── runner.py        # Agent lifecycle management
├── tools/               # Tool implementations
│   ├── registry.py      # Tool registration
│   ├── file_ops.py      # Read, write, edit tools
│   ├── bash.py          # Command execution
│   ├── glob_grep.py     # File search tools
│   ├── web.py           # Web fetch and search
│   └── tasks.py         # Task tracking
├── plugins/             # Plugin system
│   ├── loader.py        # Plugin loading from markdown
│   └── registry.py      # Plugin registration
└── ui/                  # Terminal interface
    ├── chat_layout.py   # Full-screen layout
    ├── console.py       # Rich console setup
    ├── display.py       # Output formatting
    └── agents.py        # Agent UI components
```

## Command Line Options

```bash
grok [options]

Options:
  -m, --model MODEL    Grok model to use (default: grok-4-1-fast-reasoning)
  -p, --prompt TEXT    Run a single prompt and exit
  --api-key KEY        xAI API key (or use XAI_API_KEY env var)
  --help               Show help message
```

### Examples

```bash
# Start interactive mode
grok

# Use a specific model
grok --model grok-3-latest

# Run a single prompt
grok -p "Explain what this project does"
```

## Tips & Tricks

### Efficient File Exploration
```
> @agent:explore what's the structure of this codebase?
```

### Code Review Workflow
```
> @agent:code-reviewer review the changes I made today
> !git diff HEAD~1
```

### Planning Before Coding
```
> /plan
> I need to add user authentication
```

### Quick Commands
```
> !git status              # Check git status
> @package.json            # Include file in context
> /clear                   # Start fresh
```

## Troubleshooting

### "XAI_API_KEY not found"
Set your API key:
```bash
export XAI_API_KEY="your-key"
```

### "Agent not found"
Make sure you've run `/init` and the agent file exists in `.grok/agents/`.

### UI Issues
Try resizing your terminal or pressing `Ctrl+L` to refresh.

### Scroll Not Working
Use `PageUp`/`PageDown` for reliable scrolling.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Powered by [xAI's Grok](https://x.ai)
- Inspired by [Claude Code](https://claude.ai/code)
- Built with [prompt_toolkit](https://python-prompt-toolkit.readthedocs.io/) and [Rich](https://rich.readthedocs.io/)

---

**grokCode** - Your AI pair programmer in the terminal.
