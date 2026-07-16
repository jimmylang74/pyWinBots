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
        self._overlay_hwnd = None
        self._overlay_rect = None
        self._overlay_wndproc = None
        self._overlay_brush = None
        self._overlay_user32 = None
        self._overlay_gdi32 = None
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

    def _create_overlay(self, user32):
        gdi32 = ctypes.WinDLL('gdi32')
        self._overlay_user32 = user32
        self._overlay_gdi32 = gdi32

        COLORKEY = 0x010101
        WNDPROC_TYPE = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.wintypes.HWND,
            ctypes.c_uint,
            ctypes.c_ssize_t,
            ctypes.c_ssize_t,
        )

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", ctypes.wintypes.HINSTANCE),
                ("hIcon", ctypes.wintypes.HANDLE),
                ("hCursor", ctypes.wintypes.HANDLE),
                ("hbrBackground", ctypes.wintypes.HANDLE),
                ("lpszMenuName", ctypes.c_wchar_p),
                ("lpszClassName", ctypes.c_wchar_p),
            ]

        class PAINTSTRUCT(ctypes.Structure):
            _fields_ = [
                ("hdc", ctypes.wintypes.HDC),
                ("fErase", ctypes.c_int),
                ("rcPaint", ctypes.wintypes.RECT),
                ("fRestore", ctypes.c_int),
                ("fIncUpdate", ctypes.c_int),
                ("rgbReserved", ctypes.c_byte * 32),
            ]

        u32 = user32
        g32 = gdi32

        u32.DefWindowProcW.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.c_uint,
            ctypes.c_ssize_t,
            ctypes.c_ssize_t,
        ]
        u32.DefWindowProcW.restype = ctypes.c_ssize_t

        def _wndproc(hwnd, msg, wParam, lParam):
            if msg == 0x000F:
                rect = self._overlay_rect
                ps = PAINTSTRUCT()
                hdc = u32.BeginPaint(hwnd, ctypes.byref(ps))
                if rect is not None:
                    hpen = g32.CreatePen(0, 5, 0x0000FF)
                    old_pen = g32.SelectObject(hdc, hpen)
                    old_brush = g32.SelectObject(hdc, g32.GetStockObject(5))
                    g32.Rectangle(hdc, rect[0], rect[1], rect[2], rect[3])
                    g32.SelectObject(hdc, old_pen)
                    g32.SelectObject(hdc, old_brush)
                    g32.DeleteObject(hpen)
                u32.EndPaint(hwnd, ctypes.byref(ps))
                return 0
            return u32.DefWindowProcW(hwnd, msg, wParam, lParam)

        self._overlay_wndproc = WNDPROC_TYPE(_wndproc)

        hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)

        wc = WNDCLASSW()
        wc.style = 0x0002 | 0x0001
        wc.lpfnWndProc = ctypes.cast(self._overlay_wndproc, ctypes.c_void_p).value
        wc.hInstance = hInstance
        wc.lpszClassName = "PyWinBotsOverlay"
        wc.hbrBackground = gdi32.CreateSolidBrush(COLORKEY)
        self._overlay_brush = wc.hbrBackground

        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom:
            logger.error("[LR] Overlay RegisterClassW failed: %d", ctypes.get_last_error())
            return False

        sx = user32.GetSystemMetrics(76)
        sy = user32.GetSystemMetrics(77)
        scx = user32.GetSystemMetrics(78)
        scy = user32.GetSystemMetrics(79)

        ex_style = 0x00000008 | 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000
        hwnd = user32.CreateWindowExW(
            ex_style,
            "PyWinBotsOverlay",
            None,
            0x80000000,
            sx, sy, scx, scy,
            None, None, hInstance, None,
        )

        if not hwnd:
            logger.error("[LR] Overlay CreateWindowExW failed: %d", ctypes.get_last_error())
            user32.UnregisterClassW("PyWinBotsOverlay", hInstance)
            return False

        user32.SetLayeredWindowAttributes(hwnd, COLORKEY, 0, 0x00000001)
        user32.ShowWindow(hwnd, 5)
        user32.UpdateWindow(hwnd)

        self._overlay_hwnd = hwnd
        logger.info("[LR] Overlay created hwnd=0x%X (%dx%d)", hwnd, scx, scy)
        return True

    def _destroy_overlay(self):
        if not self._overlay_hwnd:
            return
        user32 = self._overlay_user32
        if user32:
            user32.ShowWindow(self._overlay_hwnd, 0)
            user32.DestroyWindow(self._overlay_hwnd)
            hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
            user32.UnregisterClassW("PyWinBotsOverlay", hInstance)
        if self._overlay_brush and self._overlay_gdi32:
            self._overlay_gdi32.DeleteObject(self._overlay_brush)
        self._overlay_hwnd = None
        self._overlay_rect = None
        self._overlay_wndproc = None
        self._overlay_brush = None
        self._overlay_user32 = None
        self._overlay_gdi32 = None
        logger.info("[LR] Overlay destroyed")

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

        try:
            self._create_overlay(user32)
        except Exception as exc:
            logger.warning("[LR] Overlay creation failed: %s", exc)

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

        GetClassNameW = user32.GetClassNameW
        GetClassNameW.argtypes = [ctypes.wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        GetClassNameW.restype = ctypes.c_int

        EnumWindows = user32.EnumWindows
        IsWindowVisible = user32.IsWindowVisible
        InvalidateRect = user32.InvalidateRect
        InvalidateRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_bool]
        InvalidateRect.restype = ctypes.c_bool
        UpdateWindow = user32.UpdateWindow
        UpdateWindow.argtypes = [ctypes.wintypes.HWND]
        UpdateWindow.restype = ctypes.c_bool

        GA_ROOT = 1
        ENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LPARAM,
        )
        last_move_time = time.monotonic()
        last_x = last_y = 0
        idle_logged = True

        def _find_titled_window_at(x_coord, y_coord):
            found = [None]

            def _cb(hwnd, _lparam):
                if not IsWindowVisible(hwnd):
                    return True
                b = ctypes.create_unicode_buffer(256)
                GetWindowTextW(hwnd, b, 256)
                if not b.value:
                    return True
                r = ctypes.wintypes.RECT()
                if not GetWindowRect(hwnd, ctypes.byref(r)):
                    return True
                if r.left <= x_coord <= r.right and r.top <= y_coord <= r.bottom:
                    found[0] = hwnd
                    return False
                return True

            cb = ENUMPROC(_cb)
            EnumWindows(cb, 0)
            return found[0]

        while self._running:
            now = time.monotonic()
            x, y = self._last_mouse_x, self._last_mouse_y

            if x != last_x or y != last_y:
                last_move_time = now
                last_x, last_y = x, y
                idle_logged = False
                try:
                    if self._overlay_hwnd and self._overlay_rect is not None:
                        self._overlay_rect = None
                        InvalidateRect(self._overlay_hwnd, None, True)
                        UpdateWindow(self._overlay_hwnd)
                except Exception as exc:
                    logger.debug("[LR] overlay clear failed: %s", exc)
            elif not idle_logged and (now - last_move_time) >= 1.0:
                pt = ctypes.wintypes.POINT(x, y)
                hwnd = WindowFromPoint(pt)
                if hwnd:
                    hwnd = GetAncestor(hwnd, GA_ROOT)

                # WindowFromPoint may hit DWM ghost windows (#32769) or other
                # system overlays that have no title. When that happens,
                # enumerate visible top-level windows and find the first one
                # with a title that actually contains the cursor point.
                if hwnd:
                    buf = ctypes.create_unicode_buffer(256)
                    GetWindowTextW(hwnd, buf, 256)
                    if not buf.value:
                        cls_buf = ctypes.create_unicode_buffer(256)
                        GetClassNameW(hwnd, cls_buf, 256)
                        logger.debug(
                            "[LR] HWND 0x%X has no title (class='%s'), "
                            "scanning visible windows at (%d,%d)",
                            hwnd, cls_buf.value, x, y,
                        )
                        hwnd = _find_titled_window_at(x, y)

                if hwnd:
                    rect = ctypes.wintypes.RECT()
                    GetWindowRect(hwnd, ctypes.byref(rect))
                    buf = ctypes.create_unicode_buffer(256)
                    GetWindowTextW(hwnd, buf, 256)
                    logger.info(
                        "[LR] Idle window: hwnd=0x%X name='%s' rect=(%d,%d,%d,%d)",
                        hwnd, buf.value, rect.left, rect.top, rect.right, rect.bottom
                    )
                    try:
                        self._overlay_rect = (rect.left, rect.top, rect.right, rect.bottom)
                        if self._overlay_hwnd:
                            InvalidateRect(self._overlay_hwnd, None, False)
                            UpdateWindow(self._overlay_hwnd)
                    except Exception as exc:
                        logger.debug("[LR] overlay update failed: %s", exc)
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

        try:
            self._create_overlay(user32_raw)
        except Exception as exc:
            logger.warning("[LR] Overlay creation failed: %s", exc)

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
        self._destroy_overlay()
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
