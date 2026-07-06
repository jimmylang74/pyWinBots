"""Application lifecycle operations for Windows automation.

Provides launch, connect, close, and status helpers for Windows
executables, built on pywinauto.
"""

from __future__ import annotations

from typing import Any

from base.debug import get_logger

logger = get_logger()

_HAS_PYWINAUTO = False
try:
    import pywinauto
    from pywinauto import Application, ElementNotFoundError
    from pywinauto.timings import TimeoutError

    _HAS_PYWINAUTO = True
except ImportError:
    pywinauto = None  # type: ignore[assignment]
    Application = object  # placeholder
    ElementNotFoundError = RuntimeError
    TimeoutError = RuntimeError


class AppOperations:
    """Manage the lifecycle of Windows applications."""

    def __init__(self, backend: str = "uia") -> None:
        self.backend = backend
        self._apps: dict[str, Application] = {}

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def app_launch(
        self,
        app_path: str,
        app_name: str | None = None,
        timeout: int = 30,
        args: str = "",
    ) -> Any | None:
        """Launch a Windows executable.

        Args:
            app_path: Full path to the .exe.
            app_name: Logical name used to retrieve the app later.
            timeout: Seconds to wait for the main window.
            args: Optional command-line arguments.

        Returns:
            pywinauto Application instance, or None on failure.
        """
        if not _HAS_PYWINAUTO:
            logger.error("pywinauto not available – cannot launch app")
            return None

        try:
            app = Application(backend=self.backend)
            cmd = f'"{app_path}" {args}'.strip()
            app.start(cmd, timeout=timeout)
            name = app_name or _basename(app_path)
            self._apps[name] = app
            logger.info("Launched: %s (pid=%s)", name, app.process)
            return app
        except Exception as exc:
            logger.error("Failed to launch %s: %s", app_path, exc)
            return None

    # ------------------------------------------------------------------
    # Connect to running
    # ------------------------------------------------------------------

    def app_connect(
        self,
        title_re: str | None = None,
        process_id: int | None = None,
        app_name: str | None = None,
    ) -> Any | None:
        """Connect to a process that is already running."""
        if not _HAS_PYWINAUTO:
            return None
        try:
            app = Application(backend=self.backend)
            if process_id is not None:
                app.connect(process=process_id)
            elif title_re:
                app.connect(title_re=title_re)
            else:
                return None
            name = app_name or title_re or str(process_id or "")
            self._apps[name] = app
            logger.info("Connected to %s (pid=%s)", name, app.process)
            return app
        except Exception as exc:
            logger.error("app_connect failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def app_close(
        self,
        app_name: str | None = None,
        app: Any | None = None,
        timeout: int = 10,
    ) -> bool:
        """Terminate an application.

        Args:
            app_name: Logical name used during launch/connect.
            app: Direct Application reference (takes precedence).
            timeout: Seconds to wait for process exit.
        """
        if not _HAS_PYWINAUTO:
            return False
        try:
            target = app or self._apps.get(app_name) if app_name else None
            if target is None:
                logger.warning("No app to close (name=%s)", app_name)
                return False

            target.kill(timeout=timeout)
            if app_name and app_name in self._apps:
                del self._apps[app_name]
            logger.info("Closed: %s", app_name or "unknown")
            return True
        except Exception as exc:
            logger.error("app_close failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def app_is_running(self, app_name: str) -> bool:
        """Check whether a tracked application is still alive."""
        app = self._apps.get(app_name)
        if app is None:
            return False
        try:
            return app.is_process_running()
        except Exception:
            return False

    def get_app(self, app_name: str) -> Any | None:
        """Return a previously tracked Application instance."""
        return self._apps.get(app_name)

    def list_apps(self) -> dict[str, dict[str, Any]]:
        """Return info on all tracked applications."""
        info: dict[str, dict[str, Any]] = {}
        for name, app in self._apps.items():
            try:
                info[name] = {
                    "pid": app.process,
                    "running": app.is_process_running(),
                }
            except Exception:
                info[name] = {"pid": -1, "running": False}
        return info


def _basename(path: str) -> str:
    """Return the filename without directory or extension."""
    import os

    return os.path.splitext(os.path.basename(path))[0]
