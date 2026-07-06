"""Base class for all Windows app automation plugins.

Each plugin (e.g. WeChat) subclasses AppTool and implements:
- name / manifest (metadata)
- initialize() / cleanup()  (lifecycle)
- get_tool_definitions()   (MCP tool registration metadata)

Every tool function MUST have proper Python type annotations – the
MCP server uses those to generate the JSON schema for each tool.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

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

    @abstractmethod
    def get_tool_definitions(self) -> ToolMap:
        """Return every MCP tool this plugin exposes.

        Format::

            {
                "tool_name": (callable, {
                    "description": "What the tool does",
                }),
            }

        Each *callable* should have typed parameters and a return type
        annotation.  The callable can be synchronous or asynchronous.
        """
        ...

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
