"""Plugin management – scan, load, enable/disable app plugins.

The AppManager discovers plugins by scanning
``apptools/<plugin_name>/manifest.json``, then dynamically imports
and instantiates each plugin's main class.
"""

from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path
from typing import Any

from apptools.apptool import AppTool
from base.debug import get_logger

logger = get_logger()


class AppManager:
    """Manages the lifecycle of all application plugins."""

    def __init__(self, plugin_dir: str | Path | None = None) -> None:
        self._plugin_root = Path(plugin_dir) if plugin_dir else Path(__file__).parent
        self._plugins: dict[str, AppTool] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def scan_plugins(self) -> list[dict[str, Any]]:
        """Walk the plugin directory and return metadata for every candidate.

        Returns a list of dicts::

            [{"name": str, "manifest": dict, "path": Path}, ...]
        """
        results: list[dict[str, Any]] = []
        if not self._plugin_root.is_dir():
            logger.warning("Plugin directory not found: %s", self._plugin_root)
            return results

        for entry in sorted(self._plugin_root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_") or entry.name.startswith("."):
                continue

            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                logger.debug("Skipping %s (no manifest.json)", entry.name)
                continue

            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                results.append(
                    {
                        "name": entry.name,
                        "manifest": manifest,
                        "path": entry,
                    }
                )
                logger.debug("Discovered plugin: %s", entry.name)
            except Exception as exc:
                logger.error("Failed to load manifest for %s: %s", entry.name, exc)

        return results

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_plugin(self, plugin_name: str) -> AppTool | None:
        """Dynamically import and instantiate a specific plugin.

        The plugin module must be at ``apptools.<plugin_name>.<plugin_name>``
        and contain a concrete (non-abstract) subclass of AppTool.
        """
        module_name = f"apptools.{plugin_name}.{plugin_name}"

        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            logger.error("Cannot import plugin module %s: %s", module_name, exc)
            return None

        # Find the AppTool subclass in the module
        instance: AppTool | None = None
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, AppTool) and not inspect.isabstract(obj) and obj is not AppTool:
                try:
                    instance = obj()
                    break
                except Exception as exc:
                    logger.error("Cannot instantiate %s: %s", _name, exc)
                    return None

        if instance is None:
            logger.error(
                "No concrete AppTool subclass found in %s", module_name
            )
            return None

        self._plugins[plugin_name] = instance
        logger.info("Loaded plugin: %s v%s", plugin_name, instance.manifest.get("version", "?"))
        return instance

    def load_all_plugins(self) -> list[AppTool]:
        """Discover and load every plugin found in the plugin directory."""
        loaded: list[AppTool] = []
        for info in self.scan_plugins():
            instance = self.load_plugin(info["name"])
            if instance is not None:
                loaded.append(instance)
        logger.info("Loaded %d / %d plugins", len(loaded), len(self.scan_plugins()))
        return loaded

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable_plugin(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin.enabled = True
        logger.info("Plugin enabled: %s", name)
        return True

    def disable_plugin(self, name: str) -> bool:
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        plugin.enabled = False
        logger.info("Plugin disabled: %s", name)
        return True

    def set_plugin_enabled(self, name: str, enabled: bool) -> bool:
        return self.enable_plugin(name) if enabled else self.disable_plugin(name)

    # ------------------------------------------------------------------
    # Unload
    # ------------------------------------------------------------------

    def unload_plugin(self, name: str) -> bool:
        import anyio

        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return False
        anyio.run(plugin.cleanup)
        logger.info("Unloaded plugin: %s", name)
        return True

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_plugin(self, name: str) -> AppTool | None:
        return self._plugins.get(name)

    def get_all_plugins(self) -> list[AppTool]:
        return list(self._plugins.values())

    def get_enabled_plugins(self) -> list[AppTool]:
        return [p for p in self._plugins.values() if p.enabled]

    def collect_all_tools(self) -> dict[str, tuple]:
        """Return a flat dict of {tool_name: (fn, metadata)} for every
        enabled plugin."""
        all_tools: dict[str, tuple] = {}
        for name, plugin in self._plugins.items():
            if not plugin.enabled:
                continue
            try:
                tools = plugin.get_tool_definitions()
                all_tools.update(tools)
                logger.debug("  %s: %d tools", name, len(tools))
            except Exception as exc:
                logger.error("collect_tools failed for %s: %s", name, exc)
        return all_tools

    def get_plugin_info(self, name: str) -> dict[str, Any] | None:
        """Return a summary dict for a single plugin."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return None
        return {
            "name": plugin.name,
            "display_name": plugin.display_name,
            "enabled": plugin.enabled,
            "initialized": plugin.is_initialized,
            "manifest": getattr(plugin, "manifest", {}),
            "capabilities": plugin.get_capabilities(),
        }

    def list_plugins_summary(self) -> list[dict[str, Any]]:
        """Return a summary list of all loaded plugins."""
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "enabled": p.enabled,
                "capabilities": p.get_capabilities(),
            }
            for p in self._plugins.values()
        ]
