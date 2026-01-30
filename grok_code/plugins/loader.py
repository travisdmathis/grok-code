"""Plugin loader - parses plugins with markdown + YAML frontmatter"""

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Agent:
    """Agent definition from markdown file"""
    name: str
    description: str
    prompt: str
    tools: list[str] = field(default_factory=list)
    model: str = "default"
    color: str = "cyan"
    plugin: str = ""
    file_path: str = ""

    @property
    def full_name(self) -> str:
        """Full name including plugin prefix"""
        if self.plugin:
            return f"{self.plugin}:{self.name}"
        return self.name


@dataclass
class Command:
    """Command/skill definition from markdown file"""
    name: str
    description: str
    prompt: str
    argument_hint: str = ""
    plugin: str = ""
    file_path: str = ""

    @property
    def full_name(self) -> str:
        if self.plugin:
            return f"{self.plugin}:{self.name}"
        return self.name


@dataclass
class Skill:
    """Skill definition (auto-invoked commands)"""
    name: str
    description: str
    prompt: str
    triggers: list[str] = field(default_factory=list)
    plugin: str = ""
    file_path: str = ""


@dataclass
class Hook:
    """Hook definition"""
    name: str
    event: str  # PreToolUse, PostToolUse, SessionStart, Stop, UserPromptSubmit
    script: str
    plugin: str = ""
    file_path: str = ""


