#!/usr/bin/env python3
"""pyWinBots - Windows Compute Use Runtime for AI Agents.

A Streamable HTTP MCP server that provides Windows application
automation capabilities through a plugin-based architecture.

The web configuration dashboard is automatically started alongside
the MCP server on port 6565 (configurable).

Usage:
    python pywinbots.py                          # MCP :8000, Web :6565
    python pywinbots.py --port 9000               # custom MCP port
    python pywinbots.py --web-port 9001           # custom web UI port
    python pywinbots.py --no-web                  # disable web UI
    python pywinbots.py --host 127.0.0.1          # localhost only
    python pywinbots.py --log-level DEBUG         # verbose logging
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_sys_path() -> None:
    """Ensure the project root is on sys.path for reliable imports."""
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="pyWinBots - Windows Compute Use Runtime for AI Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python pywinbots.py\n"
            "  python pywinbots.py --port 9000\n"
            "  python pywinbots.py --web-port 9001 --no-web\n"
            "  python pywinbots.py --host 127.0.0.1 --log-level DEBUG\n"
        ),
    )

    # MCP server
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="MCP server bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="MCP server port (default: 8000)",
    )

    # Web UI
    parser.add_argument(
        "--web-host",
        type=str,
        default=None,
        help="Web UI bind address (default: same as --host)",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=6565,
        help="Web UI port (default: 6565)",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        default=False,
        help="Disable the web configuration dashboard",
    )

    # Logging
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (default: ~/.pywinbots/logs/)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


def main() -> None:
    _ensure_sys_path()

    args = parse_args()

    # Setup logging
    from base.debug import setup_logger

    logger = setup_logger(
        name="pyWinBots",
        level=args.log_level,
        log_file=args.log_file,
    )

    logger.info("=" * 50)
    logger.info("pyWinBots starting ...")
    logger.info("MCP server:     http://%s:%s/mcp", args.host, args.port)
    logger.info("Log level:      %s", args.log_level)

    # Warn if not on Windows
    if sys.platform != "win32":
        logger.warning(
            "Running on %s – Windows automation features (pywinauto) "
            "will not work. The MCP server and plugin system are "
            "functional for development/testing.",
            sys.platform,
        )

    from apptools.appmgt import AppManager

    app_manager = AppManager()
    from mcp_server.server import PyWinBotsServer

    mcp_server = PyWinBotsServer(app_manager=app_manager)
    mcp_server.setup()

    if not args.no_web:
        web_host = args.web_host or args.host
        logger.info("Web dashboard:  http://%s:%s", web_host, args.web_port)

        import threading

        from webui.webui import run_webui

        web_thread = threading.Thread(
            target=run_webui,
            kwargs={
                "host": web_host,
                "port": args.web_port,
                "app_manager": app_manager,
            },
            daemon=True,
            name="pywinbots-webui",
        )
        web_thread.start()
    else:
        logger.info("Web dashboard:  disabled (--no-web)")

    logger.info("=" * 50)
    mcp_server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
