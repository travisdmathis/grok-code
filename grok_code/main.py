"""Main entry point for grokCode CLI"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .client import GrokClient, Message
from .conversation import Conversation
from .tools.registry import create_default_registry, setup_agent_runner
from .tools.file_ops import clear_read_files
from .plugins.registry import setup_default_plugin_dirs
from .ui.chat_layout import ChatLayout, INTERRUPTED


class ChatUI:
    """Manages the chat UI and message flow"""

    def __init__(self, layout: ChatLayout):
        self.layout = layout
        self._streaming_content = ""
        self._stream_start_time = 0.0

    def welcome(self, project_files: list[str] = None, cwd: str = None, model: str = "grok-4-1-fast-reasoning"):
        """Display welcome message"""
        cwd = cwd or os.getcwd()

        # Shorten path for display
        home = str(Path.home())
        if cwd.startswith(home):
            display_cwd = "~" + cwd[len(home):]
        else:
            display_cwd = cwd

        # Simple ASCII logo
        lines = []
        lines.append("")
        lines.append(" ┌───┐")
        lines.append(" │ / │  grokCode v0.1.0")
        lines.append(" └───┘  " + model)
        lines.append("        " + display_cwd)
        lines.append("")
        lines.append(" Type /help for commands, @ to mention files")
        lines.append("")

        self.layout.append_output('\n'.join(lines))

    def stream_start(self):
        """Start streaming content"""
        self._streaming_content = ""
        self._stream_start_time = time.time()

    def stream_chunk(self, text: str):
        """Add a chunk of streamed text"""
        self._streaming_content += text

    def stream_end(self):
        """End streaming and display the full content"""
        if self._streaming_content:
            # Format as agent response with ⏺ prefix
            self.layout.add_assistant_message(
                self._streaming_content,
                elapsed=time.time() - self._stream_start_time
            )
        self._streaming_content = ""

    def tool_done(self, name: str, args: dict):
        """Show completed tool"""
        label = self._format_tool(name, args)
        self.layout.append_output(f"  \u2713 {label}")

    def tool_result(self, result: str, max_lines: int = 3):
        """Show brief tool result"""
        if not result or not result.strip():
            return

        lines = result.strip().split("\n")
        if len(lines) == 1 and len(lines[0]) < 60:
            self.layout.append_output(f"    \u2192 {lines[0]}")
        elif len(lines) > max_lines:
            self.layout.append_output(f"    ({len(lines)} lines)")

    def show_edit(self, filename: str, old_string: str, new_string: str):
        """Show edit preview"""
        short = filename.split('/')[-1] if '/' in filename else filename
        removed = old_string.count('\n') + 1
        added = new_string.count('\n') + 1
        self.layout.append_output(f"  Edit {short}: -{removed} +{added} lines")

    def show_write(self, filename: str, content: str, is_new: bool = False):
        """Show file write"""
        short = filename.split('/')[-1] if '/' in filename else filename
        lines = content.count('\n') + 1
        action = "Create" if is_new else "Write"
        self.layout.append_output(f"  {action} {short}: {lines} lines")

    def info(self, msg: str):
        """Display info"""
        self.layout.append_output(msg)

    def error(self, msg: str):
        """Display error"""
        self.layout.append_output(f"Error: {msg}")

    def summary(self, stats: dict):
        """Show session summary"""
        parts = []
        if stats.get("read"):
            n = stats["read"]
            parts.append(f"Read {n} file{'s' if n > 1 else ''}")
        if stats.get("edit"):
            n = stats["edit"]
            parts.append(f"Edited {n} file{'s' if n > 1 else ''}")
        if stats.get("write"):
            n = stats["write"]
            parts.append(f"Wrote {n} file{'s' if n > 1 else ''}")
        if stats.get("bash"):
            n = stats["bash"]
            parts.append(f"Ran {n} command{'s' if n > 1 else ''}")

        if parts:
            self.layout.append_output(' \u00b7 '.join(parts))

    def _format_tool(self, name: str, args: dict) -> str:
        """Format tool name and args for display"""
        formatters = {
            "read_file": lambda a: f"Read {self._short_path(a.get('file_path', ''))}",
            "write_file": lambda a: f"Write {self._short_path(a.get('file_path', ''))}",
            "edit_file": lambda a: f"Edit {self._short_path(a.get('file_path', ''))}",
            "bash": lambda a: f"$ {self._truncate(a.get('command', ''), 50)}",
            "glob": lambda a: f"Glob {a.get('pattern', '')}",
            "grep": lambda a: f"Grep {self._truncate(a.get('pattern', ''), 30)}",
            "web_search": lambda a: f"Search: {self._truncate(a.get('query', ''), 40)}",
            "web_fetch": lambda a: f"Fetch: {self._truncate(a.get('url', ''), 40)}",
            "task": lambda a: f"{a.get('agent_type', a.get('subagent_type', 'agent'))}: {self._truncate(a.get('prompt', a.get('description', '')), 30)}",
        }

        formatter = formatters.get(name)
        if formatter:
            return formatter(args)
        return name

    def _short_path(self, path: str) -> str:
        """Shorten path for display"""
        if not path:
            return ""
        parts = path.split("/")
        if len(parts) > 2:
            return f".../{'/'.join(parts[-2:])}"
        return path

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text with ellipsis"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."


async def _clear_helper_after(layout, seconds: float):
    """Clear helper text after a delay"""
    await asyncio.sleep(seconds)
    layout.clear_helper()


async def run_conversation_turn(
    client: GrokClient,
    conversation: Conversation,
    registry,
    ui: ChatUI,
    layout: ChatLayout,
    start_time: float,
) -> None:
    """Run a single conversation turn, handling tool calls"""
    # Refresh task context so Grok knows about active plan tasks
    conversation.refresh_task_context()

    tools = registry.get_schemas()
    file_changes = {"files": set(), "added": 0, "removed": 0}

    # Mark as busy
    layout.set_busy(True)

    while True:
        # Check for interruption before starting
        if layout.is_interrupted():
            layout.clear_interrupted()
            layout.set_status("Interrupted")
            await asyncio.sleep(0.5)
            layout.clear_status()
            break

        # Update status (spinner will animate automatically)
        layout.set_status("Thinking...")

        # Start streaming
        ui.stream_start()

        response = await client.chat_stream(
            messages=conversation.get_messages(),
            tools=tools,
            on_content=ui.stream_chunk,
        )

        # Check for interruption after response
        if layout.is_interrupted():
            layout.clear_interrupted()
            ui.stream_end()
            layout.set_status("Interrupted")
            await asyncio.sleep(0.5)
            layout.clear_status()
            break

        # End streaming and display
        ui.stream_end()
        layout.clear_status()

        # Add assistant message to conversation
        conversation.add_assistant_message(
            content=response.content, tool_calls=response.tool_calls
        )

        # If no tool calls, we're done
        if not response.tool_calls:
            break

        # Execute tool calls
        for tool_call in response.tool_calls:
            # Check for interruption
            if layout.is_interrupted():
                layout.clear_interrupted()
                layout.set_status("Interrupted")
                await asyncio.sleep(0.5)
                layout.clear_status()
                layout.set_busy(False)
                return

            # Update status spinner
            tool_label = ui._format_tool(tool_call.name, tool_call.arguments)
            layout.set_status(tool_label)

            # Execute tool
            result = await registry.execute(tool_call.name, tool_call.arguments)

            # Calculate line changes for file operations
            lines_added = 0
            lines_removed = 0

            if tool_call.name == "edit_file" and "Successfully" in result:
                filepath = tool_call.arguments.get("file_path", "")
                old_str = tool_call.arguments.get("old_string", "")
                new_str = tool_call.arguments.get("new_string", "")

                file_changes["files"].add(filepath)
                lines_removed = old_str.count('\n') + 1
                lines_added = new_str.count('\n') + 1
                file_changes["removed"] += lines_removed
                file_changes["added"] += lines_added

                # Show diff for edits
                layout.add_file_diff(filepath, old_str, new_str)

                layout.set_file_changes(
                    len(file_changes["files"]),
                    file_changes["added"],
                    file_changes["removed"],
                )

            elif tool_call.name == "write_file" and "Successfully" in result:
                filepath = tool_call.arguments.get("file_path", "")
                content = tool_call.arguments.get("content", "")

                file_changes["files"].add(filepath)
                lines_added = content.count('\n') + 1
                file_changes["added"] += lines_added

                # Show diff for new file (empty old content)
                layout.add_file_diff(filepath, "", content)

                layout.set_file_changes(
                    len(file_changes["files"]),
                    file_changes["added"],
                    file_changes["removed"],
                )

            elif tool_call.name == "read_file":
                filepath = tool_call.arguments.get("file_path", "")
                short_path = filepath.split('/')[-1] if '/' in filepath else filepath
                line_count = result.count('\n') if result else 0
                layout.add_tool_call(tool_call.name, short_path, f"{line_count} lines")

            else:
                # Other tools - show with result summary
                layout.add_tool_call(tool_call.name, tool_label, result)

            conversation.add_tool_result(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result=result,
            )

    layout.clear_status()
    layout.set_busy(False)
    layout.reset_input_state()

    # Process any queued messages
    while layout.has_queued_messages():
        queued = layout.pop_queued_message()
        if queued:
            layout.add_user_message(queued)
            conversation.add_user_message(queued)
            layout.set_busy(True)
            # Recursively handle the queued message
            await run_conversation_turn(client, conversation, registry, ui, layout, time.time())


async def main_loop(
    client: GrokClient,
    conversation: Conversation,
    registry,
    plugin_registry,
    agent_runner,
    layout: ChatLayout,
    ui: ChatUI,
    model: str,
) -> int:
    """Main conversation loop"""
    last_interrupt_time = 0

    while True:
        try:
            user_input = await layout.get_input_async()

            if user_input is None:
                # EOF (Ctrl+D)
                layout.set_helper("Goodbye!")
                layout.exit()
                return 0

            if user_input is INTERRUPTED:
                # Ctrl+C pressed
                now = time.time()
                if now - last_interrupt_time < 2.0:
                    # Second Ctrl+C within 2 seconds - exit
                    layout.set_helper("Goodbye!")
                    layout.exit()
                    return 0
                last_interrupt_time = now
                layout.set_helper("Press Ctrl+C again to exit")
                # Auto-clear helper after 2 seconds
                asyncio.create_task(_clear_helper_after(layout, 2.0))
                continue

            user_input = user_input.strip()

            if not user_input:
                continue

            # Reset interrupt timer and clear helper on valid input
            last_interrupt_time = 0
            layout.clear_helper()

            # Handle slash commands
            cmd = user_input.lower().lstrip("/")

            if cmd in ("exit", "quit", "q"):
                layout.set_helper("Goodbye!")
                layout.exit()
                return 0

            if cmd == "clear":
                conversation.clear()
                layout.clear_output()
                clear_read_files()  # Reset file tracking
                layout.set_helper("Conversation cleared")
                continue

            if cmd == "init":
                grok_dir = Path(os.getcwd()) / ".grok"
                grok_md = grok_dir / "GROK.md"

                if grok_dir.exists():
                    layout.set_helper(f".grok already exists in this project")
                    continue

                # Create .grok directory structure
                grok_dir.mkdir(parents=True, exist_ok=True)
                (grok_dir / "agents").mkdir(exist_ok=True)
                (grok_dir / "plans").mkdir(exist_ok=True)
                (grok_dir / "handoffs").mkdir(exist_ok=True)

                # Create GROK.md with project instructions
                grok_md_content = '''# Project Instructions for Grok

## Response Style

You are a senior software engineer providing technical assistance. Your responses should be:

### Professional & Precise
- Write like an engineer, not a social media influencer
- No excessive enthusiasm, emojis, or filler phrases
- Get to the point quickly and stay focused on the technical problem

### Well-Structured
- Use clear headings and sections for complex responses
- Format code blocks with appropriate language tags
- Use bullet points for lists, numbered steps for procedures
- Include file paths when referencing code: `src/module.py:42`

### Technically Sound
- Provide complete, working code - no placeholders like "// your code here"
- Explain the reasoning behind architectural decisions
- Note potential edge cases and error conditions
- Reference documentation or standards when relevant

### Concise
- Prefer short, direct answers over lengthy explanations
- Only elaborate when the complexity warrants it
- Avoid repeating information the user already knows

## Code Style

When writing code:
- Follow the existing project conventions
- Match the indentation and formatting of surrounding code
- Use meaningful variable and function names
- Add comments only where logic is non-obvious

## Project Context

Add project-specific context below:

```
Language:
Framework:
Build Tool:
Test Framework:
Key Directories:
  - src/       # Source code
  - tests/     # Test files
```

## Custom Instructions

Add any project-specific instructions here:

-
'''
                grok_md.write_text(grok_md_content)

                # Create example agent
                example_agent = grok_dir / "agents" / "code-reviewer.md"
                example_agent_content = '''---
name: code-reviewer
description: Reviews code for best practices, security, and style
tools: read_file, glob, grep, bash
color: #e06c75
---

# Code Reviewer Agent

You are a thorough code reviewer. When reviewing code:

## What to Check
- **Security**: SQL injection, XSS, auth issues, secrets in code
- **Performance**: N+1 queries, unnecessary loops, memory leaks
- **Best Practices**: Error handling, logging, naming conventions
- **Style**: Consistency with project patterns, clean code principles

## How to Review
1. First understand the context - read related files if needed
2. Look for issues systematically, category by category
3. Provide specific, actionable feedback with line references
4. Prioritize: security > correctness > performance > style

## Output Format
- Use `file.py:42` format for line references
- Group issues by severity (Critical, Warning, Suggestion)
- Include code examples for fixes when helpful
'''
                example_agent.write_text(example_agent_content)

                layout.append_output("")
                layout.append_output("@@TOOL@@ Write(.grok/GROK.md)")
                layout.append_output("  @@RESULT@@ Created project configuration")
                layout.append_output("@@TOOL@@ Write(.grok/agents/code-reviewer.md)")
                layout.append_output("  @@RESULT@@ Created example agent")
                layout.append_output("")
                layout.append_output("Initialized `.grok/` folder with:")
                layout.append_output("  - `GROK.md` - Project instructions")
                layout.append_output("  - `agents/code-reviewer.md` - Example custom agent")
                layout.append_output("  - `plans/` - Planning documents")
                layout.append_output("  - `handoffs/` - Session handoff files")
                layout.append_output("")
                layout.append_output("Edit `.grok/GROK.md` to customize how Grok responds.")
                layout.append_output("Use `@agent:code-reviewer` to invoke the example agent.")
                layout.append_output("")

                # Reload plugins to pick up new folder
                plugin_registry.reload()
                continue

            if cmd in ("help", "?"):
                layout.append_output("")
                layout.append_output("# grokCode")
                layout.append_output("AI coding assistant powered by Grok")
                layout.append_output("")
                layout.append_output("## Usage")
                layout.append_output("Type naturally to chat, or use commands below.")
                layout.append_output("`@file` to mention files \u00b7 `!cmd` to run bash")
                layout.append_output("")
                layout.append_output("## Commands")
                layout.append_output("  `/init`       Initialize project    `/help`       Help")
                layout.append_output("  `/agents`     Manage agents         `/agents new` Create agent")
                layout.append_output("  `/save`       Save history          `/load`       Load history")
                layout.append_output("  `/plugins`    Plugins               `/tools`      List tools")
                layout.append_output("  `/tasks`      Tasks                 `/plan`       Plan mode")
                layout.append_output("  `/clear`      Clear                 `/config`     Config")
                layout.append_output("  `/exit`       Exit")
                layout.append_output("")
                layout.append_output("## Shortcuts")
                layout.append_output("  `Ctrl+C` Cancel \u00b7 `Ctrl+C Ctrl+C` Exit \u00b7 `Ctrl+D` Exit")
                layout.append_output("  `PageUp/Down` Scroll \u00b7 `Shift+Tab` Cycle mode")
                layout.append_output("")
                continue

            if cmd == "tasks":
                from .tools.tasks import TaskStore
                store = TaskStore.get_instance()
                tasks = store.list_all()
                layout.append_output("")
                layout.append_output("## Tasks")
                if not tasks:
                    layout.append_output("  No active tasks")
                else:
                    for task in tasks:
                        status_icon = {"pending": "\u25cb", "in_progress": "\u25d0", "completed": "\u25cf"}.get(task.status.value, "?")
                        layout.append_output(f"  {status_icon} #{task.id} {task.subject}")
                layout.append_output("")
                continue

            if cmd == "agents" or cmd.startswith("agents "):
                # Check for subcommand: /agents new <name> [color]
                agent_args = cmd[7:].strip() if cmd.startswith("agents ") else ""

                if agent_args.startswith("new"):
                    # Interactive agent creation wizard
                    COLOR_PALETTE = {
                        "cyan": "#56b6c2",
                        "purple": "#c678dd",
                        "blue": "#61afef",
                        "red": "#e06c75",
                        "green": "#98c379",
                        "orange": "#d19a66",
                        "yellow": "#e5c07b",
                        "teal": "#5f9ea0",
                        "pink": "#ff79c6",
                        "gray": "#7f848e",
                    }

                    layout.append_output("")
                    layout.append_output("## Create New Agent")
                    layout.append_output("")
                    layout.append_output("**Step 1/3:** Describe what this agent does (be detailed)")
                    layout.append_output("Type your description and press Enter:")
                    layout.append_output("")

                    # Step 1: Get description
                    description_input = await layout.get_input_async()
                    if description_input is None or description_input is INTERRUPTED:
                        layout.append_output("Cancelled.")
                        continue
                    agent_description = description_input.strip()
                    if not agent_description:
                        layout.append_output("Cancelled - description required.")
                        continue
                    layout.append_output(f"> {agent_description[:80]}{'...' if len(agent_description) > 80 else ''}")
                    layout.append_output("")

                    # Step 2: Get color
                    layout.append_output("**Step 2/3:** Pick a color")
                    layout.append_output("  cyan · purple · blue · red · green · orange · yellow · teal · pink · gray")
                    layout.append_output("  Or enter a hex code like #ff79c6")
                    layout.append_output("")

                    color_input = await layout.get_input_async()
                    if color_input is None or color_input is INTERRUPTED:
                        layout.append_output("Cancelled.")
                        continue
                    color_input = color_input.strip().lower()
                    if not color_input:
                        color_input = "teal"
                    if color_input.startswith("#"):
                        resolved_color = color_input
                    else:
                        resolved_color = COLOR_PALETTE.get(color_input, "#5f9ea0")
                    layout.append_output(f"> {color_input} ({resolved_color})")
                    layout.append_output("")

                    # Step 3: Get name
                    layout.append_output("**Step 3/3:** Agent name (lowercase with dashes)")
                    layout.append_output("  Example: code-reviewer, test-runner, doc-writer")
                    layout.append_output("")

                    name_input = await layout.get_input_async()
                    if name_input is None or name_input is INTERRUPTED:
                        layout.append_output("Cancelled.")
                        continue
                    agent_name = name_input.strip().lower().replace(" ", "-")
                    if not agent_name:
                        layout.append_output("Cancelled - name required.")
                        continue
                    layout.append_output(f"> {agent_name}")
                    layout.append_output("")

                    # Create the agent file
                    grok_dir = Path(os.getcwd()) / ".grok" / "agents"
                    grok_dir.mkdir(parents=True, exist_ok=True)

                    agent_file = grok_dir / f"{agent_name}.md"
                    if agent_file.exists():
                        layout.append_output(f"Error: Agent `{agent_name}` already exists.")
                        continue

                    # Create agent with user's description as the prompt
                    template = f'''---
name: {agent_name}
description: {agent_description[:100]}
color: {resolved_color}
tools:
  - Read
  - Glob
  - Grep
  - Bash
---

# {agent_name.replace('-', ' ').title()} Agent

{agent_description}

## Guidelines

- Be thorough and precise
- Ask clarifying questions if needed
- Provide clear explanations
'''
                    agent_file.write_text(template)

                    layout.append_output(f"@@TOOL@@ Write(.grok/agents/{agent_name}.md)")
                    layout.append_output(f"  @@RESULT@@ Created agent")
                    layout.append_output("")
                    layout.append_output(f"Run with: `@agent:{agent_name}`")
                    layout.append_output("")

                    # Reload plugins to pick up new agent
                    plugin_registry.reload()
                    continue

                # Default: show agents list
                layout.append_output("")
                layout.append_output("## Manage Agents")
                layout.append_output("")
                layout.append_output("### Built-in")
                layout.append_output("  `explore`  Fast codebase exploration")
                layout.append_output("  `plan`     Design implementation approach")
                layout.append_output("  `general`  General-purpose tasks")

                plugin_agents = plugin_registry.list_agents()
                if plugin_agents:
                    layout.append_output("")
                    layout.append_output("### Project Agents")
                    for agent in plugin_agents[:15]:
                        desc = agent.description[:45] + "..." if len(agent.description) > 45 else agent.description
                        layout.append_output(f"  `{agent.name}`  {desc}")

                layout.append_output("")
                layout.append_output("### Running")
                running = agent_runner.get_running_agents()
                if running:
                    for aid in running:
                        layout.append_output(f"  \u25d0 {aid}")
                else:
                    layout.append_output("  No agents running")

                layout.append_output("")
                layout.append_output("### Actions")
                layout.append_output("  `/agents new <name> [color]`  Create a new agent")
                layout.append_output("  Use `@agent:<name>` to invoke an agent")
                layout.append_output("")
                continue

            if cmd == "tools":
                layout.append_output("")
                layout.append_output("## Available Tools")
                for tool in registry.list_tools():
                    desc = tool.description[:50] + "..." if len(tool.description) > 50 else tool.description
                    layout.append_output(f"  `{tool.name}`  {desc}")
                layout.append_output("")
                continue

            if cmd == "model":
                layout.append_output("")
                layout.append_output(f"## Model: `{model}`")
                layout.append_output("")
                continue

            if cmd == "config":
                layout.append_output("")
                layout.append_output("## Configuration")
                layout.append_output(f"  **Model:** `{model}`")
                layout.append_output(f"  **Working directory:** `{os.getcwd()}`")
                layout.append_output(f"  **Project files:** {', '.join(conversation.loaded_project_files) or 'None'}")
                layout.append_output(f"  **API:** xAI (api.x.ai)")
                layout.append_output("")
                continue

            if cmd == "save" or cmd.startswith("save "):
                save_args = cmd[5:].strip() if cmd.startswith("save ") else ""

                if save_args == "history":
                    # Save conversation history to file
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

                    # Save to .grok/history/ directory
                    history_dir = Path(os.getcwd()) / ".grok" / "history"
                    history_dir.mkdir(parents=True, exist_ok=True)

                    history_file = history_dir / f"conversation_{timestamp}.md"

                    # Build markdown content
                    content_lines = ["# Conversation History", ""]
                    content_lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    content_lines.append(f"**Model:** {model}")
                    content_lines.append("")
                    content_lines.append("---")
                    content_lines.append("")

                    for msg in conversation.get_messages():
                        role = msg.role.upper()
                        if role == "SYSTEM":
                            continue  # Skip system messages
                        content_lines.append(f"## {role}")
                        content_lines.append("")
                        content_lines.append(msg.content or "(no content)")
                        content_lines.append("")

                    history_file.write_text("\n".join(content_lines))

                    layout.append_output("")
                    layout.append_output(f"@@TOOL@@ Write(.grok/history/conversation_{timestamp}.md)")
                    layout.append_output(f"  @@RESULT@@ Saved {len(conversation.get_messages())} messages")
                    layout.append_output("")
                    continue

                # Default: show save options
                layout.append_output("")
                layout.append_output("## Save Options")
                layout.append_output("")
                layout.append_output("  `/save history`  Save conversation to .grok/history/")
                layout.append_output("")
                continue

            if cmd == "load" or cmd.startswith("load "):
                load_args = cmd[5:].strip() if cmd.startswith("load ") else ""

                if load_args == "history" or load_args.startswith("history "):
                    # Load conversation history from file
                    history_dir = Path(os.getcwd()) / ".grok" / "history"

                    # Check if specific file provided
                    file_arg = load_args[8:].strip() if load_args.startswith("history ") else ""

                    if file_arg:
                        # Load specific file
                        history_file = history_dir / file_arg
                        if not history_file.exists():
                            history_file = history_dir / f"{file_arg}.md"
                    else:
                        # Show available history files
                        if not history_dir.exists():
                            layout.append_output("")
                            layout.append_output("No saved history found. Use `/save history` first.")
                            layout.append_output("")
                            continue

                        history_files = sorted(history_dir.glob("*.md"), reverse=True)
                        if not history_files:
                            layout.append_output("")
                            layout.append_output("No saved history found. Use `/save history` first.")
                            layout.append_output("")
                            continue

                        layout.append_output("")
                        layout.append_output("## Saved Conversations")
                        layout.append_output("")
                        for hf in history_files[:10]:
                            layout.append_output(f"  `{hf.name}`")
                        layout.append_output("")
                        layout.append_output("Load with: `/load history <filename>`")
                        layout.append_output("")
                        continue

                    if not history_file.exists():
                        layout.append_output(f"File not found: {history_file.name}")
                        continue

                    # Parse the markdown file and restore messages
                    content = history_file.read_text()
                    lines = content.split("\n")

                    # Clear current conversation
                    conversation.clear()
                    layout.clear_output()

                    current_role = None
                    current_content = []
                    messages_loaded = 0

                    for line in lines:
                        if line.startswith("## USER"):
                            # Save previous message
                            if current_role and current_content:
                                msg_content = "\n".join(current_content).strip()
                                if current_role == "user":
                                    conversation.add_user_message(msg_content)
                                    layout.add_user_message(msg_content)
                                    messages_loaded += 1
                                elif current_role == "assistant":
                                    conversation.add_assistant_message(msg_content)
                                    layout.add_assistant_message(msg_content)
                                    messages_loaded += 1
                            current_role = "user"
                            current_content = []
                        elif line.startswith("## ASSISTANT"):
                            if current_role and current_content:
                                msg_content = "\n".join(current_content).strip()
                                if current_role == "user":
                                    conversation.add_user_message(msg_content)
                                    layout.add_user_message(msg_content)
                                    messages_loaded += 1
                                elif current_role == "assistant":
                                    conversation.add_assistant_message(msg_content)
                                    layout.add_assistant_message(msg_content)
                                    messages_loaded += 1
                            current_role = "assistant"
                            current_content = []
                        elif line.startswith("## ") or line.startswith("# ") or line.startswith("---") or line.startswith("**Date:") or line.startswith("**Model:"):
                            continue  # Skip headers and metadata
                        elif current_role:
                            current_content.append(line)

                    # Don't forget the last message
                    if current_role and current_content:
                        msg_content = "\n".join(current_content).strip()
                        if current_role == "user":
                            conversation.add_user_message(msg_content)
                            layout.add_user_message(msg_content)
                            messages_loaded += 1
                        elif current_role == "assistant":
                            conversation.add_assistant_message(msg_content)
                            layout.add_assistant_message(msg_content)
                            messages_loaded += 1

                    layout.append_output("")
                    layout.append_output(f"Loaded {messages_loaded} messages from {history_file.name}")
                    layout.append_output("")
                    continue

                # Default: show load options
                layout.append_output("")
                layout.append_output("## Load Options")
                layout.append_output("")
                layout.append_output("  `/load history`           List saved conversations")
                layout.append_output("  `/load history <file>`    Load specific conversation")
                layout.append_output("")
                continue

            if cmd == "plan":
                conversation.add_user_message("Enter plan mode - I want to plan an implementation before coding.")
                start_time = time.time()
                await run_conversation_turn(client, conversation, registry, ui, layout, start_time)
                continue

            if cmd == "compact":
                msgs = conversation.get_messages()
                if len(msgs) > 10:
                    layout.set_helper(f"Compacted conversation from {len(msgs)} to 10 messages")
                else:
                    layout.set_helper("Conversation is already compact")
                continue

            if cmd == "cost":
                layout.set_helper("Cost tracking: Feature coming soon")
                continue

            if cmd == "plugins":
                plugins = plugin_registry.list_plugins()
                layout.append_output("")
                layout.append_output("## Plugins")
                if plugins:
                    for p in plugins:
                        layout.append_output(f"  **{p.name}** v{p.version}")
                        layout.append_output(f"    {p.description}")
                        if p.agents:
                            layout.append_output(f"    Agents: {', '.join('`' + a.name + '`' for a in p.agents)}")
                        if p.commands:
                            layout.append_output(f"    Commands: {', '.join('`/' + c.name + '`' for c in p.commands)}")
                else:
                    layout.append_output("  No plugins loaded")
                    layout.append_output("  Use `/agents new <name>` to create one")
                layout.append_output("")
                continue

            # Check for plugin commands
            plugin_cmd = plugin_registry.get_command(cmd.split()[0] if ' ' in cmd else cmd)
            if plugin_cmd:
                args = user_input[len(cmd.split()[0]) + 1:].strip() if ' ' in user_input else ""
                prompt = plugin_cmd.prompt.replace("$ARGUMENTS", args or "(no arguments provided)")
                conversation.add_user_message(prompt)
                start_time = time.time()
                await run_conversation_turn(client, conversation, registry, ui, layout, start_time)
                continue

            # Skip if just a slash
            if user_input == "/":
                continue

            # Bash mode: ! prefix runs command directly
            if user_input.startswith("!"):
                bash_cmd = user_input[1:].strip()
                if bash_cmd:
                    import subprocess
                    ui.info(f"$ {bash_cmd}")
                    try:
                        result = subprocess.run(
                            bash_cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=120,
                            cwd=os.getcwd(),
                        )
                        output = result.stdout + result.stderr
                        if output.strip():
                            ui.info(output)
                        conversation.add_user_message(f"I ran: {bash_cmd}\n\nOutput:\n{output[:2000]}")
                    except subprocess.TimeoutExpired:
                        ui.error("Command timed out")
                    except Exception as e:
                        ui.error(f"Command failed: {e}")
                continue

            # If agent is busy, queue the message
            if layout._is_busy:
                layout.queue_message(user_input)
                continue

            # Check for explicit @agent: mention - directly invoke that agent
            import re
            agent_match = re.search(r'@agent:(\S+)', user_input)
            if agent_match:
                agent_name = agent_match.group(1)
                # Remove the @agent:name from the prompt
                prompt = re.sub(r'@agent:\S+\s*', '', user_input).strip()

                # Check if agent exists - first check built-in agents, then plugins
                BUILTIN_AGENTS = {"explore", "plan", "general"}
                agent_def = plugin_registry.get_agent(agent_name)
                is_builtin = agent_name in BUILTIN_AGENTS

                if agent_def or is_builtin:
                    layout.add_user_message(user_input)
                    layout.set_status(f"Running {agent_name}...")
                    layout.set_busy(True)

                    # Show agent start with custom color (built-ins have defaults)
                    if agent_def:
                        agent_color = getattr(agent_def, 'color', None) or "#5f9ea0"
                    else:
                        # Built-in agent colors
                        builtin_colors = {
                            "explore": "#61afef",  # Blue
                            "plan": "#c678dd",     # Purple
                            "general": "#5f9ea0",  # Teal
                        }
                        agent_color = builtin_colors.get(agent_name, "#5f9ea0")
                    layout.set_agent(agent_name, prompt[:40] if prompt else "", agent_color)

                    try:
                        result = await agent_runner.run_agent(agent_name, prompt or f"Help me with: {user_input}")

                        if result.success:
                            layout.add_assistant_message(result.output)
                            conversation.add_user_message(user_input)
                            conversation.add_assistant_message(result.output)
                        else:
                            layout.add_assistant_message(f"Agent failed: {result.error}\n\n{result.output}")
                    except Exception as e:
                        layout.add_assistant_message(f"Error running agent: {e}")
                    finally:
                        # Clean up all agent state
                        layout.clear_agent()
                        layout.clear_status()
                        layout.set_busy(False)
                        layout.reset_input_state()
                        # Process any messages that were queued during agent execution
                        while layout.has_queued_messages():
                            queued = layout.pop_queued_message()
                            if queued:
                                layout.add_user_message(queued)
                                conversation.add_user_message(queued)
                                layout.set_busy(True)
                                try:
                                    await run_conversation_turn(client, conversation, registry, ui, layout, time.time())
                                finally:
                                    layout.set_busy(False)
                                    layout.reset_input_state()
                    continue
                else:
                    layout.set_helper(f"Agent '{agent_name}' not found. Available: explore, plan, general or /agents to list custom.")
                    asyncio.create_task(_clear_helper_after(layout, 3.0))
                    continue

            # Show user message in chat chain
            layout.add_user_message(user_input)

            # Add user message and get response
            conversation.add_user_message(user_input)
            start_time = time.time()
            await run_conversation_turn(client, conversation, registry, ui, layout, start_time)

        except asyncio.CancelledError:
            return 0
        except Exception as e:
            ui.error(f"Error: {e}")


async def main_async() -> int:
    """Async main function"""
    parser = argparse.ArgumentParser(
        description="grokCode - AI Coding Assistant powered by Grok"
    )
    parser.add_argument(
        "-m", "--model",
        default="grok-4-1-fast-reasoning",
        help="Grok model to use (default: grok-4-1-fast-reasoning)",
    )
    parser.add_argument(
        "-p", "--prompt",
        help="Single prompt to run (non-interactive mode)",
    )
    parser.add_argument(
        "--api-key",
        help="xAI API key (or set XAI_API_KEY env var)",
    )
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Get API key
    api_key = args.api_key or os.environ.get("XAI_API_KEY")
    if not api_key:
        print("Error: XAI_API_KEY not found. Set it as an environment variable or use --api-key")
        return 1

    # Initialize components
    layout = ChatLayout()
    ui = ChatUI(layout)
    registry = create_default_registry()
    conversation = Conversation()

    # Set up agent UI callback
    from .ui.agents import set_layout_callback
    set_layout_callback(layout)

    # Load plugins
    plugin_registry = setup_default_plugin_dirs()

    try:
        async with GrokClient(api_key=api_key, model=args.model) as client:
            # Set up agent runner with status callback
            agent_runner = setup_agent_runner(registry, client)
            agent_runner.set_plugin_registry(plugin_registry)

            # Status callback that tracks tool calls for expand/collapse
            def agent_status_callback(status: str):
                layout.set_status(status)
                # If an agent is active, parse tool calls from status
                if layout._current_agent and status and "thinking" not in status.lower():
                    # Status format options:
                    # 1. "Agent name: tool_info" (explore agent)
                    # 2. "Tool(args)" (plugin agent)
                    tool_part = status
                    if ": " in status:
                        _, tool_part = status.split(": ", 1)
                    # Extract tool name and args: "glob(*.py)" -> ("glob", "*.py")
                    if "(" in tool_part and tool_part.endswith(")"):
                        tool_name = tool_part.split("(")[0].lower()
                        tool_args = tool_part[len(tool_name)+1:-1]
                        layout.add_tool_call(tool_name, tool_args, "")

            agent_runner.set_status_callback(agent_status_callback)

            # Non-interactive mode
            if args.prompt:
                conversation.add_user_message(args.prompt)
                start_time = time.time()
                # For non-interactive, we need a simpler output mechanism
                # Just print to stdout
                response = await client.chat_stream(
                    messages=conversation.get_messages(),
                    tools=registry.get_schemas(),
                    on_content=lambda x: print(x, end='', flush=True),
                )
                print()
                return 0

            # Interactive mode - run app and main loop concurrently
            async def run_app():
                await layout.run_async()

            async def run_main():
                # Wait a moment for the app to start
                await asyncio.sleep(0.1)
                ui.welcome(project_files=conversation.loaded_project_files, model=args.model)
                return await main_loop(
                    client, conversation, registry, plugin_registry,
                    agent_runner, layout, ui, args.model
                )

            # Run both concurrently - main_loop will call layout.exit() when done
            app_task = asyncio.create_task(run_app())
            main_task = asyncio.create_task(run_main())

            # Wait for main task to complete (it will exit the app)
            try:
                result = await main_task
            except Exception as e:
                layout.exit()
                raise
            finally:
                # Cancel app task if still running
                if not app_task.done():
                    app_task.cancel()
                    try:
                        await app_task
                    except asyncio.CancelledError:
                        pass

            return result

    except Exception as e:
        print(f"Fatal error: {e}")
        return 1


def main() -> int:
    """Main entry point"""
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
