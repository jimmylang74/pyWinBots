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

        all_prompts = self.app_manager.collect_all_prompts()
        self._register_prompts(all_prompts)

        self._setup_done = True
        tool_lines = "\n".join(f"      - {name}" for name in all_tools.keys())
        prompt_lines = "\n".join(f"      - {name}" for name in all_prompts.keys())
        logger.info("[MCP-SERVER] Server ready – %d tools, %d prompts registered:\n"
                     "    tools:\n%s\n"
                     "    prompts:\n%s",
                     len(all_tools), len(all_prompts), tool_lines, prompt_lines)

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

                params_meta = metadata.get("parameters", {})
                if params_meta:
                    tool = self.mcp._tool_manager.get_tool(tool_name)
                    if tool is not None:
                        for pname, pinfo in params_meta.items():
                            prop = tool.parameters.get("properties", {}).get(pname)
                            if prop is not None:
                                prop["type"] = pinfo.get("type", prop.get("type", "string"))
                                prop["description"] = pinfo.get("description", prop.get("description", ""))

                registered += 1
            except Exception as exc:
                logger.error("[Plugin] Failed to register tool '%s': %s", tool_name, exc)
        logger.info("[Plugin] Registered %d tools from plugins", registered)

    # ------------------------------------------------------------------
    # Prompt registration
    # ------------------------------------------------------------------

    def _register_prompts(self, prompts: dict[str, tuple[str, str]]) -> None:
        """Register prompt definitions with the FastMCP server.

        Args:
            prompts: Mapping of ``{prompt_name: (content, description)}``.
        """
        from mcp.server.fastmcp.prompts.base import Prompt as FastMCPPrompt

        registered = 0
        for prompt_name, (content, description) in prompts.items():
            try:
                def _make_prompt_fn(text: str):  # noqa: ANN001, ANN202
                    def _fn() -> str:
                        return text
                    return _fn

                prompt = FastMCPPrompt.from_function(
                    fn=_make_prompt_fn(content),
                    name=prompt_name,
                    description=description,
                )

                self.mcp.add_prompt(prompt)
                registered += 1
                logger.info("[Plugin] Loaded prompt: %s (%d chars)", prompt_name, len(content))
            except Exception as exc:
                logger.error("[Plugin] Failed to register prompt '%s': %s", prompt_name, exc)

        logger.info("[Plugin] Registered %d prompts from plugins", registered)

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

        original_list_tools = mcp_server.request_handlers.get(types.ListToolsRequest)
        if original_list_tools is not None:
            async def debug_list_tools_handler(req):
                try:
                    result = await original_list_tools(req)
                    tools = result.root.tools
                    logger.info("[MCP] >>> Responding with %d tools: %s",
                                len(tools), ", ".join(t.name for t in tools))
                    return result
                except Exception as exc:
                    logger.error("[MCP] ListTools EXCEPTION: %s", exc, exc_info=True)
                    raise

            mcp_server.request_handlers[types.ListToolsRequest] = debug_list_tools_handler

        original_call_tool = mcp_server.request_handlers.get(types.CallToolRequest)
        if original_call_tool is not None:
            async def debug_call_tool_handler(req):
                tool_name = req.params.name
                try:
                    logger.info("[MCP] >>> CallTool: %s", tool_name)
                    result = await original_call_tool(req)
                    return result
                except Exception as exc:
                    logger.error("[MCP] CallTool '%s' EXCEPTION: %s", tool_name, exc, exc_info=True)
                    raise

            mcp_server.request_handlers[types.CallToolRequest] = debug_call_tool_handler

        original_list_prompts = mcp_server.request_handlers.get(types.ListPromptsRequest)
        if original_list_prompts is not None:
            async def debug_list_prompts_handler(req):
                try:
                    result = await original_list_prompts(req)
                    prompts = result.root.prompts
                    logger.info("[MCP] >>> Responding with %d prompts: %s",
                                len(prompts), ", ".join(p.name for p in prompts))
                    return result
                except Exception as exc:
                    logger.error("[MCP] ListPrompts EXCEPTION: %s", exc, exc_info=True)
                    raise

            mcp_server.request_handlers[types.ListPromptsRequest] = debug_list_prompts_handler
