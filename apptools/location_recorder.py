import threading
from typing import Callable, Optional
from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import sys
import json
from pathlib import Path

logger = __import__('base.debug').get_logger()

@dataclass
class LocationRecordResult:
    name: str
    x: int
    y: int

_HAS_PYSIDE6 = False
try:
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtCore import Qt, QRect
    from PySide6.QtGui import QPainter, QColor, QPen
    _HAS_PYSIDE6 = True
except ImportError:
    QApplication = None
    QWidget = None
    Qt = None
    QRect = None
    QPainter = None
    QColor = None
    QPen = None

class OverlayWindow:
    def __init__(self):
        if not _HAS_PYSIDE6:
            raise RuntimeError("PySide6 is not installed or could not be imported.")
            
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.widget = QWidget()
        self.widget.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        # WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOPMOST
        self.widget.setAttribute(Qt.WA_TranslucentBackground)
        self.widget.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        self._rect = QRect()
        self._color = QColor(255, 0, 0, 255)
        self._pen_width = 3

        self.widget.paintEvent = self._paint_event
        screen_geo = self.app.primaryScreen().geometry()
        self.widget.setGeometry(screen_geo)

    def show(self):
        self.widget.show()

    def update_rect(self, x, y, w, h):
        self._rect = QRect(x, y, w, h)
        self.widget.update()

    def _paint_event(self, event):
        if self._rect.isNull():
            return
        painter = QPainter(self.widget)
        pen = QPen(self._color, self._pen_width)
        painter.setPen(pen)
        painter.drawRect(self._rect.adjusted(self._pen_width//2, self._pen_width//2, -self._pen_width//2, -self._pen_width//2))
        painter.end()

    def close(self):
        self.widget.close()

# Win32 constants
WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

class MOUSEHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("hwnd", wintypes.HWND),
        ("wHitTestCode", wintypes.UINT),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

if sys.platform == "win32":
    user32 = ctypes.WinDLL('user32', use_last_error=True)
else:
    user32 = None
    logger.warning("location_recorder: Windows APIs not available on this platform")

class LocationRecorder:
    def __init__(self):
        self._hook_id = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._overlay: Optional[OverlayWindow] = None
        self._result_callback: Optional[Callable[[LocationRecordResult], None]] = None
        self._status_callback: Optional[Callable[[str], None]] = None
        self._target_name = ""

    def _low_level_mouse_proc(self, nCode, wParam, lParam):
        if nCode >= 0:
            if wParam == WM_MOUSEMOVE:
                hook_struct = ctypes.cast(lParam, ctypes.POINTER(MOUSEHOOKSTRUCT)).contents
                x, y = hook_struct.pt.x, hook_struct.pt.y
                self._handle_mouse_move(x, y)
            elif wParam == WM_LBUTTONDOWN:
                hook_struct = ctypes.cast(lParam, ctypes.POINTER(MOUSEHOOKSTRUCT)).contents
                x, y = hook_struct.pt.x, hook_struct.pt.y
                # We handle click asynchronously so we don't block the hook too long
                # and we can cleanly unhook.
                threading.Thread(target=self._handle_click, args=(x, y), daemon=True).start()
                return 1 # Block the click so the app doesn't receive it!
        return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

    def _handle_mouse_move(self, x, y):
        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
        # GetAncestor(hwnd, GA_ROOTOWNER) is good, but RootWindow is usually fine too
        hwnd = user32.GetAncestor(hwnd, 2) # GA_ROOT = 2
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        self._overlay.update_rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def _handle_click(self, x, y):
        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
        hwnd = user32.GetAncestor(hwnd, 2)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        
        rel_x = x - rect.left
        rel_y = y - rect.top
        
        if self._result_callback:
            self._result_callback(LocationRecordResult(
                name=self._target_name,
                x=rel_x,
                y=rel_y
            ))
        
        self.stop_recording()

    def is_running(self):
        return self._running

    def start_recording(self, name: str, result_cb, status_cb):
        if self._running:
            return False
        self._target_name = name
        self._result_callback = result_cb
        self._status_callback = status_cb
        self._running = True
        
        self._thread = threading.Thread(target=self._run_hook, daemon=True)
        self._thread.start()
        return True

    def _run_hook_hook(self):
        try:
            self._overlay = OverlayWindow()
            self.app = self._overlay.app
            self._overlay.show()
        except Exception as e:
            logger.error("Failed to create OverlayWindow: %s", e)
            return

        if sys.platform == "win32":
            self._hook_id = user32.SetWindowsHookExW(
                WH_MOUSE_LL,
                ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)(self._low_level_mouse_proc),
                None,
                0
            )
        else:
            logger.error("Location recording is only supported on Windows")
            return
        
        if self._status_callback:
            self._status_callback("recording")
            
        self.app.exec()
        
        self._cleanup()

    def _run_hook(self):
        self._run_hook_hook()

    def _cleanup(self):
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
        if self._overlay:
            self._overlay.close()
            self._overlay = None
        self._running = False
        if self._status_callback:
            self._status_callback("stopped")

    def stop_recording(self):
        if not self._running:
            return
        # We need to stop the Qt loop from another thread or from within the hook.
        # Since _handle_click runs in a separate thread, we can call app.quit()
        if self._overlay and self._overlay.app:
            self._overlay.app.quit()
