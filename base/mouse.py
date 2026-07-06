"""Mouse operations for pyWinBots.

Provides typed mouse automation wrappers on top of pyautogui.
"""

from base.debug import get_logger

logger = get_logger()

_HAS_PYAUTOGUI = False
try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _HAS_PYAUTOGUI = True
except ImportError:
    pyautogui = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def click(x: int | None = None, y: int | None = None, button: str = "left") -> None:
    """Perform a mouse click.

    Args:
        x, y: Screen coordinates. Current position when omitted.
        button: 'left', 'right', or 'middle'.
    """
    if not _HAS_PYAUTOGUI:
        logger.warning("pyautogui not available – cannot click")
        return
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button)
    else:
        pyautogui.click(button=button)
    logger.debug(f"Mouse click ({button}) at ({x}, {y})")


def double_click(x: int | None = None, y: int | None = None) -> None:
    """Perform a double-click."""
    if not _HAS_PYAUTOGUI:
        logger.warning("pyautogui not available – cannot double-click")
        return
    if x is not None and y is not None:
        pyautogui.doubleClick(x, y)
    else:
        pyautogui.doubleClick()


def right_click(x: int | None = None, y: int | None = None) -> None:
    """Perform a right-click."""
    click(x, y, button="right")


def move_to(x: int, y: int, duration: float = 0.2) -> None:
    """Move the mouse cursor to absolute screen coordinates."""
    if not _HAS_PYAUTOGUI:
        logger.warning("pyautogui not available – cannot move")
        return
    pyautogui.moveTo(x, y, duration=duration)
    logger.debug(f"Mouse moved to ({x}, {y})")


def move_rel(dx: int, dy: int, duration: float = 0.1) -> None:
    """Move the mouse cursor relative to its current position."""
    if not _HAS_PYAUTOGUI:
        logger.warning("pyautogui not available – cannot move")
        return
    pyautogui.moveRel(dx, dy, duration=duration)


def get_position() -> tuple[int, int]:
    """Return current mouse cursor (x, y)."""
    if _HAS_PYAUTOGUI:
        return pyautogui.position()  # type: ignore[return-value]
    return (0, 0)


def scroll(clicks: int) -> None:
    """Scroll the mouse wheel.

    Args:
        clicks: Positive = scroll up, negative = scroll down.
    """
    if not _HAS_PYAUTOGUI:
        logger.warning("pyautogui not available – cannot scroll")
        return
    pyautogui.scroll(clicks)
    logger.debug(f"Scrolled {clicks} clicks")


def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.3) -> None:
    """Drag from (start_x, start_y) to (end_x, end_y)."""
    if not _HAS_PYAUTOGUI:
        logger.warning("pyautogui not available – cannot drag")
        return
    pyautogui.moveTo(start_x, start_y, duration=duration * 0.3)
    pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration * 0.7, button="left")
    logger.debug(f"Dragged from ({start_x},{start_y}) to ({end_x},{end_y})")
