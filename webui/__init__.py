"""pyWinBots Web UI – configuration management interface.

Provides a FastAPI-based web dashboard for managing plugins, viewing
capabilities, checking runtime status, and browsing logs.
"""

from webui.webui import create_app, run_webui

__all__ = ["create_app", "run_webui"]
