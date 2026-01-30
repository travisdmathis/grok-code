"""Input handling with bottom toolbar"""

import os
import glob as globlib
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.layout.processors import BeforeInput
from pathlib import Path

from .console import console


class InterruptedInput:
    pass


INTERRUPTED = InterruptedInput()

# Permission modes (cycle with shift+tab)
MODES = ["auto", "plan", "manual"]
MODE_LABELS = {
    "auto": "auto-accept",
    "plan": "plan mode",
    "manual": "approve edits",
}

# Commands
COMMANDS = {
    "help": "Show help",
    "agents": "List agents",
    "plugins": "List plugins",
    "tools": "List tools",
    "tasks": "Show tasks",
    "plan": "Plan mode",
    "clear": "Clear history",
    "config": "Configuration",
    "model": "Change model",
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


class GrokCompleter(Completer):
    """Completer for slash commands and @ file mentions"""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if text.startswith("/"):
            prefix = text[1:].lower()
            for cmd, desc in COMMANDS.items():
                if not prefix or cmd.startswith(prefix):
                    yield Completion(
                        "/" + cmd,
                        start_position=-len(text),
                        display=HTML(f'<style fg="cyan">/{cmd}</style>'),
                        display_meta=desc,
                    )
            for cmd, desc in get_plugin_commands().items():
                if not prefix or cmd.startswith(prefix):
                    yield Completion(
                        "/" + cmd,
                        start_position=-len(text),
                        display=HTML(f'<style fg="yellow">/{cmd}</style>'),
                        display_meta=desc,
                    )

        elif "@" in text:
            at_idx = text.rfind("@")
            path_prefix = text[at_idx + 1:]
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


# Dark theme style for grokCode
STYLE = Style.from_dict({
    'prompt': 'ansicyan bold',
    'bottom-toolbar': 'bg:#1a1a1a #888888',
    'bottom-toolbar.text': '#888888',
    'mode': 'fg:ansigreen',
    'files': 'fg:ansicyan',
    'line': 'fg:#444444',
    'completion-menu': 'bg:#1a1a1a #cccccc',
    'completion-menu.completion': 'bg:#1a1a1a #cccccc',
    'completion-menu.completion.current': 'bg:#333333 #ffffff',
})


class InputHandler:
    def __init__(self, history_file=None):
        if history_file is None:
            history_dir = Path.home() / ".grokcode"
            history_dir.mkdir(exist_ok=True)
            history_file = str(history_dir / "history")

        self.history = FileHistory(history_file)
        self.completer = GrokCompleter()

        # State
        self.mode_idx = 0  # Current mode index
        self.files_changed = 0
        self.lines_added = 0
        self.lines_removed = 0
        self.status_message = ""

        bindings = KeyBindings()

        @bindings.add("/")
        def handle_slash(event):
            buf = event.current_buffer
            buf.insert_text("/")
            if buf.text == "/":
                buf.start_completion(select_first=False)

        @bindings.add("@")
        def handle_at(event):
            buf = event.current_buffer
            buf.insert_text("@")
            buf.start_completion(select_first=False)

        @bindings.add("escape")
        def handle_escape(event):
            buf = event.current_buffer
            if buf.complete_state:
                buf.cancel_completion()

        @bindings.add("s-tab")  # Shift+Tab
        def handle_shift_tab(event):
            # Cycle through modes
            self.mode_idx = (self.mode_idx + 1) % len(MODES)

        self.session = PromptSession(
            history=self.history,
            key_bindings=bindings,
            completer=self.completer,
            complete_while_typing=False,
            complete_in_thread=True,
            multiline=False,
            enable_history_search=True,
            style=STYLE,
            bottom_toolbar=self._get_toolbar,
            prompt_continuation=self._get_continuation,
        )

    def _get_toolbar(self):
        """Generate the bottom toolbar content"""
        parts = []

        # Mode indicator
        mode = MODES[self.mode_idx]
        mode_label = MODE_LABELS[mode]

        if mode == "auto":
            parts.append(('class:mode', f'  ⏵⏵ {mode_label}'))
        elif mode == "plan":
            parts.append(('class:mode', f'  ◇ {mode_label}'))
        else:
            parts.append(('', f'  ○ {mode_label}'))

        parts.append(('class:bottom-toolbar.text', ' (shift+Tab to cycle)'))

        # File changes if any
        if self.files_changed > 0:
            parts.append(('class:bottom-toolbar.text', ' · '))
            parts.append(('class:files', f'{self.files_changed} file{"s" if self.files_changed > 1 else ""}'))
            if self.lines_added > 0 or self.lines_removed > 0:
                parts.append(('class:bottom-toolbar.text', ' '))
                if self.lines_added > 0:
                    parts.append(('fg:ansigreen', f'+{self.lines_added}'))
                if self.lines_removed > 0:
                    if self.lines_added > 0:
                        parts.append(('class:bottom-toolbar.text', ' '))
                    parts.append(('fg:ansired', f'-{self.lines_removed}'))

        # Status message if any
        if self.status_message:
            parts.append(('class:bottom-toolbar.text', f' · {self.status_message}'))

        return parts

    def _get_continuation(self, width, line_number, is_soft_wrap):
        """Continuation prompt for multiline"""
        return '  '

    def _get_prompt(self):
        """Get the prompt with surrounding lines"""
        width = os.get_terminal_size().columns
        line = '─' * width
        return f'\n\033[90m{line}\033[0m\n\033[36m❯\033[0m '

    def set_status(self, message: str):
        """Set status message in toolbar"""
        self.status_message = message

    def set_file_changes(self, files: int, added: int = 0, removed: int = 0):
        """Set file change counts"""
        self.files_changed = files
        self.lines_added = added
        self.lines_removed = removed

    def clear_changes(self):
        """Clear file change counts"""
        self.files_changed = 0
        self.lines_added = 0
        self.lines_removed = 0
        self.status_message = ""

    @property
    def current_mode(self) -> str:
        """Get current mode"""
        return MODES[self.mode_idx]

    def _get_width(self) -> int:
        """Get terminal width safely"""
        try:
            return os.get_terminal_size().columns
        except OSError:
            return 80

    def get_input(self, prompt=None):
        try:
            return self.session.prompt([('class:prompt', '❯ ')])
        except EOFError:
            return None
        except KeyboardInterrupt:
            return INTERRUPTED

    async def get_input_async(self, prompt=None):
        try:
            return await self.session.prompt_async([('class:prompt', '❯ ')])
        except EOFError:
            return None
        except KeyboardInterrupt:
            return INTERRUPTED
