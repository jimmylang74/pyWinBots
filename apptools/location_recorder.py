"""Location Recorder — launch mouse_overlay.exe, capture first click, save coords."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = __import__("base.debug").get_logger()

_MOUSE_OVERLAY_EXE = (
    Path(__file__).resolve().parent.parent / "mouse_overlay" / "mouse_overlay.exe"
)


@dataclass
class ClickResult:
    handle: str
    title: str
    rel_x: int
    rel_y: int
    abs_x: int
    abs_y: int
    rect_left: int
    rect_top: int
    rect_right: int
    rect_bottom: int


def _parse_click_json(data: dict) -> Optional[ClickResult]:
    try:
        rect = data["rect"]
        mouse = data["mouse"]
    except (KeyError, TypeError):
        return None

    left = int(rect["left"])
    top = int(rect["top"])
    abs_x = int(mouse["x"])
    abs_y = int(mouse["y"])

    return ClickResult(
        handle=str(data.get("handle", "")),
        title=str(data.get("title", "")),
        rel_x=abs_x - left,
        rel_y=abs_y - top,
        abs_x=abs_x,
        abs_y=abs_y,
        rect_left=left,
        rect_top=top,
        rect_right=int(rect["right"]),
        rect_bottom=int(rect["bottom"]),
    )


def _save_to_config(config_path: str, loc_name: str, x: int, y: int) -> None:
    path = Path(config_path)
    if not path.exists():
        logger.error("[LR] Config file not found: %s", config_path)
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("[LR] Failed to read config %s: %s", config_path, exc)
        return

    if "locations" not in data:
        data["locations"] = {}

    data["locations"][loc_name] = [x, y]

    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            "[LR] Saved location '%s' = [%d, %d] → %s", loc_name, x, y, config_path
        )
    except Exception as exc:
        logger.error("[LR] Failed to write config %s: %s", config_path, exc)


def _get_foreground_hwnd() -> Optional[int]:
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if hwnd:
            return hwnd
    except Exception as exc:
        logger.debug("[LR] GetForegroundWindow failed: %s", exc)
    return None


def _restore_foreground(hwnd: Optional[int]) -> None:
    if hwnd is None:
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
        my_tid = kernel32.GetCurrentThreadId()

        user32.AttachThreadInput(my_tid, fg_tid, True)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.SetFocus(hwnd)
        user32.AttachThreadInput(my_tid, fg_tid, False)

        logger.debug("[LR] Restored foreground window handle=%s", hwnd)
    except Exception as exc:
        logger.debug("[LR] Restore foreground failed: %s", exc)


async def record_click(
    config_path: str,
    loc_name: str,
    timeout: float = 0,
) -> Optional[ClickResult]:
    if sys.platform != "win32":
        logger.error("[LR] Location recording is only supported on Windows")
        return None

    if not _MOUSE_OVERLAY_EXE.exists():
        logger.error("[LR] mouse_overlay.exe not found at %s", _MOUSE_OVERLAY_EXE)
        return None

    # Capture the foreground window (browser) before overlay takes focus
    prev_hwnd = _get_foreground_hwnd()
    logger.info(
        "[LR] Starting mouse_overlay.exe (config=%s, loc=%s, prev_hwnd=%s)",
        config_path, loc_name, prev_hwnd,
    )

    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = await asyncio.create_subprocess_exec(
        str(_MOUSE_OVERLAY_EXE),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )

    logger.info("[LR] mouse_overlay.exe started (pid=%d)", proc.pid)

    try:
        result = await _read_click(proc, config_path, loc_name, timeout)
        return result
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
            logger.debug("[LR] mouse_overlay.exe terminated")
        _restore_foreground(prev_hwnd)


async def _read_click(
    proc: asyncio.subprocess.Process,
    config_path: str,
    loc_name: str,
    timeout: float,
) -> Optional[ClickResult]:
    assert proc.stdout is not None

    async def _read_loop() -> Optional[ClickResult]:
        while True:
            line = await proc.stdout.readline()  # type: ignore[union-attr]
            if not line:
                logger.warning("[LR] mouse_overlay.exe stdout closed")
                return None

            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                logger.debug("[LR] mouse_overlay stdout (non-JSON): %s", text)
                continue

            click_result = _parse_click_json(data)
            if click_result is None:
                logger.debug("[LR] mouse_overlay JSON (not click): %s", text)
                continue

            logger.info(
                "[LR] Click captured: handle=%s title='%s' abs=(%d,%d) rel=(%d,%d)",
                click_result.handle,
                click_result.title,
                click_result.abs_x,
                click_result.abs_y,
                click_result.rel_x,
                click_result.rel_y,
            )

            _save_to_config(config_path, loc_name, click_result.rel_x, click_result.rel_y)
            return click_result

    try:
        if timeout > 0:
            return await asyncio.wait_for(_read_loop(), timeout=timeout)
        return await _read_loop()
    except asyncio.TimeoutError:
        logger.warning("[LR] Timeout waiting for click (%.0fs)", timeout)
        return None
