"""Full-screen chat layout - input fixed at bottom, conversation above"""

import asyncio
import os
import re
import time as _time
import uuid
from typing import Optional, List
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout import Layout, HSplit, VSplit, Window, ConditionalContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.filters import has_completions, Condition
from pathlib import Path
import glob as globlib

# Syntax highlighting
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
    from pygments.formatters import Terminal256Formatter
    from pygments.util import ClassNotFound

    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False


class InterruptedInput:
    pass


INTERRUPTED = InterruptedInput()

# Permission modes (matches ApprovalMode enum)
MODES = ["auto", "approve", "manual"]
MODE_LABELS = {
    "auto": "auto-accept",
    "approve": "approve edits",
    "manual": "approve all",
}
MODE_ICONS = {
    "auto": "\u23f5\u23f5",      # ⏵⏵
    "approve": "\u25cb",         # ○
    "manual": "\u25a1",          # □
}

# Commands for completion
COMMANDS = {
    "help": "Show help",
    "init": "Initialize .grok in project",
    "agents": "Manage agents",
    "agents new": "Create new agent with color",
    "plugins": "List plugins",
    "tools": "List tools",
    "tasks": "Show tasks",
    "plan": "Plan mode",
    "save": "Save options",
    "save history": "Save conversation to file",
    "load": "Load options",
    "load history": "Load conversation from file",
    "clear": "Clear history",
    "config": "Configuration",
    "model": "Current model",
    "compact": "Compact context",
    "cost": "Token usage",
    "exit": "Exit",
}


def get_plugin_commands() -> dict[str, str]:
    """Get commands from loaded plugins"""
    try:
        from ..plugins.registry import PluginRegistry

        registry = PluginRegistry.get_instance()
        cmds = {}
        for cmd in registry.list_commands():
            desc = cmd.description[:35] + "..." if len(cmd.description) > 35 else cmd.description
            cmds[cmd.name] = desc
        return cmds
    except Exception:
        return {}


def get_history_files() -> list[tuple[str, str]]:
    """Get available history files for completion"""
    try:
        history_dir = Path(os.getcwd()) / ".grok" / "history"
        if not history_dir.exists():
            return []
        files = sorted(history_dir.glob("*.md"), reverse=True)
        result = []
        for f in files[:10]:
            # Extract date from filename for display
            name = f.stem
            if name.startswith("conversation_"):
                date_part = name[13:]  # Remove "conversation_"
                if len(date_part) >= 8:
                    desc = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
                else:
                    desc = ""
            else:
                desc = ""
            result.append((f.name, desc))
        return result
    except Exception:
        return []


class ChatCompleter(Completer):
    """Completer for slash commands and @ file mentions"""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Special case: /load history <file> completion
        if text.lower().startswith("/load history "):
            file_prefix = text[14:].lower()  # After "/load history "
            for filename, date_desc in get_history_files():
                if not file_prefix or filename.lower().startswith(file_prefix):
                    yield Completion(
                        filename,
                        start_position=-len(file_prefix) if file_prefix else 0,
                        display=filename,
                        display_meta=date_desc,
                    )
            return

        if text.startswith("/"):
            prefix = text[1:].lower()
            for cmd, desc in COMMANDS.items():
                if not prefix or cmd.startswith(prefix):
                    yield Completion(
                        "/" + cmd,
                        start_position=-len(text),
                        display=f"/{cmd}",
                        display_meta=desc,
                    )
            for cmd, desc in get_plugin_commands().items():
                if not prefix or cmd.startswith(prefix):
                    yield Completion(
                        "/" + cmd,
                        start_position=-len(text),
                        display=f"/{cmd}",
                        display_meta=desc,
                    )

        elif "@" in text:
            at_idx = text.rfind("@")
            path_prefix = text[at_idx + 1 :]
            search_path = path_prefix + "*" if path_prefix else "*"
            try:
                matches = globlib.glob(search_path)
                for match in sorted(matches)[:15]:
                    basename = os.path.basename(match)
                    if os.path.isdir(match):
                        basename += "/"
                    yield Completion(
                        match,
                        start_position=-len(path_prefix) if path_prefix else 0,
                        display=basename,
                    )
            except Exception:
                pass


STYLE = Style.from_dict(
    {
        "output": "#b0b0b0",
        "status": "#707070",
        "status.spinner": "#5f9ea0",
        "status.time": "#606060",
        "separator": "#3a3a3a",
        "input": "#e0e0e0",
        "prompt": "#5f9ea0",
        "toolbar": "bg:#0a0a0a #606060",
        "toolbar.mode": "#6b8e6b",
        "toolbar.mode-auto": "#98c379",    # Green - auto accept
        "toolbar.mode-approve": "#e5c07b", # Yellow - approve edits
        "toolbar.mode-manual": "#e06c75",  # Red - approve all
        "toolbar.files": "#5f9ea0",
        "toolbar.hint": "#4a4a4a",
        "queue": "#707070 italic",
        "queue.editing": "#5f9ea0 italic",
        "helper": "#606060 italic",
        "completion-menu": "noinherit #808080",
        "completion-menu.completion": "noinherit #808080",
        "completion-menu.completion.current": "noinherit reverse",
        "completion-menu.meta": "noinherit #606060",
        "completion-menu.meta.current": "noinherit reverse #888888",
        # Tool colors
        "tool.read": "#6b9bd1",  # Blue for Read
        "tool.write": "#d19a66",  # Orange for Write
        "tool.update": "#c678dd",  # Purple for Update/Edit
        "tool.glob": "#98c379",  # Green for Glob
        "tool.grep": "#56b6c2",  # Cyan for Grep
        "tool.bash": "#e5c07b",  # Yellow for Bash
        "tool.agent": "#e06c75",  # Red for Agent
        "tool.default": "#abb2bf",  # Gray for others
        "tool.result": "#5c6370",  # Dim for results
        "diff.add": "#98c379",  # Green for added
        "diff.remove": "#e06c75",  # Red for removed
        "user": "#61afef",  # Blue for user messages
    }
)


