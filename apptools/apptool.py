"""Base class for all Windows app automation plugins.

Each plugin (e.g. WeChat) subclasses AppTool and implements:
- name / manifest (metadata)
- initialize() / cleanup()  (lifecycle)

Tool definitions are driven by manifest.json ``tools`` section.
Each tool entry must specify a ``method`` field that maps to the
Python method name on the plugin class.  ``description`` and
``params`` are also read from manifest — no need to hardcode them
in Python.

Subclasses may override ``get_tool_definitions()`` if manifest-driven
lookup is not sufficient.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for tool registration.
# {tool_name: (callable, metadata_dictionary)}
ToolMap = dict[str, tuple[Callable[..., Any], dict[str, Any]]]


class AppTool(ABC):
    """Abstract base class for a Windows app automation plugin.

    Subclass and fill the abstract members, then place the module in
    the ``apptools/<plugin_name>/`` directory.
    """

    def __init__(self) -> None:
        self.enabled: bool = True
        self._initialized: bool = False

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin identifier (e.g. 'weixin')."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name – can be overridden by manifest."""
        return self.name

    @property
    @abstractmethod
    def manifest(self) -> dict[str, Any]:
        """Return the parsed manifest.json content."""
        ...

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> bool:
        """Prepare the plugin (check deps, load config, etc.).

        Return False to signal that the plugin should be disabled.
        """
        self._initialized = True
        return True

    async def cleanup(self) -> None:
        """Release any resources held by the plugin."""
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> ToolMap:
        """Build MCP tool definitions from manifest.json ``tools`` section.

        Each entry in ``manifest["tools"]`` is keyed by the tool name,
        which must also be the Python method name on this class:

        .. code-block:: json

            {
              "my_tool": {
                "description": "What it does",
                "params": [{"name": "x", "type": "string", "description": "..."}]
              }
            }

        The base class resolves ``self.my_tool`` automatically.
        Subclasses may override for custom behaviour.
        """
        manifest = self.manifest
        tools_cfg: dict[str, Any] = manifest.get("tools", {})
        if not tools_cfg:
            return {}

        definitions: ToolMap = {}
        for tool_name, tool_cfg in tools_cfg.items():
            method = getattr(self, tool_name, None)
            if method is None or not callable(method):
                logger.error(
                    "Tool %r has no matching method on %s",
                    tool_name, type(self).__name__,
                )
                continue

            metadata: dict[str, Any] = {
                "description": tool_cfg.get("description", ""),
            }

            params_list = tool_cfg.get("params", [])
            if params_list:
                metadata["parameters"] = {
                    p["name"]: {
                        "type": p.get("type", "string"),
                        "description": p.get("description", ""),
                    }
                    for p in params_list
                }

            definitions[tool_name] = (method, metadata)

        return definitions

    # ------------------------------------------------------------------
    # Manifest helpers
    # ------------------------------------------------------------------

    def get_capabilities(self) -> list[str]:
        """Return the list of capability names from the manifest."""
        return list(self.get_tool_definitions().keys())

    def is_compatible(self) -> bool:
        """Return False if the current platform cannot run this plugin."""
        # Default: plugins are Windows-only
        import sys

        return sys.platform == "win32"
