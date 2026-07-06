"""Keyboard operations for pyWinBots.

Provides typed keyboard automation wrappers.
Windows-only; falls back to pyautogui with safe defaults.
"""

import time
from base.debug import get_logger

logger = get_logger()

# ---------------------------------------------------------------------------
# Imports – allow graceful failure on non-Windows / missing deps
# ---------------------------------------------------------------------------
_HAS_PYAUTOGUI = False
_HAS_PYWIN32 = False

try:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _HAS_PYAUTOGUI = True
except ImportError:
    pyautogui = None  # type: ignore[assignment]

try:
    import win32con
    import win32api
    import win32gui

    _HAS_PYWIN32 = True
except ImportError:
    win32con = None  # type: ignore[assignment]
    win32api = None  # type: ignore[assignment]
    win32gui = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def type_text(text: str, interval: float = 0.02) -> None:
    """Type *text* at the currently focused window/control."""
    if _HAS_PYAUTOGUI:
        pyautogui.typewrite(text, interval=interval)
        logger.debug(f"Typed text ({len(text)} chars)")
    else:
        logger.warning("pyautogui not available – cannot type text")


def press_key(key: str, presses: int = 1, interval: float = 0.0) -> None:
    """Press and release a keyboard key.

    Args:
        key: Key name (e.g. 'enter', 'tab', 'escape', 'a').
        presses: Number of times to press.
        interval: Seconds between presses.
    """
    if _HAS_PYAUTOGUI:
        for _ in range(presses):
            pyautogui.press(key)
            if interval > 0:
                time.sleep(interval)
        logger.debug(f"Pressed key '{key}' x{presses}")
    else:
        logger.warning("pyautogui not available – cannot press key")


def hotkey(*keys: str) -> None:
    """Execute a hotkey combination (e.g. hotkey('ctrl', 'c').

    All keys are pressed simultaneously in order, then released in reverse.
    """
    if _HAS_PYAUTOGUI:
        pyautogui.hotkey(*keys)
        logger.debug(f"Hotkey: {'+'.join(keys)}")
    else:
        logger.warning("pyautogui not available – cannot send hotkey")


def key_down(key: str) -> None:
    """Hold a key down."""
    if _HAS_PYAUTOGUI:
        pyautogui.keyDown(key)


def key_up(key: str) -> None:
    """Release a held key."""
    if _HAS_PYAUTOGUI:
        pyautogui.keyUp(key)


def write_text_via_clipboard(text: str) -> None:
    """Write text to the clipboard and paste it via Ctrl+V.

    Fallback for reliable CJK / Unicode text input.
    """
    if _HAS_PYWIN32:
        import win32clipboard  # type: ignore[import-untyped]

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)  # type: ignore[union-attr]
        win32clipboard.CloseClipboard()
        hotkey("ctrl", "v")
        logger.debug(f"Pasted {len(text)} chars via clipboard")
    else:
        type_text(text)
