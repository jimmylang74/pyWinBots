#!/usr/bin/env python3
"""MCP test client for pyWinBots.

Reads ``test.json`` and executes the configured tool calls against a
running pyWinBots MCP server.

Usage:
    python test.py                          # uses test.json
    python test.py --config my_tests.json
    python test.py --url http://localhost:8000/mcp
    python test.py --test launch_weixin     # run single test by ID
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is on path
_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

logger = None


# ---------------------------------------------------------------------------
# MCP Client using Streamable HTTP
# ---------------------------------------------------------------------------

async def call_tool(session, tool_name: str, arguments: dict[str, Any]) -> dict[str, object]:
    """Call an MCP tool with retry/logging."""
    logger.info("  Calling tool: %s(%s)", tool_name, arguments)
    try:
        result = await session.call_tool(tool_name, arguments=arguments)
        logger.info("  Result: %s", result)
        if result.isError:
            logger.error("  Tool returned error: %s", result.content)
            return {"success": False, "tool": tool_name, "error": str(result.content)}
        return {"success": True, "tool": tool_name, "result": str(result.content)}
    except Exception as exc:
        logger.error("  FAILED: %s", exc)
        return {"success": False, "tool": tool_name, "error": str(exc)}


async def run_tests(
    config_path_str: str,
    override_url: str | None = None,
    test_id: str | None = None,
) -> list[dict[str, object]]:
    """Run all tests from the JSON config against the MCP server."""
    # Load config
    config_path = Path(config_path_str)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        return []

    config = json.loads(config_path.read_text(encoding="utf-8"))
    url = override_url or config.get("mcp_server_url", "http://localhost:8000/mcp")
    tests = config.get("tests", [])

    if test_id:
        tests = [t for t in tests if t.get("id") == test_id]
        if not tests:
            logger.error("Test not found: %s", test_id)
            return []

    logger.info("=" * 60)
    logger.info("pyWinBots Test Client")
    logger.info("MCP Server URL: %s", url)
    logger.info("Tests: %d", len(tests))
    logger.info("=" * 60)

    results: list[dict[str, object]] = []

    # Connect to MCP server
    try:
        from mcp.client.streamable_http import streamable_http_client
        from mcp.client.session import ClientSession

        async with streamable_http_client(url=url) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # List tools
                tools_result = await session.list_tools()
                logger.info("\nAvailable tools on server (%d):", len(tools_result.tools))
                for i, t in enumerate(tools_result.tools, 1):
                    params = getattr(t, "inputSchema", {}).get("properties", {})
                    param_str = ", ".join(params.keys()) if params else "none"
                    logger.info("  %d. %s (%s) — %s", i, t.name, param_str, t.description)

                # Run tests
                logger.info("\n%s", "=" * 60)
                logger.info("Executing tests...")
                logger.info("%s\n", "=" * 60)

                for test in tests:
                    tid = test.get("id", "unknown")
                    desc = test.get("description", "")
                    tool = test.get("tool", "")
                    params = test.get("params", {})

                    logger.info("[%s] %s", tid, desc)
                    start = time.time()
                    result = await call_tool(session, tool, params)
                    elapsed = time.time() - start
                    result["id"] = tid
                    result["elapsed"] = round(elapsed, 2)
                    results.append(result)

                    # Brief pause between calls
                    await asyncio.sleep(0.5)

    except ImportError as exc:
        logger.error("MCP client libraries not available: %s", exc)
        logger.error("Install with: pip install mcp httpx")
        return results
    except Exception as exc:
        logger.error("Connection failed: %s", exc)
        logger.error("Make sure pyWinBots is running (python pywinbots.py)")
        return results

    # Summary
    logger.info("\n%s", "=" * 60)
    logger.info("Test Results Summary")
    logger.info("%s", "=" * 60)
    passed = sum(1 for r in results if r.get("success"))
    for r in results:
        status = "✅ PASS" if r.get("success") else "❌ FAIL"
        logger.info("  %s [%s] %s (%.1fs)", status, r["id"], r.get("tool", "?"), r.get("elapsed", 0))

    logger.info("\n%d / %d tests passed", passed, len(results))
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    config_path = Path("test.json")
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        test_ids = [t.get("id", "?") for t in config.get("tests", [])]
        test_hint = f"Available: {', '.join(test_ids)}" if test_ids else ""
    else:
        config = {}
        test_hint = ""

    parser = argparse.ArgumentParser(description="pyWinBots Test Client")
    parser.add_argument(
        "--config",
        default="test.json",
        help="Test configuration file (default: test.json)",
    )
    default_url = config.get("mcp_server_url", "http://localhost:8000/mcp")

    parser.add_argument(
        "--url",
        default=None,
        help=f"MCP server URL (overrides config file, default: {default_url})",
    )
    parser.add_argument(
        "--test",
        default=None,
        help=f"Run only the test with this ID. {test_hint}",
    )
    args = parser.parse_args()

    from base.debug import setup_logger

    global logger
    logger = setup_logger("pyWinBots-Test", level="DEBUG")

    results = asyncio.run(run_tests(args.config, args.url, test_id=args.test))

    # Exit code
    sys.exit(0 if all(r.get("success") for r in results) else 1)


if __name__ == "__main__":
    main()
