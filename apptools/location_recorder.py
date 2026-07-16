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
        dll = _MOUSE_HOOK_DLL
        user32 = ctypes.WinDLL('user32')

        WM_MOUSEMOVE = 0x0200

        CB_FUNC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)

        def _hook_cb(nCode, wParam, lParam):
            if nCode >= 0 and wParam == WM_MOUSEMOVE:
                self._last_mouse_x = ctypes.c_int.from_address(lParam).value
                self._last_mouse_y = ctypes.c_int.from_address(lParam + 4).value
            return dll.CallNext(self._hook_id, nCode, wParam, lParam)

        self._c_cb = CB_FUNC(_hook_cb)

        dll.InstallHook.restype = ctypes.c_void_p
        dll.InstallHook.argtypes = [ctypes.c_void_p]
        dll.CallNext.restype = ctypes.c_long
        dll.CallNext.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]

        self._hook_id = dll.InstallHook(self._c_cb)
        if not self._hook_id:
            logger.error("[LR] C hook InstallHook returned NULL")
            return

        logger.info("[LR] C hook installed, recording started")
        if self._status_callback:
            self._status_callback("recording")

        self._poll_thread = threading.Thread(target=self._poll_window_info, args=(user32,), daemon=True)
        self._poll_thread.start()

        dll.RunMessagePump()

    def _poll_window_info(self, user32):
        WindowFromPoint = user32.WindowFromPoint
        WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
        WindowFromPoint.restype = ctypes.wintypes.HWND

        GetAncestor = user32.GetAncestor
        GetAncestor.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint]
        GetAncestor.restype = ctypes.wintypes.HWND

        GetWindowRect = user32.GetWindowRect
        GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
        GetWindowRect.restype = ctypes.c_bool

        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        GetWindowTextW.restype = ctypes.c_int

        GA_ROOT = 1
        last_move_time = time.monotonic()
        last_x = last_y = 0
        idle_logged = True

        while self._running:
            now = time.monotonic()
            x, y = self._last_mouse_x, self._last_mouse_y

            if x != last_x or y != last_y:
                last_move_time = now
                last_x, last_y = x, y
                idle_logged = False
            elif not idle_logged and (now - last_move_time) >= 1.0:
                pt = ctypes.wintypes.POINT(x, y)
                hwnd = WindowFromPoint(pt)
                if hwnd:
                    hwnd = GetAncestor(hwnd, GA_ROOT)
                if hwnd:
                    rect = ctypes.wintypes.RECT()
                    GetWindowRect(hwnd, ctypes.byref(rect))
                    buf = ctypes.create_unicode_buffer(256)
                    GetWindowTextW(hwnd, buf, 256)
                    logger.info(
                        "[LR] Idle window: hwnd=0x%X name='%s' rect=(%d,%d,%d,%d)",
                        hwnd, buf.value, rect.left, rect.top, rect.right, rect.bottom
                    )
                idle_logged = True

            time.sleep(0.2)

    def _run_python_hook(self):
        import ctypes as _ct

        WH_MOUSE_LL = 14
        WM_MOUSEMOVE = 0x0200
        wt = _ct.wintypes
        user32_raw = _ct.WinDLL('user32')

        def _cb(nCode, wParam, lParam):
            if nCode >= 0 and wParam == WM_MOUSEMOVE:
                self._last_mouse_x = _ct.c_int.from_address(lParam).value
                self._last_mouse_y = _ct.c_int.from_address(lParam + 4).value
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

        self._poll_thread = threading.Thread(target=self._poll_window_info, args=(user32_raw,), daemon=True)
        self._poll_thread.start()

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
