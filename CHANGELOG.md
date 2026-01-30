# Changelog

## [0.1.0] - 2026-01-30
### Added
- CLI coding assistant powered by Grok API
- File read/write/edit with permission system
- Safe bash tool (subprocess_exec, no shell=True)
- Agent system (explore, plan, general, custom plugins)
- Plan mode for architectural planning
- Task tracking system
- Rich terminal UI with streaming, diffs, status bar
- Conversation history save/load
- PyPI packaging with pinned deps
- Tests and GitHub CI

### Changed
- Refactored main.py into submodules (cli, app, handlers)
- Added logging and improved error handling
- Added type hints and auto-formatting (black, ruff)

### Fixed
- Security: shell=True in bash command
- Infinite agent loops (max_iterations=10)
- HTML entities in test files
## [0.2.0] - 2026-01-30

### Added
- General agent for multi-step tasks (`grok_code/agents/general.py`)
- Persistent permissions approvals (`.grok/permissions.json`)

### Changed
- Agent runner and planning improvements (`agents/runner.py`, `agents/plan.py`)
- Enhanced conversation handling (`conversation.py`)
- UI chat layout updates (`ui/chat_layout.py`)
- Tool refinements (`tools/file_ops.py`, `tools/plan_mode.py`, etc.)

### Fixed
- Gitignore for `.grok/` and `.github/` directories

