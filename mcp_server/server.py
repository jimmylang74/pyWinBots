"""MCP Server with Streamable HTTP transport for pyWinBots.

Dynamically registers automation tools from all enabled plugins and
exposes them via the MCP protocol over HTTP.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from apptools.appmgt import AppManager
from base.debug import get_logger

logger = get_logger()


class PyWinBotsServer:
    """MCP server that aggregates tools from all AppTool plugins.

    Usage::

        server = PyWinBotsServer()
        server.setup()          # discover + load plugins, register tools
        server.run(host="0.0.0.0", port=8000)
    """

    def __init__(self, app_manager: AppManager | None = None) -> None:
        self.mcp = FastMCP("pyWinBots")
        self.app_manager = app_manager or AppManager()
        self._setup_done = False

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Discover, load, and register all plugin tools with the MCP server."""
        if self._setup_done:
            logger.warning("setup() already called – skipping")
            return

        logger.info("Setting up pyWinBots MCP server ...")

        # Load plugins
        plugins = self.app_manager.load_all_plugins()
        logger.info("Loaded %d plugins", len(plugins))

        # Initialize each enabled plugin
        for plugin in plugins:
            if plugin.enabled:
                try:
                    asyncio.run(plugin.initialize())
                except Exception as exc:
                    logger.error("Failed to init plugin %s: %s", plugin.name, exc)
                    plugin.enabled = False

        # Register tools from all enabled plugins
        all_tools = self.app_manager.collect_all_tools()
        self._register_tools(all_tools)

        # Register built-in tools (server info, plugin listing, etc.)
        self._register_builtin_tools()

        self._setup_done = True
        logger.info(
            "pyWinBots server ready – %d tools available",
            len(all_tools) + 5,  # approximate count including builtins
        )

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self, tools: dict[str, tuple[Any, ...]]) -> None:
        """Register externally-defined tool functions with the FastMCP server.

        Args:
            tools: Mapping of ``{tool_name: (callable, metadata_dict)}``.
        """
        registered = 0
        for tool_name, (fn, metadata) in tools.items():
            try:
                desc = metadata.get("description", "")
                self.mcp.add_tool(fn, name=tool_name, description=desc)
                registered += 1
            except Exception as exc:
                logger.error("Failed to register tool '%s': %s", tool_name, exc)
        logger.info("Registered %d tools from plugins", registered)

    def _register_builtin_tools(self) -> None:
        """Register pyWinBots built-in tools (info, plugin mgmt, etc.)."""

        @self.mcp.tool(
            name="pywinbots_list_plugins",
            description="列出所有已加载的插件及其能力和启用状态",
        )
        def list_plugins() -> str:
            plugins = self.app_manager.list_plugins_summary()
            lines = ["已加载的插件:"]
            for p in plugins:
                status = "✅ 启用" if p["enabled"] else "⛔ 禁用"
                lines.append(
                    f"  - {p['display_name']} ({p['name']}) {status}"
                )
                for cap in p["capabilities"]:
                    lines.append(f"      🔧 {cap}")
            return "\n".join(lines) if lines else "未加载任何插件"

        @self.mcp.tool(
            name="pywinbots_get_plugin_info",
            description="获取指定插件的详细信息，包括清单和能力",
        )
        def get_plugin_info(plugin_name: str) -> str:
            info = self.app_manager.get_plugin_info(plugin_name)
            if info is None:
                return f"插件 '{plugin_name}' 未找到"
            import json

            return json.dumps(info, ensure_ascii=False, indent=2)

        @self.mcp.tool(
            name="pywinbots_enable_plugin",
            description="启用一个已加载的插件",
        )
        def enable_plugin(plugin_name: str) -> str:
            ok = self.app_manager.enable_plugin(plugin_name)
            # Re-register tools (simple approach: re-setup)
            if ok:
                self._setup_done = False
                self.setup()
                return f"插件 '{plugin_name}' 已启用"
            return f"无法启用插件 '{plugin_name}'"

        @self.mcp.tool(
            name="pywinbots_disable_plugin",
            description="禁用一个已加载的插件",
        )
        def disable_plugin(plugin_name: str) -> str:
            ok = self.app_manager.disable_plugin(plugin_name)
            if ok:
                # Regenerate tools without this plugin
                self.mcp._tool_manager._tools.clear()
                self._setup_done = False
                self.setup()
                return f"插件 '{plugin_name}' 已禁用"
            return f"无法禁用插件 '{plugin_name}'"

        @self.mcp.tool(
            name="pywinbots_server_info",
            description="获取 pyWinBots 服务器的版本和状态信息",
        )
        def server_info() -> str:
            plugins = self.app_manager.get_all_plugins()
            lines = [
                "pyWinBots MCP Server",
                f"  状态: 运行中",
                f"  插件数: {len(plugins)}",
                f"  启用插件: {sum(1 for p in plugins if p.enabled)}",
            ]
            return "\n".join(lines)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """Start the MCP server with Streamable HTTP transport.

        Args:
            host: Bind address.
            port: TCP port.
        """
        if not self._setup_done:
            self.setup()

        logger.info("Starting Streamable HTTP MCP server on %s:%s", host, port)

        # FastMCP.run() doesn't accept host/port directly for streamable-http,
        # so we get the underlying ASGI app and run it with uvicorn.
        app = self.mcp.streamable_http_app()

        import uvicorn

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            reload=False,
        )
