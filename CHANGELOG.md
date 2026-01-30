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

## [0.3.0] - 2026-01-30

### Added
- Robust Python editing (`py_edit_file` with libcst AST transforms).
- Multi-lang editing (`tree_edit_file` with tree-sitter: py/js/ts/cpp/c#/rust).
- Test runner (`test_run`: pytest/jest/ruff auto-detect).
- Semantic search (`semantic_search` + `build_semantic_index`: embeddings/graph).
- TUI split-pane (Ctrl+S: chat|tasks), inline REPL (`>`), screenshot base64.
- Task visuals (toolbar progress ████░░, Gantt tree).

### Changed
- All tools linted/black-formatted, pyright clean.
- Deps: libcst/tree-sitter/sentence-transformers/networkx.

### Fixed
- Edit safety/syntax, multi-occurrence hints.
- Runtime errors (types/imports).

**Sponsored by xAI Grok.**