class ChatLayout:
    """Full-screen chat with fixed input at bottom, output scrolling above"""

    SPINNER_FRAMES = [
        "\u280b",
        "\u2819",
        "\u2839",
        "\u2838",
        "\u283c",
        "\u2834",
        "\u2826",
        "\u2827",
        "\u2807",
        "\u280f",
    ]
    SPINNER_THINKING = ["\u25d0", "\u25d3", "\u25d1", "\u25d2"]

    def __init__(self, history_file: str = None):
        if history_file is None:
            history_dir = Path.home() / ".grokcode"
            history_dir.mkdir(exist_ok=True)
            history_file = str(history_dir / "history")

        self.history = FileHistory(history_file)
        self.completer = ChatCompleter()

        # State
        self.mode_idx = 0
        self.files_changed = 0
        self.lines_added = 0
        self.lines_removed = 0
        self.status_text = ""
        self.status_time = 0.0
        self.status_start = 0.0
        self.input_tokens = 0
        self.output_tokens = 0

        # Spinner animation
        self._spinner_idx = 0
        self._spinner_task: Optional[asyncio.Task] = None

        # Output accumulator
        self._output_lines: List[str] = []

        # Message queue
        self._queued_messages: List[dict] = []
        self._is_busy = False

        # Approval state
        self._waiting_approval = False
        self._approval_response: Optional[str] = None

        # Helper text
        self._helper_text = ""

        # File mention (@) state
        self._file_matches: List[str] = []
        self._file_match_prefix = ""

        # Agent state
        self._current_agent: Optional[str] = None
        self._current_agent_task: str = ""
        self._agent_color: str = "#5f9ea0"  # Default cyan
        self._tool_calls_collapsed: bool = True  # Collapse tool calls by default
        self._agent_tool_count: int = 0  # Count of tool calls in current agent block
        self._agent_start_time: float = 0.0
        self._agent_status: str = ""  # Current agent status text
        self._agent_live_idx: int = -1  # Index of live status line in _output_lines

        # Input handling
        self._input_ready = asyncio.Event()
        self._current_input = ""
        self._interrupted = False
        self._exit = False
        self._auto_scroll = True
        self._scroll_position = 0  # 0 = bottom, positive = lines from bottom

        # Paste masking
        self._pasted_content: Optional[str] = None  # Stores actual pasted content
        self._last_escape_time = 0.0  # For escape-twice-to-clear
        self._escape_clear_task: Optional[asyncio.Task] = None

        self._setup_layout()

    def _get_terminal_width(self) -> int:
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 80

    def _get_terminal_height(self) -> int:
        try:
            return os.get_terminal_size().lines
        except OSError:
            return 24

    def _do_scroll(self, delta: int):
        """Scroll the output pane. Negative delta = show older content (up)"""
        # Estimate max scroll - use raw lines * 2 to account for formatting expansion
        # This ensures we can always scroll to the top
        max_scroll = len(self._output_lines) * 2

        if delta < 0:
            # Scrolling up - show older content
            self._auto_scroll = False
            self._scroll_position = min(max_scroll, self._scroll_position - delta)
        else:
            # Scrolling down - show newer content
            self._scroll_position = max(0, self._scroll_position - delta)
            if self._scroll_position == 0:
                self._auto_scroll = True
        if self.app.is_running:
            self.app.invalidate()

    def _setup_layout(self):
        """Set up the prompt_toolkit layout"""

        # Output control with cursor-based scrolling

        self.output_control = FormattedTextControl(
            self._get_output_text,
            focusable=False,
            show_cursor=False,
            get_cursor_position=self._get_cursor_position,
        )
        self.output_window = Window(
            content=self.output_control,
            wrap_lines=True,
            always_hide_cursor=True,
            cursorline=False,
        )

        # Status line - fixed just above input
        self.status_window = ConditionalContainer(
            Window(
                content=FormattedTextControl(self._get_status_line),
                height=1,
            ),
            filter=Condition(lambda: bool(self.status_text)),
        )

        # Separator
        def get_sep():
            width = self._get_terminal_width()
            return [("class:separator", "\u2500" * width)]

        sep_line = Window(
            content=FormattedTextControl(get_sep),
            height=1,
            style="class:separator",
        )

        # Queue display
        queue_window = ConditionalContainer(
            Window(
                content=FormattedTextControl(self._get_queue_display),
                height=Dimension(min=1, max=5),
            ),
            filter=Condition(self._has_queued),
        )

        # Input - multiline enabled for paste support
        self.input_buffer = Buffer(
            history=self.history,
            completer=self.completer,
            complete_while_typing=True,
            multiline=True,
            accept_handler=self._accept_input,
            on_text_changed=self._on_text_changed,
        )

        self.input_control = BufferControl(buffer=self.input_buffer)
        self.input_window = Window(
            content=self.input_control,
            height=1,
        )

        # Multiline indicator (shows when paste has multiple lines - but not when masked)
        self.multiline_indicator = ConditionalContainer(
            Window(
                content=FormattedTextControl(self._get_multiline_indicator),
                height=1,
                style="class:helper",
            ),
            filter=Condition(
                lambda: "\n" in self.input_buffer.text and self._pasted_content is None
            ),
        )

        input_area = HSplit(
            [
                VSplit(
                    [
                        Window(
                            content=FormattedTextControl([("class:prompt", "\u276f ")]),
                            width=2,
                            dont_extend_width=True,
                        ),
                        self.input_window,
                    ],
                    height=1,
                ),
                self.multiline_indicator,
            ]
        )

        # Completions
        completions = ConditionalContainer(
            CompletionsMenu(max_height=8),
            filter=has_completions,
        )

        # Helper text
        helper_window = ConditionalContainer(
            Window(
                content=FormattedTextControl(self._get_helper_text),
                height=1,
                style="class:helper",
            ),
            filter=Condition(lambda: bool(self._helper_text) or bool(self._file_matches)),
        )

        # Toolbar
        toolbar = Window(
            content=FormattedTextControl(self._get_toolbar),
            height=1,
            style="class:toolbar",
        )

        # Key bindings
        self.kb = KeyBindings()

        @self.kb.add("c-c")
        def handle_ctrl_c(event):
            self._interrupted = True
            self._input_ready.set()

        @self.kb.add("c-d")
        def handle_ctrl_d(event):
            self._exit = True
            self._input_ready.set()

        @self.kb.add("s-tab")
        def handle_shift_tab(event):
            self.mode_idx = (self.mode_idx + 1) % len(MODES)
            # Sync with permission manager
            from ..permissions import PermissionManager, ApprovalMode
            perm_mgr = PermissionManager.get_instance()
            mode_name = MODES[self.mode_idx]
            perm_mgr.set_mode(ApprovalMode(mode_name))

        @self.kb.add("escape")
        def handle_escape(event):
            buf = event.current_buffer
            if buf.complete_state:
                buf.cancel_completion()
                return

            now = _time.time()

            # If there's text in input, first escape clears it
            if buf.text:
                buf.text = ""
                self._pasted_content = None
                self._last_escape_time = now
                return

            # No text - check for double escape to interrupt
            if now - self._last_escape_time < 1.0:
                # Double escape with no text = interrupt
                self._interrupted = True
                self._input_ready.set()
                self._last_escape_time = 0.0
                self._helper_text = ""
            else:
                self._last_escape_time = now
                if self._is_busy:
                    self._helper_text = "Press Esc again to interrupt"

                    # Auto-clear helper after 1.5s
                    async def clear_escape_hint():
                        try:
                            await asyncio.sleep(1.5)
                            if self._helper_text == "Press Esc again to interrupt":
                                self._helper_text = ""
                                self._last_escape_time = 0.0
                                if self.app.is_running:
                                    self.app.invalidate()
                        except asyncio.CancelledError:
                            pass

                    if self._escape_clear_task and not self._escape_clear_task.done():
                        self._escape_clear_task.cancel()
                    self._escape_clear_task = asyncio.create_task(clear_escape_hint())
                    self.app.invalidate()

        @self.kb.add("up")
        def handle_up(event):
            buf = event.current_buffer
            if not buf.text and self._queued_messages:
                # Pop the last message from queue to edit it
                msg = self._queued_messages.pop()
                buf.text = msg
                buf.cursor_position = len(buf.text)
                self.app.invalidate()
            else:
                buf.history_backward()

        @self.kb.add("down")
        def handle_down(event):
            buf = event.current_buffer
            buf.history_forward()

        @self.kb.add("pageup", eager=True)
        def handle_pageup(event):
            self._do_scroll(-10)  # Show older content

        @self.kb.add("pagedown", eager=True)
        def handle_pagedown(event):
            self._do_scroll(10)  # Show newer content

        # Mouse wheel scroll - works in terminals that support it
        @self.kb.add(Keys.ScrollUp, eager=True)
        def handle_scroll_up(event):
            self._do_scroll(-3)  # Show older content

        @self.kb.add(Keys.ScrollDown, eager=True)
        def handle_scroll_down(event):
            self._do_scroll(3)  # Show newer content

        @self.kb.add("end", eager=True)
        def handle_end(event):
            # Jump to bottom
            self._scroll_position = 0
            self._auto_scroll = True
            self.app.invalidate()

        @self.kb.add("home", eager=True)
        def handle_home(event):
            # Jump to top
            self._auto_scroll = False
            formatted = self._get_output_text()
            line_count = sum(1 for style, text in formatted if text == "\n")
            self._scroll_position = line_count
            self.app.invalidate()

        @self.kb.add("c-o")
        def handle_ctrl_o(event):
            # Toggle tool call collapse/expand
            self._tool_calls_collapsed = not self._tool_calls_collapsed
            self.app.invalidate()

        @self.kb.add("/")
        def handle_slash(event):
            buf = event.current_buffer
            buf.insert_text("/")
            if buf.text == "/":
                buf.start_completion(select_first=False)

        @self.kb.add("@")
        def handle_at(event):
            buf = event.current_buffer
            buf.insert_text("@")
            # File matches will appear in helper text via _on_text_changed

        @self.kb.add("tab")
        def handle_tab(event):
            buf = event.current_buffer
            # If we have file matches for @ mentions
            if self._file_matches and "@" in buf.text:
                at_idx = buf.text.rfind("@")
                # Replace from @ to cursor with selected match
                match_type, name, desc = self._file_matches[0]
                if match_type == "dir":
                    name += "/"
                new_text = buf.text[: at_idx + 1] + name
                buf.text = new_text
                buf.cursor_position = len(new_text)
                self._clear_file_matches()
            # If we have history matches for /load history
            elif self._file_matches and buf.text.lower().startswith("/load history"):
                match_type, name, desc = self._file_matches[0]
                new_text = f"/load history {name}"
                buf.text = new_text
                buf.cursor_position = len(new_text)
                self._clear_file_matches()
            else:
                # Default tab behavior - try completion
                buf.start_completion(select_first=True)

        @self.kb.add("backspace")
        def handle_backspace(event):
            buf = event.current_buffer
            # If we have masked paste content and cursor is at end after ]
            if self._pasted_content is not None and buf.text.endswith("]"):
                # Clear entire mask and pasted content
                buf.text = ""
                self._pasted_content = None
            else:
                # Normal backspace
                buf.delete_before_cursor(1)

        @self.kb.add("enter")
        def handle_enter(event):
            # Submit on Enter (even with multiline content)
            buf = event.current_buffer
            if buf.text.strip():
                buf.validate_and_handle()

        # Layout
        bottom_section = HSplit(
            [
                self.status_window,
                sep_line,
                queue_window,
                input_area,
                completions,
                toolbar,
                helper_window,
            ]
        )

        root = HSplit(
            [
                self.output_window,
                bottom_section,
            ]
        )

        self.layout = Layout(root, focused_element=self.input_window)

        self.app = Application(
            layout=self.layout,
            key_bindings=self.kb,
            style=STYLE,
            full_screen=True,
            mouse_support=True,
        )

    def _on_text_changed(self, buff: Buffer):
        """Detect multiline paste, @ file mentions, /load history, and update helper text"""
        text = buff.text

        # If we already have masked content, don't re-process
        if self._pasted_content is not None:
            return

        # Check for /load history command
        if text.lower().startswith("/load history"):
            if len(text) > 13:  # Has space after "history"
                file_prefix = text[14:] if len(text) > 14 else ""
                self._update_history_matches(file_prefix)
            else:
                self._update_history_matches("")
        # Check for @ file mention
        elif "@" in text:
            at_idx = text.rfind("@")
            path_prefix = text[at_idx + 1 :]
            # Only show matches if we're at the end of the @ mention (cursor after @)
            if buff.cursor_position > at_idx:
                self._update_file_matches(path_prefix)
            else:
                self._clear_file_matches()
        else:
            self._clear_file_matches()

        # Detect multiline paste (more than 1 newline suggests paste)
        if "\n" in text and text.count("\n") >= 1:
            lines = text.split("\n")
            line_count = len(lines)

            # Create mask
            first_line = lines[0][:30]
            if len(lines[0]) > 30:
                first_line += "..."

            # Store actual content and replace with mask
            self._pasted_content = text
            mask = f"[{first_line} +{line_count - 1} lines]"
            buff.text = mask
            buff.cursor_position = len(mask)

    def _update_file_matches(self, prefix: str):
        """Update file matches for @ mention (files and agents)"""
        self._file_match_prefix = prefix
        matches = []

        # Built-in agents (always available)
        builtin_agents = [
            ("explore", "Fast codebase exploration and search"),
            ("plan", "Design implementation approaches"),
            ("general", "General-purpose multi-step tasks"),
        ]

        # Add built-in agents
        for name, desc in builtin_agents:
            if (
                not prefix
                or name.lower().startswith(prefix.lower())
                or (
                    prefix.lower().startswith("agent:")
                    and name.lower().startswith(prefix[6:].lower())
                )
            ):
                matches.append(("agent", f"agent:{name}", desc))

        # Get plugin/custom agents
        try:
            from ..plugins.registry import PluginRegistry

            registry = PluginRegistry.get_instance()
            for agent in registry.list_agents():
                agent_name = f"agent:{agent.name}"
                if (
                    not prefix
                    or agent.name.lower().startswith(prefix.lower())
                    or (
                        prefix.lower().startswith("agent:")
                        and agent.name.lower().startswith(prefix[6:].lower())
                    )
                ):
                    matches.append(("agent", agent_name, agent.description))
        except Exception:
            pass

        # Get plan files for @plan: mentions
        if not prefix or prefix.lower().startswith("plan") or prefix.lower().startswith("plan:"):
            try:
                plans_dir = Path(os.getcwd()) / ".grok" / "plans"
                if plans_dir.exists():
                    plan_prefix = prefix[5:] if prefix.lower().startswith("plan:") else ""
                    for plan_file in sorted(plans_dir.glob("*.md"), reverse=True)[:5]:
                        plan_name = plan_file.stem
                        if not plan_prefix or plan_name.lower().startswith(plan_prefix.lower()):
                            # Extract date from filename for description
                            desc = ""
                            if "_" in plan_name:
                                parts = plan_name.rsplit("_", 1)
                                if len(parts[1]) >= 8:
                                    desc = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]}"
                            matches.append(("plan", f"plan:{plan_name}", desc))
            except Exception:
                pass

        # Get file matches (only if not explicitly looking for agents or plans)
        if not prefix.lower().startswith("agent:") and not prefix.lower().startswith("plan:"):
            search_path = prefix + "*" if prefix else "*"
            try:
                file_matches = globlib.glob(search_path)
                for f in sorted(file_matches)[:6]:
                    is_dir = os.path.isdir(f)
                    matches.append(("dir" if is_dir else "file", f, ""))
            except Exception:
                pass

        # Store as list of tuples (type, name, description)
        self._file_matches = matches[:8]
        if self.app.is_running:
            self.app.invalidate()

    def _update_history_matches(self, prefix: str):
        """Update matches for /load history command"""
        self._file_match_prefix = prefix
        matches = []
        for filename, date_desc in get_history_files():
            if not prefix or filename.lower().startswith(prefix.lower()):
                matches.append(("history", filename, date_desc))
        self._file_matches = matches[:8]
        if self.app.is_running:
            self.app.invalidate()

    def _clear_file_matches(self):
        """Clear file match state"""
        if self._file_matches:
            self._file_matches = []
            self._file_match_prefix = ""
            if self.app.is_running:
                self.app.invalidate()

    def _accept_input(self, buff: Buffer):
        if self._is_busy:
            queued_text = self._pasted_content if self._pasted_content is not None else buff.text
            self.queue_message(queued_text)
            if self._pasted_content is not None:
                self._pasted_content = None
            buff.reset()
            return

        # Use pasted content if available, otherwise use buffer text
        if self._pasted_content is not None:
            self._current_input = self._pasted_content
            self._pasted_content = None
        else:
            self._current_input = buff.text
        buff.reset()
        self._input_ready.set()

    def _get_helper_text(self):
        # Show file/agent/history matches if we have them
        if self._file_matches:
            match_type = self._file_matches[0][0] if self._file_matches else ""
            # Choose prefix based on match type
            if match_type == "history":
                parts = [("class:helper", "  📁 ")]
            else:
                parts = [("class:helper", "  @ ")]
            for i, match in enumerate(self._file_matches):
                match_type, name, desc = match
                if match_type == "agent":
                    display = name.replace("agent:", "")
                    style = "#e06c75"  # Red/pink for agents
                elif match_type == "plan":
                    display = name.replace("plan:", "")
                    if desc:
                        display = f"{display} ({desc})"
                    style = "#98c379"  # Green for plans
                elif match_type == "dir":
                    display = os.path.basename(name) + "/"
                    style = "#5f9ea0"  # Cyan for directories
                elif match_type == "history":
                    display = name
                    if desc:
                        display = f"{name} ({desc})"
                    style = "#c678dd"  # Purple for history files
                else:
                    display = os.path.basename(name)
                    style = "#808080"  # Gray for files
                if i > 0:
                    parts.append(("class:helper", "  "))
                parts.append((style, display))
            return parts

        if not self._helper_text:
            return []
        return [("class:helper", f"  {self._helper_text}")]

    def _get_multiline_indicator(self):
        """Show indicator when input has multiple lines"""
        text = self.input_buffer.text
        if "\n" not in text:
            return []

        lines = text.split("\n")
        first_line = lines[0][:30]
        if len(lines[0]) > 30:
            first_line += "..."
        extra_lines = len(lines) - 1

        return [("class:helper", f"    [{first_line} +{extra_lines} lines]")]

    def set_helper(self, text: str):
        self._helper_text = text
        if self.app.is_running:
            self.app.invalidate()

    def clear_helper(self):
        self._helper_text = ""
        if self.app.is_running:
            self.app.invalidate()

    def _get_status_line(self):
        """Get the status line content (fixed above input)"""
        if not self.status_text:
            return []

        parts = []
        spinner = self._get_spinner()
        parts.append(("class:status.spinner", f"  {spinner} "))
        parts.append(("class:status", self.status_text))

        if self.status_start > 0:
            import time

            elapsed = time.time() - self.status_start
            if elapsed < 60:
                time_str = f"{elapsed:.1f}s"
            else:
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                time_str = f"{mins}m {secs}s"
            parts.append(("class:status.time", f" ({time_str})"))

        return parts

    def _get_queue_display(self):
        if not self._queued_messages:
            return []

        parts = []
        queue_frames = ["\u25f7", "\u25f6", "\u25f5", "\u25f4"]
        frame = queue_frames[self._spinner_idx % len(queue_frames)]

        # Show header
        parts.append(("#5c6370", f"  Queued ({len(self._queued_messages)}):\n"))
        for msg in self._queued_messages:
            display_msg = msg[:55] + "..." if len(msg) > 55 else msg
            parts.append(("#61afef", f"  {frame} "))
            parts.append(("#abb2bf", f"{display_msg}\n"))

        return parts

    def _get_spinner(self) -> str:
        if "Thinking" in self.status_text or "thinking" in self.status_text:
            frames = self.SPINNER_THINKING
        else:
            frames = self.SPINNER_FRAMES
        return frames[self._spinner_idx % len(frames)]

    def _get_toolbar(self):
        parts = []
        mode = MODES[self.mode_idx]
        mode_label = MODE_LABELS[mode]
        mode_icon = MODE_ICONS[mode]

        style_key = f"class:toolbar.mode-{mode}"
        parts.append((style_key, f"  {mode_icon} {mode_label}"))
        parts.append(("class:toolbar.hint", " (shift+Tab)"))

        if self.files_changed > 0:
            parts.append(("class:toolbar", " \u00b7 "))
            parts.append(
                (
                    "class:toolbar.files",
                    f'{self.files_changed} file{"s" if self.files_changed > 1 else ""}',
                )
            )
            if self.lines_added or self.lines_removed:
                parts.append(("class:toolbar", " "))
                if self.lines_added:
                    parts.append(("fg:ansigreen", f"+{self.lines_added}"))
                if self.lines_removed:
                    parts.append(("class:toolbar", " "))
                    parts.append(("fg:ansired", f"-{self.lines_removed}"))

        return parts

    def _get_cursor_position(self):
        """Get cursor position - always at end since we slice content for scrolling"""
        from prompt_toolkit.data_structures import Point

        formatted = self._get_output_text()
        if not formatted:
            return Point(x=0, y=0)
        line_count = sum(1 for style, text in formatted if text == "\n")
        return Point(x=0, y=line_count)

    def _get_tool_style(self, tool_text: str) -> str:
        """Get the style for a tool based on its name"""
        tool_lower = tool_text.lower()
        if tool_lower.startswith("read"):
            return "#6b9bd1"  # Blue
        elif tool_lower.startswith("write"):
            return "#d19a66"  # Orange
        elif tool_lower.startswith("update") or tool_lower.startswith("edit"):
            return "#c678dd"  # Purple
        elif tool_lower.startswith("glob"):
            return "#98c379"  # Green
        elif tool_lower.startswith("grep"):
            return "#56b6c2"  # Cyan
        elif tool_lower.startswith("bash") or tool_lower.startswith("$"):
            return "#e5c07b"  # Yellow
        elif tool_lower.startswith("agent"):
            return "#e06c75"  # Red/Pink
        else:
            return "#abb2bf"  # Gray

    def _parse_markdown_line(self, text: str, base_style: str = "") -> list:
        """Parse inline markdown and return formatted text tuples"""
        import re

        result = []
        pos = 0

        # Pattern for inline formatting: ***bold italic***, **bold**, *italic*, `code`
        pattern = re.compile(r"(\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)")

        for match in pattern.finditer(text):
            # Add text before match
            if match.start() > pos:
                result.append((base_style, text[pos : match.start()]))

            if match.group(2):  # ***bold italic***
                result.append(("bold italic", match.group(2)))
            elif match.group(3):  # **bold**
                result.append(("bold", match.group(3)))
            elif match.group(4):  # *italic*
                result.append(("italic", match.group(4)))
            elif match.group(5):  # `code`
                result.append(("#e5c07b", match.group(5)))  # Yellow for code

            pos = match.end()

        # Add remaining text
        if pos < len(text):
            result.append((base_style, text[pos:]))

        return result if result else [(base_style, text)]

    def _highlight_code(self, code: str, lang: str) -> list:
        """Syntax highlight code and return formatted tuples"""
        if not PYGMENTS_AVAILABLE:
            return [("#98c379", code)]

        try:
            if lang:
                lexer = get_lexer_by_name(lang, stripall=True)
            else:
                lexer = guess_lexer(code)
        except ClassNotFound:
            lexer = TextLexer()

        # Get tokens from pygments and convert to prompt_toolkit format
        result = []
        from pygments.token import Token

        # Token to color mapping (One Dark theme inspired)
        token_colors = {
            Token.Keyword: "#c678dd",  # Purple
            Token.Keyword.Namespace: "#c678dd",
            Token.Keyword.Type: "#e5c07b",
            Token.Name.Function: "#61afef",  # Blue
            Token.Name.Class: "#e5c07b",  # Yellow
            Token.Name.Builtin: "#56b6c2",  # Cyan
            Token.Name.Decorator: "#e5c07b",
            Token.String: "#98c379",  # Green
            Token.Number: "#d19a66",  # Orange
            Token.Operator: "#56b6c2",
            Token.Comment: "#5c6370 italic",  # Gray italic
            Token.Punctuation: "#abb2bf",
            Token.Name: "#e06c75",  # Red for names
            Token.Name.Variable: "#e06c75",
        }

        for token_type, value in lexer.get_tokens(code):
            # Find matching color (check parent types too)
            color = "#abb2bf"  # Default
            for t in token_type.split():
                if t in token_colors:
                    color = token_colors[t]
                    break
            result.append((color, value))

        return result

    def _render_table(self, rows: list, prefix: str = "") -> list:
        """Render a markdown table with box drawing characters"""
        if not rows:
            return []

        result = []

        # Parse all rows into cells
        parsed_rows = []
        for row in rows:
            cells = [c.strip() for c in row[1:-1].split("|")]
            parsed_rows.append(cells)

        if not parsed_rows:
            return []

        # Calculate column widths from ALL rows
        num_cols = max(len(r) for r in parsed_rows)
        col_widths = [0] * num_cols
        for row in parsed_rows:
            for i, cell in enumerate(row):
                if i < num_cols:
                    col_widths[i] = max(col_widths[i], len(cell) + 2)

        # Ensure minimum width
        col_widths = [max(w, 5) for w in col_widths]

        # Top border: ┌───┬───┐
        result.append(("#5c6370", f"{prefix}\u250c"))
        for i, width in enumerate(col_widths):
            result.append(("#5c6370", "\u2500" * width))
            if i < len(col_widths) - 1:
                result.append(("#5c6370", "\u252c"))
        result.append(("#5c6370", "\u2510"))
        result.append(("", "\n"))

        for row_idx, cells in enumerate(parsed_rows):
            # Data row: │ cell │ cell │
            result.append(("#5c6370", f"{prefix}\u2502"))
            for i in range(num_cols):
                cell = cells[i] if i < len(cells) else ""
                width = col_widths[i]
                if row_idx == 0:
                    # Header row - bold and centered
                    padded = cell.center(width - 2)
                    result.append(("bold", f" {padded} "))
                else:
                    # Data row - left aligned
                    padded = cell.ljust(width - 2)
                    result.append(("", f" {padded} "))
                if i < num_cols - 1:
                    result.append(("#5c6370", "\u2502"))
            result.append(("#5c6370", "\u2502"))
            result.append(("", "\n"))

            # After header row, add separator: ├───┼───┤
            if row_idx == 0 and len(parsed_rows) > 1:
                result.append(("#5c6370", f"{prefix}\u251c"))
                for i, width in enumerate(col_widths):
                    result.append(("#5c6370", "\u2500" * width))
                    if i < len(col_widths) - 1:
                        result.append(("#5c6370", "\u253c"))
                result.append(("#5c6370", "\u2524"))
                result.append(("", "\n"))

        # Bottom border: └───┴───┘
        result.append(("#5c6370", f"{prefix}\u2514"))
        for i, width in enumerate(col_widths):
            result.append(("#5c6370", "\u2500" * width))
            if i < len(col_widths) - 1:
                result.append(("#5c6370", "\u2534"))
        result.append(("#5c6370", "\u2518"))
        result.append(("", "\n"))

        return result

    def _format_content_line(self, content: str, indent: str = "") -> list:
        """Format a content line with markdown, returning formatted tuples"""
        result = []

        # Check for headers (with optional leading asterisks stripped)
        clean = content.lstrip()

        # Headers - check from most specific to least
        if clean.startswith("#### "):
            text = clean[5:].strip().replace("*", "")
            result.append(("#56b6c2", f"{indent}{text}"))  # Cyan for h4
        elif clean.startswith("### "):
            text = clean[4:].strip().replace("*", "")
            result.append(("bold #61afef", f"{indent}{text}"))
        elif clean.startswith("## "):
            text = clean[3:].strip().replace("*", "")
            result.append(("bold", f"{indent}\u2500 {text} \u2500"))
        elif clean.startswith("# "):
            text = clean[2:].strip().replace("*", "")
            result.append(("bold", f"{indent}\u2550 {text.upper()} \u2550"))
        # Lists
        elif clean.startswith("- "):
            result.append(("", f"{indent}\u2022 "))
            result.extend(self._parse_markdown_line(clean[2:]))
        elif clean.startswith("* ") and len(clean) > 2 and clean[2] != "*":
            # List item with * (but not **bold**)
            result.append(("", f"{indent}\u2022 "))
            result.extend(self._parse_markdown_line(clean[2:]))
        # Numbered lists
        elif clean and clean[0].isdigit():
            m = re.match(r"^(\d+)\.\s+(.*)$", clean)
            if m:
                result.append(("#5c6370", f"{indent}{m.group(1)}. "))
                result.extend(self._parse_markdown_line(m.group(2)))
            else:
                result.extend(self._parse_markdown_line(f"{indent}{clean}"))
        else:
            result.extend(self._parse_markdown_line(f"{indent}{clean}"))

        return result

    def _get_output_text(self):
        """Get formatted output text"""
        lines = self._output_lines.copy()

        # Format lines with colors
        result = []
        in_code_block = False
        code_lang = ""
        code_buffer = []
        in_table = False
        table_rows = []
        table_col_widths = []

        # Agent block tracking
        in_agent_block = False
        agent_name = ""
        agent_tool_count = 0

        for line in lines:
            # Handle agent block markers
            if line.startswith("@@AGENT_START@@ "):
                in_agent_block = True
                # Parse: name|task|color
                parts = line[16:].split("|")
                agent_name = parts[0] if parts else "agent"
                agent_task = parts[1] if len(parts) > 1 else ""
                agent_color = parts[2] if len(parts) > 2 else "#5f9ea0"
                agent_tool_count = 0

                # Show agent header: [⏺ name] task description
                result.append(("", "\n"))
                result.append((f"bg:{agent_color} #1e1e1e bold", f" \u23fa {agent_name} "))
                if agent_task:
                    display_task = agent_task[:50] + "..." if len(agent_task) > 50 else agent_task
                    result.append(("#abb2bf", f" {display_task}"))
                result.append(("", "\n"))
                continue

            elif line.startswith("@@AGENT_LIVE@@ "):
                # Parse: status|tool_count
                parts = line[15:].split("|")
                status_text = parts[0].strip() if parts and parts[0].strip() else "Thinking..."
                live_tool_count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0

                # Always show current status with spinner
                spinner_frames = ["◐", "◓", "◑", "◒"]
                import time as _t
                spinner = spinner_frames[int(_t.time() * 2) % 4]
                result.append(("#61afef", f"  {spinner} "))
                result.append(("#abb2bf", status_text))
                if live_tool_count > 1:
                    result.append(("#5c6370", f"  ({live_tool_count} tools)"))
                result.append(("", "\n"))

                # Show live task list below the status (if any)
                try:
                    from ..tools.tasks import TaskStore, TaskStatus
                    store = TaskStore.get_instance()
                    tasks = store.list_all()
                    if tasks:
                        for task in tasks[:10]:  # Limit to 10 tasks
                            if task.status == TaskStatus.COMPLETED:
                                result.append(("#98c379", "    ✓ "))
                                result.append(("#5c6370 strike", f"{task.subject[:50]}"))
                            elif task.status == TaskStatus.IN_PROGRESS:
                                result.append(("#e5c07b", "    ◐ "))
                                result.append(("#abb2bf", f"{task.subject[:50]}"))
                            else:
                                result.append(("#5c6370", "    ○ "))
                                result.append(("#abb2bf", f"{task.subject[:50]}"))
                            result.append(("", "\n"))
                except Exception:
                    pass
                continue

            elif line.startswith("@@AGENT_END@@ "):
                # Parse: name|tool_uses|tokens|elapsed
                parts = line[14:].split("|")
                end_agent_name = parts[0] if parts else ""
                tool_uses = (
                    int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else agent_tool_count
                )
                tokens = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                elapsed = float(parts[3]) if len(parts) > 3 else 0

                # Format elapsed time
                if elapsed >= 60:
                    time_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
                else:
                    time_str = f"{elapsed:.1f}s"

                # Format tokens
                if tokens >= 1000:
                    token_str = f"{tokens / 1000:.1f}k tokens"
                else:
                    token_str = f"{tokens} tokens" if tokens > 0 else ""

                # Show completion line: ⎿  Done (X tool uses · Xk tokens · Xm Xs)
                stats_parts = []
                if tool_uses > 0:
                    stats_parts.append(f"{tool_uses} tool uses")
                if token_str:
                    stats_parts.append(token_str)
                if elapsed > 0:
                    stats_parts.append(time_str)

                stats_str = " · ".join(stats_parts) if stats_parts else "Done"
                result.append(("#5c6370", f"  \u23bf  Done ({stats_str})"))
                result.append(("", "\n"))

                # Show expand/collapse hint if there are tool calls
                if tool_uses > 0 and self._tool_calls_collapsed:
                    result.append(("#5c6370", f"     (ctrl+o to expand {tool_uses} tool calls)"))
                    result.append(("", "\n"))

                result.append(("", "\n"))
                in_agent_block = False
                agent_name = ""
                agent_tool_count = 0
                continue

            # Skip tool calls if collapsed and in agent block
            if in_agent_block and self._tool_calls_collapsed:
                if (
                    line.startswith("@@TOOL@@ ")
                    or line.strip().startswith("@@RESULT@@ ")
                    or line.strip().startswith("@@DIFF_")
                    or line.startswith("    - ")
                    or line.startswith("    + ")
                ):
                    if line.startswith("@@TOOL@@ "):
                        agent_tool_count += 1
                    continue
            # Detect prefix (⏺ for assistant first line, or indentation)
            prefix = ""
            content = line

            if line.startswith("\u23fa "):  # ⏺ assistant message start
                prefix = "\u23fa "
                content = line[2:]
            elif line.startswith("  ") and not line.startswith("    "):  # Assistant continuation
                prefix = "  "
                content = line[2:]

            # Handle code blocks (check content, not full line)
            content_stripped = content.strip() if content else ""

            if content_stripped.startswith("```"):
                if not in_code_block:
                    # Starting code block
                    in_code_block = True
                    code_lang = content_stripped[3:].strip()
                    code_buffer = []
                    result.append(("#5c6370", f"{prefix}\u250c\u2500\u2500 {code_lang or 'code'} "))
                    result.append(("#5c6370", "\u2500" * 20))
                    result.append(("", "\n"))
                else:
                    # Ending code block - now highlight the buffered code
                    in_code_block = False
                    if code_buffer:
                        full_code = "\n".join(code_buffer)
                        highlighted = self._highlight_code(full_code, code_lang)
                        # Split highlighted code back into lines
                        current_line = [("#5c6370", f"{prefix}\u2502 ")]
                        for style, text in highlighted:
                            if "\n" in text:
                                parts = text.split("\n")
                                for i, part in enumerate(parts):
                                    if i > 0:
                                        # Finish previous line, start new one
                                        result.extend(current_line)
                                        result.append(("", "\n"))
                                        current_line = [("#5c6370", f"{prefix}\u2502 ")]
                                    if part:
                                        current_line.append((style, part))
                            else:
                                current_line.append((style, text))
                        if current_line != [("#5c6370", f"{prefix}\u2502 ")]:
                            result.extend(current_line)
                            result.append(("", "\n"))
                    result.append(("#5c6370", f"{prefix}\u2514"))
                    result.append(("#5c6370", "\u2500" * 24))
                    result.append(("", "\n"))
                    code_buffer = []
                continue

            if in_code_block:
                code_buffer.append(content)
                continue

            # Handle tables - collect all rows, render when table ends
            is_table_row = content_stripped.startswith("|") and content_stripped.endswith("|")
            is_separator = (
                is_table_row
                and "---" in content_stripped
                and not any(
                    c.isalpha()
                    for c in content_stripped.replace("|", "")
                    .replace("-", "")
                    .replace(":", "")
                    .strip()
                )
            )

            # If we have buffered rows and this isn't a table row, render the table
            if table_rows and not is_table_row:
                result.extend(self._render_table(table_rows, prefix))
                table_rows = []
                in_table = False

            if is_table_row:
                if is_separator:
                    # Mark that we've seen the separator (header is complete)
                    in_table = True
                else:
                    table_rows.append(content_stripped)
                continue

            # Tool markers (these are raw, not prefixed)
            if line.startswith("@@TOOL@@ "):
                tool_text = line[9:]
                style = self._get_tool_style(tool_text)
                result.append((style, f"\u23fa {tool_text}"))
                result.append(("", "\n"))
            elif line.strip().startswith("@@RESULT@@ "):
                result.append(("#5c6370", f"  \u23bf {line.strip()[11:]}"))
                result.append(("", "\n"))
            elif line.strip().startswith("@@DIFF_REMOVE@@ "):
                result.append(("#e06c75", f"  \u2796 {line.strip()[16:]}"))
                result.append(("", "\n"))
            elif line.strip().startswith("@@DIFF_ADD@@ "):
                result.append(("#98c379", f"  \u2795 {line.strip()[13:]}"))
                result.append(("", "\n"))
            elif line.startswith("@@PLAN_TASK@@ "):
                # Format: @@PLAN_TASK@@ id|status|subject
                # Look up current status from TaskStore for live updates
                parts = line[14:].split("|", 2)
                task_id = parts[0] if parts else "?"
                task_status = parts[1] if len(parts) > 1 else "pending"
                task_subject = parts[2] if len(parts) > 2 else ""
                # Try to get current status from TaskStore
                try:
                    from ..tools.tasks import TaskStore

                    store = TaskStore.get_instance()
                    task = store.get(task_id)
                    if task:
                        task_status = task.status.value
                except Exception:
                    pass
                if task_status == "completed":
                    # Checkmark with strikethrough (dim + strikethrough style)
                    result.append(("#98c379", "  ✓ "))
                    result.append(("#5c6370 strike", task_subject))
                elif task_status == "in_progress":
                    # In progress indicator
                    result.append(("#61afef", "  ◐ "))
                    result.append(("#abb2bf", task_subject))
                else:
                    # Pending checkbox
                    result.append(("#5c6370", "  ☐ "))
                    result.append(("#abb2bf", task_subject))
                result.append(("", "\n"))
            elif line.startswith("    - "):
                result.append(("#e06c75", f"    \u2212 {line[6:]}"))
                result.append(("", "\n"))
            elif line.startswith("    + "):
                result.append(("#98c379", f"    + {line[6:]}"))
                result.append(("", "\n"))
            # User message (> for first line, >  for continuations)
            elif line.startswith("> "):
                if line.startswith(">  "):
                    # Continuation line
                    result.append(("#61afef", f"  {line[3:]}"))
                else:
                    # First line
                    result.append(("#61afef", f"\u276f {line[2:]}"))
                result.append(("", "\n"))
            # Thinking indicator
            elif line.startswith("\u2733 "):
                result.append(("#5c6370", line))
                result.append(("", "\n"))
            # Empty line
            elif not line.strip():
                result.append(("", line))
                result.append(("", "\n"))
            # Assistant message with prefix - format the content
            elif prefix:
                result.append(("#abb2bf", prefix))
                result.extend(self._format_content_line(content))
                result.append(("", "\n"))
            # Headers at line start (not indented)
            elif line.startswith("### ") or line.startswith("## ") or line.startswith("# "):
                result.extend(self._format_content_line(line))
                result.append(("", "\n"))
            # Regular text with inline markdown
            else:
                result.extend(self._parse_markdown_line(line))
                result.append(("", "\n"))

        # Flush any remaining table
        if table_rows:
            result.extend(self._render_table(table_rows, ""))

        # Remove trailing newline if present
        if result and result[-1] == ("", "\n"):
            result.pop()

        # Convert result to lines for slicing/display
        lines = []
        current_line = []
        for item in result:
            current_line.append(item)
            if item == ("", "\n"):
                lines.append(current_line)
                current_line = []
        if current_line:
            lines.append(current_line)

        total_lines = len(lines)
        visible_height = self._get_terminal_height() - 6  # Account for UI elements

        # If content fits in visible area, return as-is
        if total_lines <= visible_height:
            return result

        # Calculate visible window based on scroll position
        if self._auto_scroll:
            # Auto-scroll: show bottom portion
            start_line = max(0, total_lines - visible_height)
            end_line = total_lines
        else:
            # Manual scroll: show based on scroll_position
            start_line = max(0, total_lines - self._scroll_position - visible_height)
            end_line = max(visible_height, total_lines - self._scroll_position)
            # Clamp to valid range
            start_line = max(0, min(start_line, total_lines - visible_height))
            end_line = min(total_lines, start_line + visible_height)

        # Rebuild result from sliced lines
        sliced_result = []
        for line in lines[start_line:end_line]:
            sliced_result.extend(line)

        # Add scroll indicator at top if not at the very top
        if start_line > 0:
            sliced_result = [
                ("#5c6370", f"\u2191 {start_line} more lines above \u2191"),
                ("", "\n"),
            ] + sliced_result

        # Add scroll indicator at bottom if not at the very bottom (only when manually scrolled)
        if not self._auto_scroll and end_line < total_lines:
            sliced_result.append(("", "\n"))
            sliced_result.append(
                ("#5c6370", f"\u2193 {total_lines - end_line} more lines below \u2193")
            )

        return sliced_result

    def append_output(self, text: str):
        self._output_lines.append(text)
        if self.app.is_running:
            self.app.invalidate()

    def clear_output(self):
        self._output_lines = []
        self._auto_scroll = True
        if self.app.is_running:
            self.app.invalidate()

    def add_user_message(self, text: str):
        # Scroll to bottom for new message
        self._auto_scroll = True
        self._scroll_position = 0
        self._output_lines.append("")
        lines = text.split("\n")
        # Use >  prefix for all user message lines (first line and continuations)
        for i, line in enumerate(lines):
            if i == 0:
                self._output_lines.append(f"> {line}")
            else:
                self._output_lines.append(f">  {line}")  # >  for continuation
        self._output_lines.append("")
        if self.app.is_running:
            self.app.invalidate()

    def add_assistant_message(self, text: str, elapsed: float = 0):
        # Scroll to bottom for new response
        self._auto_scroll = True
        self._scroll_position = 0
        self._output_lines.append("")
        lines = text.strip().split("\n")
        if lines:
            self._output_lines.append(f"\u23fa {lines[0]}")
            for line in lines[1:]:
                if line.strip():
                    self._output_lines.append(f"  {line}")
                else:
                    self._output_lines.append("")

        if elapsed > 0:
            self._output_lines.append("")
            if elapsed < 60:
                time_str = f"{elapsed:.0f}s"
            else:
                mins = int(elapsed // 60)
                secs = int(elapsed % 60)
                time_str = f"{mins}m {secs}s"
            self._output_lines.append(f"\u2733 Thinking for {time_str}")

        self._output_lines.append("")
        if self.app.is_running:
            self.app.invalidate()

    def set_agent(self, agent_name: str, task: str = "", color: str = "#5f9ea0"):
        """Set the current running agent"""
        self._current_agent = agent_name
        self._current_agent_task = task
        self._agent_color = color
        self._agent_tool_count = 0
        self._agent_start_time = _time.time()
        self._agent_status = "Thinking..."
        # Format: @@AGENT_START@@ name|task|color
        self._output_lines.append(f"@@AGENT_START@@ {agent_name}|{task}|{color}")
        # Add live status line that will be updated
        self._agent_live_idx = len(self._output_lines)
        self._output_lines.append(f"@@AGENT_LIVE@@ {self._agent_status}|0")
        if self.app.is_running:
            self.app.invalidate()

    def update_agent_status(self, status: str, tool_count: int = 0):
        """Update the current agent's status text"""
        if self._current_agent and self._agent_live_idx >= 0:
            self._agent_status = status
            # Update tool count if provided (from external agents)
            if tool_count > 0:
                self._agent_tool_count = tool_count
            # Update the live status line
            self._output_lines[self._agent_live_idx] = (
                f"@@AGENT_LIVE@@ {status}|{self._agent_tool_count}"
            )
            if self.app.is_running:
                self.app.invalidate()

    def clear_agent(self, tool_uses: int = 0, tokens: int = 0):
        """Clear the current agent and show completion stats"""
        if self._current_agent:
            elapsed = _time.time() - getattr(self, "_agent_start_time", _time.time())
            tool_uses = tool_uses or self._agent_tool_count
            # Remove the live status line
            if self._agent_live_idx >= 0 and self._agent_live_idx < len(self._output_lines):
                if self._output_lines[self._agent_live_idx].startswith("@@AGENT_LIVE@@"):
                    self._output_lines.pop(self._agent_live_idx)
            self._agent_live_idx = -1
            # Format: @@AGENT_END@@ name|tool_uses|tokens|elapsed
            self._output_lines.append(
                f"@@AGENT_END@@ {self._current_agent}|{tool_uses}|{tokens}|{elapsed:.1f}"
            )
            self._current_agent = None
            self._current_agent_task = ""
            self._agent_tool_count = 0
            self._agent_status = ""
            if self.app.is_running:
                self.app.invalidate()

    def add_tool_call(
        self,
        tool_name: str,
        label: str,
        result: str = "",
        lines_added: int = 0,
        lines_removed: int = 0,
    ):
        if tool_name in ("read_file", "read"):
            display_name = "Read"
        elif tool_name in ("write_file", "write"):
            display_name = "Write"
        elif tool_name in ("edit_file", "edit"):
            display_name = "Update"
        elif tool_name in ("bash", "bash_output"):
            display_name = "Bash"
        elif tool_name == "glob":
            display_name = "Glob"
        elif tool_name == "grep":
            display_name = "Grep"
        elif tool_name == "task":
            display_name = "Agent"
        else:
            display_name = tool_name.replace("_", " ").title()

        # Track tool calls under current agent and update live status
        if self._current_agent:
            self._agent_tool_count += 1
            # Update live status line with current tool
            status_text = f"{display_name}({label[:40]}{'...' if len(label) > 40 else ''})"
            if self._agent_live_idx >= 0 and self._agent_live_idx < len(self._output_lines):
                self._output_lines[self._agent_live_idx] = (
                    f"@@AGENT_LIVE@@ {status_text}|{self._agent_tool_count}"
                )

        self._output_lines.append(f"@@TOOL@@ {display_name}({label})")

        if lines_added > 0 or lines_removed > 0:
            change_info = []
            if lines_added > 0:
                change_info.append(f"+{lines_added}")
            if lines_removed > 0:
                change_info.append(f"-{lines_removed}")
            self._output_lines.append(f"  @@RESULT@@ {' '.join(change_info)} lines")
        elif result:
            first_line = result.strip().split("\n")[0][:80]
            if first_line:
                self._output_lines.append(f"  @@RESULT@@ {first_line}")

        if self.app.is_running:
            self.app.invalidate()

    def add_file_diff(self, filepath: str, old_content: str, new_content: str):
        """Show a diff of file changes"""
        short_path = filepath.split("/")[-1] if "/" in filepath else filepath

        old_lines = old_content.split("\n") if old_content else []
        new_lines = new_content.split("\n") if new_content else []

        # Simple diff display - show removed then added
        self._output_lines.append(f"@@TOOL@@ Update({short_path})")

        # Show a few lines of context
        max_preview = 5

        if old_lines:
            removed_count = len(old_lines)
            self._output_lines.append(f"  @@DIFF_REMOVE@@ -{removed_count} lines")
            for i, line in enumerate(old_lines[:max_preview]):
                self._output_lines.append(f"    - {line[:60]}")
            if len(old_lines) > max_preview:
                self._output_lines.append(f"    ... +{len(old_lines) - max_preview} more")

        if new_lines:
            added_count = len(new_lines)
            self._output_lines.append(f"  @@DIFF_ADD@@ +{added_count} lines")
            for i, line in enumerate(new_lines[:max_preview]):
                self._output_lines.append(f"    + {line[:60]}")
            if len(new_lines) > max_preview:
                self._output_lines.append(f"    ... +{len(new_lines) - max_preview} more")

        if self.app.is_running:
            self.app.invalidate()

    def set_busy(self, busy: bool):
        self._is_busy = busy

    def is_interrupted(self) -> bool:
        """Check if user has requested interruption (escape twice)"""
        return self._interrupted

    def clear_interrupted(self):
        """Clear the interrupted flag"""
        self._interrupted = False

    def reset_input_state(self):
        """Reset all input-related state for a fresh prompt"""
        self._interrupted = False
        self._exit = False
        self._current_input = ""
        self._input_ready.clear()
        self._helper_text = ""
        # Reset auto-scroll to bottom
        self._auto_scroll = True
        self._scroll_position = 0
        if self.app.is_running:
            # Ensure input window is focused
            self.app.layout.focus(self.input_window)
            self.app.invalidate()

    def queue_message(self, message: str):
        self._queued_messages.append(message)
        if self.app.is_running:
            self.app.invalidate()

    def pop_queued_message(self) -> Optional[str]:
        if self._queued_messages:
            msg = self._queued_messages.pop(0)
            if self.app.is_running:
                self.app.invalidate()
            return msg
        return None

    def has_queued_messages(self) -> bool:
        return bool(self._queued_messages)

    def _has_queued(self) -> bool:
        """Check if there are queued messages (for conditional filter)"""
        return bool(self._queued_messages)

    async def _animate_spinner(self):
        try:
            while self.status_text:
                await asyncio.sleep(0.1)
                self._spinner_idx += 1
                if self.app.is_running:
                    self.app.invalidate()
        except asyncio.CancelledError:
            pass

    def set_status(self, text: str, input_tokens: int = 0, output_tokens: int = 0):
        import time

        was_empty = not self.status_text
        self.status_text = text

        if input_tokens > 0:
            self.input_tokens = input_tokens
        if output_tokens > 0:
            self.output_tokens = output_tokens

        if was_empty and text:
            self.status_start = time.time()
            self._spinner_idx = 0

        if text and self._spinner_task is None and self.app.is_running:
            self._spinner_task = asyncio.create_task(self._animate_spinner())

        if self.app.is_running:
            self.app.invalidate()

    def clear_status(self):
        self.status_text = ""
        self.status_start = 0

        if self._spinner_task:
            self._spinner_task.cancel()
            self._spinner_task = None

        if self.app.is_running:
            self.app.invalidate()

    def set_file_changes(self, files: int, added: int = 0, removed: int = 0):
        self.files_changed = files
        self.lines_added = added
        self.lines_removed = removed
        if self.app.is_running:
            self.app.invalidate()

    def clear_changes(self):
        self.files_changed = 0
        self.lines_added = 0
        self.lines_removed = 0
        if self.app.is_running:
            self.app.invalidate()

    @property
    def current_mode(self) -> str:
        return MODES[self.mode_idx]

    async def get_input_async(self) -> Optional[str]:
        self._input_ready.clear()
        self._current_input = ""
        self._interrupted = False
        self._exit = False

        await self._input_ready.wait()

        if self._exit:
            return None
        if self._interrupted:
            return INTERRUPTED

        return self._current_input

    async def run_async(self):
        await self.app.run_async()

    def show_error_overlay(self, error: str):
        \"\"\"Show persistent error above input\"\"\"
        self.clear_status()
        self._output_lines.append(\"\")

        self._output_lines.append(f\"@@ERROR_BLOCK@@ {error}\")
        self._output_lines.append(\"Press any key to dismiss...\")

        if self.app.is_running:
            self.app.invalidate()

    def exit(self):
        self.app.exit()

    async def prompt_approval(self, tool_desc: str, danger_reason: str = None) -> str:
        """
        Prompt user for tool approval.
        Returns: 'yes', 'no', or 'always'
        """
        # Show the approval prompt in helper area
        if danger_reason:
            self._helper_text = f"⚠️  {danger_reason}: {tool_desc}"
        else:
            self._helper_text = f"Approve? {tool_desc}"

        # Store original input and set up for approval
        original_text = self.input_buffer.text
        self.input_buffer.text = ""

        # Show options
        self.append_output("")
        self.append_output(f"@@TOOL@@ {tool_desc}")
        if danger_reason:
            self.append_output(f"  ⚠️  DANGEROUS: {danger_reason}")
        self.append_output("  [y]es  [n]o  [a]lways (save to permissions)")

        if self.app.is_running:
            self.app.invalidate()

        # Wait for single key input
        self._approval_response = None
        self._waiting_approval = True

        # Set up temporary key binding for approval
        @self.kb.add('y')
        def approve_yes(event):
            if self._waiting_approval:
                self._approval_response = 'yes'
                self._waiting_approval = False
                self._input_ready.set()

        @self.kb.add('n')
        def approve_no(event):
            if self._waiting_approval:
                self._approval_response = 'no'
                self._waiting_approval = False
                self._input_ready.set()

        @self.kb.add('a')
        def approve_always(event):
            if self._waiting_approval:
                self._approval_response = 'always'
                self._waiting_approval = False
                self._input_ready.set()

        @self.kb.add('escape')
        def approve_escape(event):
            if self._waiting_approval:
                self._approval_response = 'no'
                self._waiting_approval = False
                self._input_ready.set()

        self._input_ready.clear()
        await self._input_ready.wait()

        # Clean up
        self._waiting_approval = False
        self._helper_text = ""

        # Show result
        response = self._approval_response or 'no'
        if response == 'yes':
            self.append_output("  ✓ Approved")
        elif response == 'always':
            self.append_output("  ✓ Approved (saved)")
        else:
            self.append_output("  ✗ Denied")

        if self.app.is_running:
            self.app.invalidate()

        return response
