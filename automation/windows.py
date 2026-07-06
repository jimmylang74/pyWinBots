"""Window operations for Windows automation.

Provide means to find, inspect, and navigate the window tree of
running desktop applications using pywinauto (backend="uia").
"""

from __future__ import annotations

from typing import Any

from base.debug import get_logger

logger = get_logger()

_HAS_PYWINAUTO = False
try:
    import pywinauto
    from pywinauto import Desktop, Application, ElementNotFoundError, WindowSpecification
    from pywinauto.timings import TimeoutError

    _HAS_PYWINAUTO = True
except ImportError:
    pywinauto = None  # type: ignore[assignment]
    Desktop = object  # placeholder
    Application = object  # placeholder
    ElementNotFoundError = RuntimeError
    TimeoutError = RuntimeError


class WindowOperations:
    """Operations for discovering and inspecting windows and controls."""

    def __init__(self, backend: str = "uia") -> None:
        self.backend = backend
        self._apps: dict[str, Application] = {}

    # ------------------------------------------------------------------
    # Window discovery
    # ------------------------------------------------------------------

    def window_find(
        self,
        title: str | None = None,
        class_name: str | None = None,
        process_id: int | None = None,
        timeout: int = 10,
    ) -> Any | None:
        """Find a top-level window by title / class / PID.

        Returns a pywinauto WindowSpecification or None.
        """
        if not _HAS_PYWINAUTO:
            logger.error("pywinauto not available")
            return None
        try:
            desktop = Desktop(backend=self.backend)
            criteria: dict[str, Any] = {}
            if title:
                criteria["title"] = title
            if class_name:
                criteria["class_name"] = class_name
            if process_id:
                criteria["process_id"] = process_id

            window = desktop.window(**criteria)
            window.wait("exists", timeout=timeout)
            logger.info("Found window: %s", title or class_name or process_id)
            return window
        except TimeoutError:
            logger.warning("Window not found (timeout %ss): %s", timeout, title)
            return None
        except Exception as exc:
            logger.error("window_find failed: %s", exc)
            return None

    def window_find_all(
        self,
        title_re: str | None = None,
        class_name: str | None = None,
    ) -> list[Any]:
        """Find all windows matching criteria."""
        if not _HAS_PYWINAUTO:
            return []
        try:
            desktop = Desktop(backend=self.backend)
            criteria: dict[str, Any] = {}
            if title_re:
                criteria["title_re"] = title_re
            if class_name:
                criteria["class_name"] = class_name
            return desktop.windows(**criteria)
        except Exception as exc:
            logger.error("window_find_all failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Control discovery
    # ------------------------------------------------------------------

    def control_find(
        self,
        window: Any,
        control_type: str | None = None,
        title: str | None = None,
        auto_id: str | None = None,
        class_name: str | None = None,
        found_index: int | None = None,
    ) -> Any | None:
        """Find a control inside *window*."""
        if not _HAS_PYWINAUTO:
            return None
        try:
            criteria: dict[str, Any] = {}
            if control_type:
                criteria["control_type"] = control_type
            if title:
                criteria["title"] = title
            if auto_id:
                criteria["auto_id"] = auto_id
            if class_name:
                criteria["class_name"] = class_name

            if found_index is not None:
                return window.child_window(**criteria, found_index=found_index)
            return window.child_window(**criteria)
        except Exception as exc:
            logger.error("control_find failed: %s", exc)
            return None

    def control_exists(
        self,
        window: Any,
        title: str | None = None,
        auto_id: str | None = None,
        timeout: int = 3,
    ) -> bool:
        """Check if a control exists (with optional wait)."""
        if not _HAS_PYWINAUTO:
            return False
        try:
            ctrl = window.child_window(title=title, auto_id=auto_id)
            ctrl.wait("exists", timeout=timeout)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Tree dump (debugging)
    # ------------------------------------------------------------------

    def window_dump_tree(
        self,
        window: Any,
        depth: int = 3,
        filename: str | None = None,
    ) -> str:
        """Dump the UI Automation control tree of a window.

        Args:
            window: pywinauto WindowSpecification.
            depth: How many levels to descend.
            filename: If provided, write to file instead of returning.

        Returns:
            Pretty-printed tree as a string.
        """
        if not _HAS_PYWINAUTO or window is None:
            return "Window automation not available"
        try:
            tree = window.dump_tree(depth=depth)
            text = str(tree)
            if filename:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(text)
                logger.info("Tree dumped to %s", filename)
            return text
        except Exception as exc:
            logger.error("dump_tree failed: %s", exc)
            return f"Error: {exc}"

    # ------------------------------------------------------------------
    # App connection
    # ------------------------------------------------------------------

    def connect_to_app(
        self,
        title_re: str | None = None,
        process_id: int | None = None,
        name: str = "app",
    ) -> Any | None:
        """Connect to an already-running application.

        Returns an Application object.
        """
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
            self._apps[name] = app
            logger.info("Connected to app '%s'", name)
            return app
        except Exception as exc:
            logger.error("connect_to_app failed: %s", exc)
            return None

    def get_app(self, name: str) -> Any | None:
        """Return a previously connected/launched Application."""
        return self._apps.get(name)