@dataclass
class Plugin:
    """A loaded plugin"""
    name: str
    version: str
    description: str
    path: Path
    agents: list[Agent] = field(default_factory=list)
    commands: list[Command] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content"""
    if not content.startswith("---"):
        return {}, content

    # Find the closing ---
    end_match = re.search(r'\n---\n', content[3:])
    if not end_match:
        return {}, content

    frontmatter_str = content[3:end_match.start() + 3]
    body = content[end_match.end() + 3 + 1:]

    # Simple YAML parsing (key: value)
    frontmatter = {}
    for line in frontmatter_str.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            # Strip quotes from values (YAML allows quoted strings)
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            # Only split into list for known list fields (tools, triggers)
            if key in ('tools', 'triggers') and ',' in value:
                value = [v.strip() for v in value.split(',')]
            frontmatter[key] = value

    return frontmatter, body.strip()


class PluginLoader:
    """Loads plugins from directories"""

    def __init__(self, plugin_dirs: list[Path] = None):
        self.plugin_dirs = plugin_dirs or []
        self.plugins: dict[str, Plugin] = {}

    def add_plugin_dir(self, path: Path) -> None:
        """Add a directory to search for plugins"""
        if path not in self.plugin_dirs:
            self.plugin_dirs.append(path)

    def discover_plugins(self) -> list[Path]:
        """Find all plugin directories"""
        found = []
        for base_dir in self.plugin_dirs:
            if not base_dir.exists():
                continue
            # Look for directories with .grok-plugin
            for item in base_dir.iterdir():
                if item.is_dir():
                    plugin_marker = item / ".grok-plugin" / "plugin.json"
                    grok_marker = item / ".grok-plugin" / "plugin.json"
                    if plugin_marker.exists() or grok_marker.exists():
                        found.append(item)
        return found

    def load_plugin(self, plugin_path: Path) -> Optional[Plugin]:
        """Load a single plugin from a directory"""
        # Find plugin.json
        plugin_json = plugin_path / ".grok-plugin" / "plugin.json"
        if not plugin_json.exists():
            plugin_json = plugin_path / ".grok-plugin" / "plugin.json"
        if not plugin_json.exists():
            return None

        try:
            with open(plugin_json) as f:
                meta = json.load(f)
        except Exception:
            return None

        plugin = Plugin(
            name=meta.get("name", plugin_path.name),
            version=meta.get("version", "1.0.0"),
            description=meta.get("description", ""),
            path=plugin_path,
        )

        # Load agents
        agents_dir = plugin_path / "agents"
        if agents_dir.exists():
            for agent_file in agents_dir.glob("*.md"):
                agent = self._load_agent(agent_file, plugin.name)
                if agent:
                    plugin.agents.append(agent)

        # Load commands
        commands_dir = plugin_path / "commands"
        if commands_dir.exists():
            for cmd_file in commands_dir.glob("*.md"):
                cmd = self._load_command(cmd_file, plugin.name)
                if cmd:
                    plugin.commands.append(cmd)

        # Load skills
        skills_dir = plugin_path / "skills"
        if skills_dir.exists():
            for skill_file in skills_dir.glob("*.md"):
                skill = self._load_skill(skill_file, plugin.name)
                if skill:
                    plugin.skills.append(skill)

        # Load hooks (Python scripts)
        hooks_dir = plugin_path / "hooks"
        if hooks_dir.exists():
            for hook_file in hooks_dir.glob("*.py"):
                hook = self._load_hook(hook_file, plugin.name)
                if hook:
                    plugin.hooks.append(hook)

        self.plugins[plugin.name] = plugin
        return plugin

    def load_all(self) -> list[Plugin]:
        """Load all discovered plugins and standalone agents"""
        plugins = []

        # Load full plugins (directories with .grok-plugin/plugin.json)
        for plugin_path in self.discover_plugins():
            plugin = self.load_plugin(plugin_path)
            if plugin:
                plugins.append(plugin)

        # Load standalone agent files from plugin directories
        standalone_agents = []
        for base_dir in self.plugin_dirs:
            if not base_dir.exists():
                continue
            # Look for .md files directly in the directory
            for item in base_dir.glob("*.md"):
                if item.is_file():
                    agent = self._load_agent(item, "local")
                    if agent:
                        standalone_agents.append(agent)

        # Create a synthetic plugin for standalone agents
        if standalone_agents:
            local_plugin = Plugin(
                name="local",
                version="1.0.0",
                description="Local project agents",
                path=Path.cwd() / ".grok",
                agents=standalone_agents,
            )
            plugins.append(local_plugin)
            self.plugins["local"] = local_plugin

        return plugins

    def _load_agent(self, file_path: Path, plugin_name: str) -> Optional[Agent]:
        """Load an agent from a markdown file"""
        try:
            content = file_path.read_text()
            frontmatter, body = parse_frontmatter(content)

            name = frontmatter.get("name", file_path.stem)
            tools = frontmatter.get("tools", [])
            if isinstance(tools, str):
                tools = [t.strip() for t in tools.split(",")]

            return Agent(
                name=name,
                description=frontmatter.get("description", ""),
                prompt=body,
                tools=tools,
                model=frontmatter.get("model", "default"),
                color=frontmatter.get("color", "cyan"),
                plugin=plugin_name,
                file_path=str(file_path),
            )
        except Exception:
            return None

    def _load_command(self, file_path: Path, plugin_name: str) -> Optional[Command]:
        """Load a command from a markdown file"""
        try:
            content = file_path.read_text()
            frontmatter, body = parse_frontmatter(content)

            return Command(
                name=file_path.stem,
                description=frontmatter.get("description", ""),
                prompt=body,
                argument_hint=frontmatter.get("argument-hint", ""),
                plugin=plugin_name,
                file_path=str(file_path),
            )
        except Exception:
            return None

    def _load_skill(self, file_path: Path, plugin_name: str) -> Optional[Skill]:
        """Load a skill from a markdown file"""
        try:
            content = file_path.read_text()
            frontmatter, body = parse_frontmatter(content)

            triggers = frontmatter.get("triggers", [])
            if isinstance(triggers, str):
                triggers = [t.strip() for t in triggers.split(",")]

            return Skill(
                name=file_path.stem,
                description=frontmatter.get("description", ""),
                prompt=body,
                triggers=triggers,
                plugin=plugin_name,
                file_path=str(file_path),
            )
        except Exception:
            return None

    def _load_hook(self, file_path: Path, plugin_name: str) -> Optional[Hook]:
        """Load a hook from a Python file"""
        try:
            # Determine event from filename
            stem = file_path.stem.lower()
            event_map = {
                "pretooluse": "PreToolUse",
                "posttooluse": "PostToolUse",
                "sessionstart": "SessionStart",
                "stop": "Stop",
                "userpromptsubmit": "UserPromptSubmit",
            }
            event = event_map.get(stem, stem)

            return Hook(
                name=file_path.stem,
                event=event,
                script=str(file_path),
                plugin=plugin_name,
                file_path=str(file_path),
            )
        except Exception:
            return None
