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

import inspect
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, get_args, get_origin, get_type_hints, Optional

logger = logging.getLogger(__name__)

_PYTHON_TO_JSON_SCHEMA_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

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

            sig = inspect.signature(method)
            func_params = [
                p for p in sig.parameters
                if p not in ("self", "cls", "kwargs", "args")
            ]

            params_list = tool_cfg.get("params", [])
            manifest_param_names = [p["name"] for p in params_list]

            missing_in_func = [
                n for n in manifest_param_names if n not in func_params
            ]
            missing_in_manifest = [
                n for n in func_params if n not in manifest_param_names
            ]

            if missing_in_func or missing_in_manifest:
                errors = []
                if missing_in_func:
                    errors.append(
                        f"params in manifest but not in function: {missing_in_func}"
                    )
                if missing_in_manifest:
                    errors.append(
                        f"params in function but not in manifest: {missing_in_manifest}"
                    )
                logger.error(
                    "Tool %r parameter mismatch: %s",
                    tool_name, "; ".join(errors),
                )
                continue

            type_errors = []
            try:
                all_hints = get_type_hints(method)
            except Exception:
                all_hints = {}
            hints = {k: v for k, v in all_hints.items() if k in func_params}
            for p in params_list:
                pname = p["name"]
                manifest_type = p.get("type", "string")
                annotation = hints.get(pname)
                if annotation is None:
                    continue
                actual = annotation
                if get_origin(actual) is Optional:
                    args = get_args(actual)
                    actual = args[0] if args else str
                json_type = _PYTHON_TO_JSON_SCHEMA_TYPE.get(actual)
                if json_type is not None and json_type != manifest_type:
                    type_errors.append(
                        f"{pname}: manifest={manifest_type!r}, function={json_type!r}"
                    )
            if type_errors:
                logger.error(
                    "Tool %r type mismatch: %s",
                    tool_name, "; ".join(type_errors),
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
