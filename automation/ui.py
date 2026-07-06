"""UI element operations for Windows automation.

Provides high-level wrappers around pywinauto for common UI interactions:
button clicks, text input, combobox selection, and element discovery.
"""

from __future__ import annotations

import time
from typing import Any

from base.debug import get_logger

logger = get_logger()

_HAS_PYWINAUTO = False
try:
    import pywinauto
    from pywinauto import timings
    from pywinauto.findwindows import ElementNotFoundError

    _HAS_PYWINAUTO = True
except ImportError:
    pywinauto = None  # type: ignore[assignment]
    ElementNotFoundError = RuntimeError  # placeholder


class UIOperations:
    """High-level operations over UI elements inside a window."""

    # ------------------------------------------------------------------
    # Button
    # ------------------------------------------------------------------

    @staticmethod
    def button_click(
        window: Any,
        control_id: int | str | None = None,
        title: str | None = None,
        auto_id: str | None = None,
        class_name: str | None = None,
        timeout: int = 5,
    ) -> bool:
        """Click a button matching one or more criteria.

        Args:
            window: pywinauto WindowSpecification.
            control_id: Numeric or string control ID.
            title: Button text / title.
            auto_id: AutomationId (recommended for modern UWP/WPF apps).
            class_name: Window class name.

        Returns:
            True if the click succeeded.
        """
        if not _HAS_PYWINAUTO:
            logger.error("pywinauto not available")
            return False

        try:
            ctrl = _resolve_control(window, control_id, title, auto_id, class_name)
            ctrl.wait("enabled", timeout=timeout)
            ctrl.click()
            logger.info(
                "Clicked button: %s",
                title or auto_id or control_id or class_name,
            )
            return True
        except Exception as exc:
            logger.error("Button click failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Text input
    # ------------------------------------------------------------------

    @staticmethod
    def text_set_text(
        window: Any,
        text: str = "",
        control_id: int | str | None = None,
        title: str | None = None,
        auto_id: str | None = None,
        clear_first: bool = True,
    ) -> bool:
        """Type text into an edit control.

        Args:
            window: pywinauto WindowSpecification.
            text: Text to enter.
            control_id / title / auto_id: Control identification.
            clear_first: Select all + delete before typing.

        Returns:
            True on success.
        """
        if not _HAS_PYWINAUTO:
            logger.error("pywinauto not available")
            return False

        try:
            ctrl = _resolve_control(window, control_id, title, auto_id)
            ctrl.wait("enabled", timeout=5)
            if clear_first:
                ctrl.select()
                ctrl.type_keys("^a{DELETE}")
            ctrl.type_keys(text, with_spaces=True)
            logger.info("Set text (%d chars)", len(text))
            return True
        except Exception as exc:
            logger.error("Set text failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Combo-box / list selection
    # ------------------------------------------------------------------

    @staticmethod
    def select_combo_item(
        window: Any,
        item_text: str,
        auto_id: str | None = None,
    ) -> bool:
        """Select an item in a combobox by visible text."""
        if not _HAS_PYWINAUTO:
            return False
        try:
            criteria: dict[str, Any] = {"control_type": "ComboBox"}
            if auto_id:
                criteria["auto_id"] = auto_id
            combo = window.child_window(**criteria)
            combo.select(item_text)
            logger.info("Selected combo item: %s", item_text)
            return True
        except Exception as exc:
            logger.error("Combo selection failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def wait_and_focus(window: Any, timeout: int = 10) -> bool:
        """Wait for a window to be ready and bring it to foreground."""
        if not _HAS_PYWINAUTO:
            return False
        try:
            window.wait("visible", timeout=timeout)
            window.set_focus()
            time.sleep(0.3)
            return True
        except Exception as exc:
            logger.warning("wait_and_focus failed: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_RESOLVERS = [
    ("control_id", lambda w, v: w[v]),
    ("title", lambda w, v: w.child_window(title=v)),
    ("auto_id", lambda w, v: w.child_window(auto_id=v)),
    ("class_name", lambda w, v: w.child_window(class_name=v)),
]


def _resolve_control(window, *criteria):
    """Try resolving a control by the first non-None criterion."""
    for name, value, resolver in zip(
        ("control_id", "title", "auto_id", "class_name"),
        criteria,
        [r[1] for r in _RESOLVERS],
    ):
        if value is not None:
            return resolver(window, value)
    # Fall back to focused / first child
    return window
