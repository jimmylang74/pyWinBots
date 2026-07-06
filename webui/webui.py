"""FastAPI configuration management UI for pyWinBots.

Provides web-based plugin management:
- Browse installed plugins and their capabilities
- Enable / disable plugins
- View runtime status and logs

Run standalone:
    python -m webui.webui [--host ...] [--port ...]

Or programmatically:
    app = create_app(server)
    uvicorn.run(app, host="0.0.0.0", port=8080)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from apptools.appmgt import AppManager
from base.debug import get_logger

logger = get_logger()

_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
_static_root = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(app_manager: AppManager | None = None) -> FastAPI:
    """Create the FastAPI web UI application.

    Args:
        app_manager: Shared AppManager instance. Creates a new one if None.
    """
    mgr = app_manager or AppManager()

    # Ensure plugins are loaded
    if not mgr.get_all_plugins():
        mgr.load_all_plugins()
        for p in mgr.get_all_plugins():
            import anyio

            anyio.run(p.initialize)

    app = FastAPI(
        title="pyWinBots Web UI",
        version="1.0.0",
        description="Configuration management dashboard for pyWinBots",
    )

    # Serve static JS/CSS files
    if _static_root.is_dir():
        app.mount("/static", StaticFiles(directory=str(_static_root)), name="static")

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request):
        plugins = mgr.list_plugins_summary()
        return _templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "plugins": plugins,
                "plugin_count": len(plugins),
                "app_title": "pyWinBots",
            },
        )

    @app.get("/api/plugins", response_class=JSONResponse)
    async def api_list_plugins():
        return {"plugins": mgr.list_plugins_summary()}

    @app.get("/api/plugins/{name}", response_class=JSONResponse)
    async def api_plugin_detail(name: str):
        info = mgr.get_plugin_info(name)
        if info is None:
            return JSONResponse({"error": "Plugin not found"}, status_code=404)
        return info

    @app.post("/api/plugins/{name}/toggle", response_class=JSONResponse)
    async def api_toggle_plugin(name: str, enabled: bool = Form(True)):
        ok = mgr.set_plugin_enabled(name, enabled)
        if not ok:
            return JSONResponse(
                {"error": f"Plugin '{name}' not found"}, status_code=404
            )
        logger.info("Web UI toggled plugin %s -> %s", name, enabled)
        return {"success": True, "name": name, "enabled": enabled}

    @app.get("/api/status", response_class=JSONResponse)
    async def api_status():
        plugins = mgr.get_all_plugins()
        return {
            "server": "pyWinBots",
            "plugin_count": len(plugins),
            "enabled_count": sum(1 for p in plugins if p.enabled),
            "plugins": [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "initialized": p.is_initialized,
                    "capabilities": p.get_capabilities(),
                    "manifest": getattr(p, "manifest", {}),
                }
                for p in plugins
            ],
        }

    @app.get("/api/logs", response_class=JSONResponse)
    async def api_logs(lines: int = 50):
        logs = _read_recent_logs(lines)
        return {"logs": logs}

    @app.get("/api/plugins/{name}/config", response_class=JSONResponse)
    async def api_get_plugin_config(name: str):
        plugin_dir = Path(__file__).parent.parent / "apptools" / name
        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.exists():
            return JSONResponse({"error": "manifest not found"}, status_code=404)
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return data
        except Exception as exc:
            return JSONResponse({"error": f"Failed to read config: {exc}"}, status_code=500)

    @app.post("/api/plugins/{name}/config", response_class=JSONResponse)
    async def api_save_plugin_config(name: str, request: Request):
        plugin_dir = Path(__file__).parent.parent / "apptools" / name
        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.exists():
            return JSONResponse({"error": "manifest not found"}, status_code=404)
        try:
            body = await request.json()
            manifest_path.write_text(
                json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {"success": True, "name": name}
        except Exception as exc:
            return JSONResponse({"error": f"Failed to save config: {exc}"}, status_code=500)

    @app.get("/logs", response_class=HTMLResponse, include_in_schema=False)
    async def logs_page(request: Request, lines: int = 100):
        logs = _read_recent_logs(lines)
        return _templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "request": request,
                "tab": "logs",
                "logs": logs,
                "app_title": "pyWinBots - Logs",
            },
        )

    return app


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _read_recent_logs(n: int = 50) -> list[str]:
    """Read the last *n* lines from the current log file."""
    from base.debug import _get_default_log_dir

    log_dir = _get_default_log_dir()
    try:
        log_files = sorted(log_dir.glob("pywinbots_*.log"), reverse=True)
        if not log_files:
            return ["(No log files found)"]
        latest = log_files[0]
        text = latest.read_text(encoding="utf-8")
        lines = text.strip().splitlines()
        return lines[-n:]
    except Exception as exc:
        return [f"(Error reading logs: {exc})"]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_webui(
    host: str = "0.0.0.0",
    port: int = 8080,
    app_manager: AppManager | None = None,
) -> None:
    """Run the web UI.

    Args:
        host: Bind address.
        port: Listen port.
        app_manager: Optional shared AppManager. If omitted, creates a fresh one.
    """
    import uvicorn

    logger.info("Starting Web UI on http://%s:%s", host, port)
    app = create_app(app_manager)
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    parser = argparse.ArgumentParser(description="pyWinBots Web UI")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8080, help="Port")
    args = parser.parse_args()
    run_webui(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
