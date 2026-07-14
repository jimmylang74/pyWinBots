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
        self.mcp = FastMCP(
            "pyWinBots",
            host="0.0.0.0",
            json_response=True,
        )
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

        plugins = self.app_manager.load_all_plugins()

        for plugin in plugins:
            if plugin.enabled:
                try:
                    asyncio.run(plugin.initialize())
                except Exception as exc:
                    logger.error("Failed to init plugin %s: %s", plugin.name, exc)
                    plugin.enabled = False

        all_tools = self.app_manager.collect_all_tools()
        self._register_tools(all_tools)

        self._setup_done = True
        tool_names = ", ".join(all_tools.keys())
        logger.info("MCP server ready – %d tools registered: %s", len(all_tools), tool_names)

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

        self._patch_mcp_for_debug()

        app = self.mcp.streamable_http_app()

        import uvicorn

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            reload=False,
        )

    def _patch_mcp_for_debug(self) -> None:
        """Patch MCP server to log client requests and responses."""
        mcp_server = self.mcp._mcp_server

        if mcp_server.request_handlers is None:
            return

        from mcp import types

        original_handler = mcp_server.request_handlers.get(types.ListToolsRequest)
        if original_handler is None:
            return

        async def debug_list_tools_handler(req):
            try:
                result = await original_handler(req)
                tools = result.root.tools
                logger.info("[MCP] >>> Responding with %d tools: %s",
                            len(tools), ", ".join(t.name for t in tools))
                return result
            except Exception as exc:
                logger.error("[MCP] ListTools EXCEPTION: %s", exc, exc_info=True)
                raise

        mcp_server.request_handlers[types.ListToolsRequest] = debug_list_tools_handler
