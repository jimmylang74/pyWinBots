"""Low-level mouse hook implemented in C for zero-Python-overhead."""

import ctypes
import os
import sys
import threading
import time
from typing import Callable, Optional

logger = __import__('base.debug').get_logger()

_MOUSE_HOOK_DLL = None

if sys.platform == "win32":
    _dll_path = os.path.join(os.path.dirname(__file__), "mouse_hook.dll")
    if os.path.exists(_dll_path):
        _MOUSE_HOOK_DLL = ctypes.WinDLL(_dll_path)
    else:
        logger.warning("[LR] mouse_hook.dll not found at %s, falling back to pure Python", _dll_path)


class LocationRecorder:
    def __init__(self, auto_start_name: str = ""):
        self._hook_id = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._status_callback: Optional[Callable[[str], None]] = None
        self._last_mouse_x: int = 0
        self._last_mouse_y: int = 0
        self._has_event: bool = False
        self._c_event = threading.Event()
        if auto_start_name:
            logger.info("[LR] Auto-starting with name='%s'", auto_start_name)
            self.start_recording(auto_start_name, None, None)

    def start_recording(self, name: str, result_cb, status_cb):
        if self._running:
            return False
        self._status_callback = status_cb
        self._running = True

        if sys.platform != "win32":
            logger.error("Location recording is only supported on Windows")
            return False

        self._thread = threading.Thread(target=self._run_hook_thread, daemon=True)
        self._thread.start()
        return True

    def is_running(self):
        return self._running

    def _run_hook_thread(self):
        if sys.platform != "win32":
            logger.error("Location recording is only supported on Windows")
            return

        if _MOUSE_HOOK_DLL is not None:
            self._run_c_hook()
        else:
            self._run_python_hook()

        self._cleanup()

    def _run_c_hook(self):
        """Pure-C hook path: callback runs 100% in C, zero Python overhead."""
        dll = _MOUSE_HOOK_DLL

        self._hook_id = dll.InstallHook()
        if not self._hook_id:
            logger.error("[LR] C hook InstallHook returned NULL")
            return

        logger.info("[LR] C hook installed (zero-Python overhead), recording started")
        if self._status_callback:
            self._status_callback("recording")

        # Lightweight poll thread: reads C globals at 10 Hz, does cooldown logic
        def _poll():
            x = ctypes.c_int(0)
            y = ctypes.c_int(0)
            left = ctypes.c_int(0)
            top = ctypes.c_int(0)
            right = ctypes.c_int(0)
            bottom = ctypes.c_int(0)
            name_buf = ctypes.create_unicode_buffer(256)

            while self._running:
                if dll.HasWindowInfo():
                    hwnd = dll.GetIdleWindowHandle()
                    dll.GetIdleWindowRect(
                        ctypes.byref(left), ctypes.byref(top),
                        ctypes.byref(right), ctypes.byref(bottom)
                    )
                    dll.GetIdleWindowName(name_buf, 256)
                    logger.info(
                        "[LR] Idle window: hwnd=%s name='%s' rect=(%d,%d,%d,%d)",
                        hwnd, name_buf.value,
                        left.value, top.value, right.value, bottom.value
                    )
                time.sleep(0.1)

        self._poll_thread = threading.Thread(target=_poll, daemon=True)
        self._poll_thread.start()

        # Blocks until StopMessagePump() is called
        dll.RunMessagePump()

    def _run_python_hook(self):
        import ctypes as _ct

        WH_MOUSE_LL = 14
        WM_MOUSEMOVE = 0x0200

        wt = _ct.wintypes

        class MOUSEHOOKSTRUCT(_ct.Structure):
            _fields_ = [
                ("pt", wt.POINT),
                ("hwnd", wt.HWND),
                ("wHitTestCode", wt.UINT),
                ("dwExtraInfo", _ct.POINTER(_ct.c_ulong)),
            ]

        user32_raw = _ct.WinDLL('user32')

        def _cb(nCode, wParam, lParam):
            if nCode >= 0 and wParam == WM_MOUSEMOVE:
                self._last_mouse_x = _ct.c_int.from_address(lParam).value
                self._last_mouse_y = _ct.c_int.from_address(lParam + 4).value
                self._has_event = True
            return user32_raw.CallNextHookEx(self._hook_id, nCode, wParam, _ct.c_void_p(lParam))

        CB = _ct.WINFUNCTYPE(_ct.c_int, _ct.c_int, wt.WPARAM, wt.LPARAM)
        self._c_cb = CB(_cb)
        self._hook_id = user32_raw.SetWindowsHookExW(WH_MOUSE_LL, self._c_cb, None, 0)
        if not self._hook_id:
            logger.error("[LR] SetWindowsHookExW returned NULL")
            return

        logger.info("[LR] Python hook installed (slower than C version)")
        if self._status_callback:
            self._status_callback("recording")

        try:
            msg = wt.MSG()
            while self._running:
                user32_raw.MsgWaitForMultipleObjects(0, None, False, 200, 0)
                while user32_raw.PeekMessageW(_ct.byref(msg), None, 0, 0, 1):
                    user32_raw.TranslateMessage(_ct.byref(msg))
                    user32_raw.DispatchMessageW(_ct.byref(msg))
        except Exception as e:
            logger.error("[LR] message pump error: %s", e, exc_info=True)

    def _cleanup(self):
        if _MOUSE_HOOK_DLL and self._hook_id:
            _MOUSE_HOOK_DLL.UninstallHook()
        elif self._hook_id:
            import ctypes as _ct
            user32_raw = _ct.WinDLL('user32')
            user32_raw.UnhookWindowsHookEx(self._hook_id)
        self._hook_id = None
        self._running = False
        if self._status_callback:
            self._status_callback("stopped")

    def stop_recording(self):
        if not self._running:
            return
        self._running = False
        if _MOUSE_HOOK_DLL:
            _MOUSE_HOOK_DLL.StopMessagePump()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
