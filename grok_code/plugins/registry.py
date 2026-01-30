"""Plugin registry - central access to all plugins, agents, commands, skills"""

from pathlib import Path
from typing import Optional

from .loader import PluginLoader, Plugin, Agent, Command, Skill, Hook


class PluginRegistry:
    """Central registry for all plugins and their components"""

    _instance: Optional["PluginRegistry"] = None

    def __init__(self):
        self.loader = PluginLoader()
        self._plugins: dict[str, Plugin] = {}
        self._agents: dict[str, Agent] = {}
        self._commands: dict[str, Command] = {}
        self._skills: dict[str, Skill] = {}
        self._hooks: dict[str, list[Hook]] = {}

    @classmethod
    def get_instance(cls) -> "PluginRegistry":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_plugin_dir(self, path: Path) -> None:
        """Add a directory to search for plugins"""
        self.loader.add_plugin_dir(path)

    def load_plugins(self) -> None:
        """Load all plugins from registered directories"""
        plugins = self.loader.load_all()
        for plugin in plugins:
            self._register_plugin(plugin)

    def _register_plugin(self, plugin: Plugin) -> None:
        """Register a plugin and all its components"""
        self._plugins[plugin.name] = plugin

        # Register agents
        for agent in plugin.agents:
            self._agents[agent.full_name] = agent
            # Also register without prefix for convenience
            if agent.name not in self._agents:
                self._agents[agent.name] = agent

        # Register commands
        for cmd in plugin.commands:
            self._commands[cmd.full_name] = cmd
            if cmd.name not in self._commands:
                self._commands[cmd.name] = cmd

        # Register skills
        for skill in plugin.skills:
            key = f"{plugin.name}:{skill.name}"
            self._skills[key] = skill
            if skill.name not in self._skills:
                self._skills[skill.name] = skill

        # Register hooks by event type
        for hook in plugin.hooks:
            if hook.event not in self._hooks:
                self._hooks[hook.event] = []
            self._hooks[hook.event].append(hook)

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name"""
        return self._plugins.get(name)

    def get_agent(self, name: str) -> Optional[Agent]:
        """Get an agent by name (with or without plugin prefix)"""
        return self._agents.get(name)

    def get_command(self, name: str) -> Optional[Command]:
        """Get a command by name"""
        return self._commands.get(name)

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name"""
        return self._skills.get(name)

    def get_hooks(self, event: str) -> list[Hook]:
        """Get all hooks for an event type"""
        return self._hooks.get(event, [])

    def list_plugins(self) -> list[Plugin]:
        """List all loaded plugins"""
        return list(self._plugins.values())

    def list_agents(self) -> list[Agent]:
        """List all available agents"""
        # Return unique agents (by full_name to avoid duplicates)
        seen = set()
        agents = []
        for agent in self._agents.values():
            if agent.full_name not in seen:
                seen.add(agent.full_name)
                agents.append(agent)
        return agents

    def list_commands(self) -> list[Command]:
        """List all available commands"""
        seen = set()
        commands = []
        for cmd in self._commands.values():
            if cmd.full_name not in seen:
                seen.add(cmd.full_name)
                commands.append(cmd)
        return commands

    def list_skills(self) -> list[Skill]:
        """List all available skills"""
        seen = set()
        skills = []
        for skill in self._skills.values():
            key = f"{skill.plugin}:{skill.name}"
            if key not in seen:
                seen.add(key)
                skills.append(skill)
        return skills

    def reload(self) -> None:
        """Clear and reload all plugins"""
        self._plugins.clear()
        self._agents.clear()
        self._commands.clear()
        self._skills.clear()
        self._hooks.clear()
        self.load_plugins()


def setup_default_plugin_dirs() -> PluginRegistry:
    """Set up plugin registry with default directories"""
    registry = PluginRegistry.get_instance()

    # Add default plugin directories
    # 1. Built-in plugins (shipped with grokCode)
    grok_code_dir = Path(__file__).parent.parent.parent
    builtin_plugins = grok_code_dir / "plugins"
    if builtin_plugins.exists():
        registry.add_plugin_dir(builtin_plugins)

    # 2. User plugins (~/.grokcode/plugins)
    user_plugins = Path.home() / ".grokcode" / "plugins"
    if user_plugins.exists():
        registry.add_plugin_dir(user_plugins)

    # 3. Project plugins (.grok/plugins in current directory)
    project_plugins = Path.cwd() / ".grok" / "plugins"
    if project_plugins.exists():
        registry.add_plugin_dir(project_plugins)

    # 4. Project agents (.grok/agents - standalone agent files)
    project_agents = Path.cwd() / ".grok" / "agents"
    if project_agents.exists():
        registry.add_plugin_dir(project_agents)

    # Load all plugins
    registry.load_plugins()

    return registry
