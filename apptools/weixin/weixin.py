"""WeChat (微信) Windows automation plugin.

Provides MCP tools to launch WeChat, search contacts, and send messages
using pywinauto (uia backend).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from apptools.apptool import AppTool, ToolMap
from automation.app import AppOperations
from automation.ui import UIOperations
from automation.windows import WindowOperations
from base.debug import get_logger

logger = get_logger()

_HAS_PSUTIL = False
try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore[assignment]

_HAS_PYWINAUTO = False
try:
    import pywinauto
    from pywinauto import Application, Desktop, ElementNotFoundError

    _HAS_PYWINAUTO = True
except ImportError:
    pywinauto = None  # type: ignore[assignment]
    Application = object  # placeholder

_HAS_PYAUTOGUI = False
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    _HAS_PYAUTOGUI = True
except ImportError:
    pyautogui = None  # type: ignore[assignment]

_HAS_PYPERCLIP = False
try:
    import pyperclip
    _HAS_PYPERCLIP = True
except ImportError:
    pyperclip = None  # type: ignore[assignment]


def _clipboard_paste(text: str) -> None:
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return
    except Exception:
        pass

    import subprocess
    ps_cmd = f'Set-Clipboard -Value "{text}"'
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_cmd],
        capture_output=True, timeout=5,
    )




def _log_process_tree(parent_pid: int) -> None:
    """Log the process tree rooted at *parent_pid* with window titles."""
    if not _HAS_PSUTIL:
        logger.debug("[process-tree] psutil not installed – skipping")
        return

    try:
        parent = psutil.Process(parent_pid)
    except psutil.NoSuchProcess:
        logger.debug("[process-tree] PID %d not found", parent_pid)
        return

    def _walk(proc: psutil.Process, depth: int = 0) -> None:
        prefix = "  " * depth
        try:
            name = proc.name()
            status = proc.status()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        logger.debug("[process-tree] %s├─ pid=%d  name=%r  status=%s", prefix, proc.pid, name, status)
        try:
            children = proc.children(recursive=False)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            children = []
        for child in children:
            _walk(child, depth + 1)

    logger.debug("[process-tree] Process tree for parent pid=%d:", parent_pid)
    _walk(parent)


class WeixinTool(AppTool):
    """WeChat automation plugin."""

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "weixin"

    @property
    def manifest(self) -> dict[str, Any]:
        return self._load_manifest()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        super().__init__()
        self._manifest_data: dict[str, Any] = {}
        self._app_ops = AppOperations(backend="uia")
        self._window_ops = WindowOperations(backend="uia")
        self._ui_ops = UIOperations()

        # WeChat uses "WeChat" / "微信" as window title pattern
        self._main_window = None

        # Default UI offsets (relative to main window top-left)
        self._searchbox_offset = [320, 100]
        self._messageinput_offset = [600, 1500]

    async def initialize(self) -> bool:
        self._manifest_data = self._load_manifest()
        locations = self._manifest_data.get("locations", {})
        self._searchbox_offset = locations.get(
            "searchbox_offset", self._searchbox_offset
        )
        self._messageinput_offset = locations.get(
            "messageinput_offset", self._messageinput_offset
        )
        logger.info("Weixin plugin initialized")
        return True

    # ------------------------------------------------------------------
    # Tool definitions
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> ToolMap:
        return {
            "weixin_launch": (
                self.launch_weixin,
                {"description": "启动微信 Windows 客户端。如果微信已在运行则直接连接。"},
            ),
            "weixin_search_contact": (
                self.search_contact,
                {
                    "description": "搜索微信联系人并打开聊天窗口。",
                    "parameters": {
                        "name": {
                            "type": "string",
                            "description": "联系人姓名或昵称",
                        }
                    },
                },
            ),
            "weixin_send_message": (
                self.send_message,
                {
                    "description": "向指定联系人发送文本消息。自动搜索联系人并进入聊天窗口。",
                    "parameters": {
                        "contact": {
                            "type": "string",
                            "description": "联系人姓名或昵称",
                        },
                        "message": {
                            "type": "string",
                            "description": "要发送的消息内容",
                        },
                    },
                },
            ),
            "weixin_get_main_window": (
                self.get_main_window_info,
                {"description": "获取微信主窗口的位置、大小和标题信息。"},
            ),
        }

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def launch_weixin(self) -> str:
        """Launch WeChat or connect if already running."""
        # Try to connect first
        try:
            app = Application(backend="uia")
            app.connect(title_re="(WeChat|微信)")
            self._app_ops._apps["weixin"] = app
            win = app.window(title_re="(WeChat|微信)")
            self._main_window = win
            logger.info("Connected to running WeChat")
            return "微信已在运行中，已连接成功"
        except Exception:
            pass

        # Launch
        app_path = self._manifest_data.get("app_path", "")
        app_args = self._manifest_data.get("app_args", "")
        if not app_path:
            raise RuntimeError("未配置微信路径 (manifest.json 中的 app_path)")

        result = self._app_ops.app_launch(app_path, "weixin", timeout=30, args=app_args)
        if result is None:
            raise RuntimeError(f"启动失败: {app_path}")

        parent_pid = result.process
        logger.debug("[launch_weixin DEBUG] Parent process: %d", parent_pid)
        _log_process_tree(parent_pid)

        title_pattern = "(?i)(wechat|微信)"
        max_wait = 30
        poll_interval = 2
        win = None

        desktop = Desktop(backend="uia")

        for elapsed in range(0, max_wait, poll_interval):
            try:
                all_windows = desktop.windows()
                logger.debug(
                    "[launch_weixin DEBUG] t=%ds: %d desktop window(s):",
                    elapsed, len(all_windows),
                )
                for w in all_windows:
                    try:
                        logger.debug("  title=%r  pid=%s", w.window_text(), w.process_id())
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[launch_weixin DEBUG] t=%ds: desktop enumerate failed: %s", elapsed, exc)
                all_windows = []

            for w in all_windows:
                try:
                    title = w.window_text()
                    if re.search(title_pattern, title):
                        win = w
                        logger.debug("[launch_weixin DEBUG] Matched: title=%r", title)
                        break
                except Exception:
                    continue

            if win is not None:
                break

            logger.debug(
                "[launch_weixin DEBUG] No match in %d window(s) – retrying",
                len(all_windows),
            )
            time.sleep(poll_interval)

        if win is not None:
            try:
                pid = win.process_id()
                app = Application(backend="uia")
                app.connect(process=pid)
                self._app_ops._apps["weixin"] = app
                self._main_window = self._pick_main_window(app, title_pattern)
                logger.info(
                    "WeChat launched & connected via Application (pid=%d, title=%r)",
                    pid, self._main_window.window_text(),
                )
            except Exception as exc:
                logger.warning("Application.connect failed (%s), falling back to raw UIAWrapper", exc)
                self._main_window = win
            return "微信启动成功，请在手机上扫码登录"

        logger.warning("WeChat launched but main window not found after %ds", max_wait)
        raise RuntimeError("微信已启动，但未能检测到主窗口")

    def search_contact(self, name: str) -> str:
        if not self._ensure_ready():
            raise RuntimeError("微信未启动或主窗口不可用")
        if not _HAS_PYAUTOGUI:
            raise RuntimeError("pyautogui 未安装，无法使用坐标定位")

        t0 = time.monotonic()
        def elapsed():
            return f"{time.monotonic() - t0:.2f}s"

        try:
            logger.info("[search_contact] step 1/5: set_focus ...")
            self._main_window.set_focus()
            time.sleep(0.5)
            rect = self._main_window.rectangle()
            logger.info("[search_contact] step 1/5 done (%s) - window rect=(%d,%d,%d,%d)",
                        elapsed(), rect.left, rect.top, rect.right, rect.bottom)

            search_x = rect.left + self._searchbox_offset[0]
            search_y = rect.top + self._searchbox_offset[1]
            logger.info("[search_contact] step 2/5: click search box at (%d, %d) ...", search_x, search_y)
            pyautogui.click(search_x, search_y)
            time.sleep(0.5)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("delete")
            time.sleep(0.2)
            logger.info("[search_contact] step 2/5 done (%s)", elapsed())

            logger.info("[search_contact] step 3/5: type name %r ...", name)
            _clipboard_paste(name)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(2.0)
            logger.info("[search_contact] step 3/5 done (%s)", elapsed())

            logger.info("[search_contact] step 4/5: press Enter ...")
            pyautogui.press("enter")
            time.sleep(1.0)
            logger.info("[search_contact] step 4/5 done (%s)", elapsed())

            logger.info("[search_contact] step 5/5: verify ...")
            logger.info("[search_contact] DONE (%s) - 已点击联系人: %s", elapsed(), name)
            return f"已找到联系人: {name}"

        except Exception as exc:
            logger.error("[search_contact] FAILED at (%s): %s", elapsed(), exc)
            raise

    def send_message(self, contact: str, message: str) -> str:
        if not self._ensure_ready():
            raise RuntimeError("微信未启动或主窗口不可用")
        if not _HAS_PYAUTOGUI:
            raise RuntimeError("pyautogui 未安装，无法使用坐标定位")

        try:
            self.search_contact(contact)
            time.sleep(1)

            self._main_window.set_focus()
            time.sleep(0.5)
            rect = self._main_window.rectangle()

            input_x = rect.left + self._messageinput_offset[0]
            input_y = rect.top + self._messageinput_offset[1]
            logger.info("[send_message] click input box at (%d, %d)", input_x, input_y)
            pyautogui.click(input_x, input_y)
            time.sleep(0.3)

            _clipboard_paste(message)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.5)

            pyautogui.press("enter")
            logger.info("Message sent to %s (%d chars)", contact, len(message))
            return f"消息已成功发送给 {contact}"

        except Exception as exc:
            logger.error("send_message failed: %s", exc)
            raise

    def get_main_window_info(self) -> str:
        """Return info about the WeChat main window."""
        if not self._ensure_ready():
            raise RuntimeError("微信未启动或主窗口不可用")

        try:
            rect = self._main_window.rectangle()
            info = (
                f"微信主窗口\n"
                f"  标题: {self._main_window.window_text()}\n"
                f"  位置: ({rect.left}, {rect.top})\n"
                f"  大小: {rect.width()} x {rect.height()}\n"
                f"  可见: {self._main_window.is_visible()}\n"
                f"  激活: {self._main_window.is_active()}"
            )
            return info
        except Exception as exc:
            logger.error("get_main_window_info failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick_main_window(self, app: Application, title_pattern: str):
        candidates = app.windows()
        logger.debug("[_pick_main_window] %d window(s) from Application:", len(candidates))
        best_title = None
        best_area = 0
        for w in candidates:
            try:
                title = w.window_text()
                rect = w.rectangle()
                area = rect.width() * rect.height()
                visible = w.is_visible()
                logger.debug(
                    "  title=%r  rect=(%d,%d,%d,%d)  area=%d  visible=%s",
                    title, rect.left, rect.top, rect.right, rect.bottom, area, visible,
                )
                if visible and area > best_area:
                    best_title = title
                    best_area = area
            except Exception as exc:
                logger.debug("  (read failed: %s)", exc)
        if best_title is None:
            logger.warning("[_pick_main_window] no visible window found, falling back to regex")
            return app.window(title_re=title_pattern)
        logger.debug("[_pick_main_window] selected: title=%r  area=%d", best_title, best_area)
        return app.window(title=best_title)

    def _log_window_layout(self, window, depth: int = 0, max_depth: int = 5) -> None:
        prefix = "  " * depth
        try:
            children = window.children()
        except Exception:
            children = []
        for child in children:
            try:
                ctrl = child.element_info.control_type
                title = child.window_text()[:40]
                auto_id = getattr(child.element_info, "automation_id", "")
                class_name = getattr(child.element_info, "class_name", "")
                rect = child.rectangle()
                logger.debug(
                    "%s[%s] title=%r  auto_id=%r  class=%r  rect=(%d,%d,%d,%d)",
                    prefix, ctrl, title, auto_id, class_name,
                    rect.left, rect.top, rect.right, rect.bottom,
                )
                if depth < max_depth:
                    self._log_window_layout(child, depth + 1, max_depth)
            except Exception as exc:
                logger.debug("%s  (read failed: %s)", prefix, exc)

    def _is_valid_main_window(self, window) -> bool:
        if window is None:
            return False
        try:
            if not window.exists():
                return False
            rect = window.rectangle()
            area = rect.width() * rect.height()
            if area < 10000:
                logger.debug(
                    "[_ensure_ready] cached window too small (%dx%d=%d), rejecting",
                    rect.width(), rect.height(), area,
                )
                return False
            return True
        except Exception:
            return False

    def _ensure_ready(self) -> bool:
        if self._is_valid_main_window(self._main_window):
            return True

        try:
            app = Application(backend="uia")
            app.connect(title_re="(WeChat|微信)")
            self._app_ops._apps["weixin"] = app
            self._main_window = self._pick_main_window(app, "(WeChat|微信)")
            self._main_window.wait("visible", timeout=5)
            return True
        except Exception:
            logger.warning("Cannot connect to WeChat, attempting to launch")
            try:
                self.launch_weixin()
                return True
            except Exception as launch_exc:
                logger.error("Auto-launch WeChat failed: %s", launch_exc)
                return False

    def _load_manifest(self) -> dict[str, Any]:
        """Load manifest.json from the same directory."""
        manifest_path = Path(__file__).parent / "manifest.json"
        if manifest_path.exists():
            try:
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.error("Failed to read manifest: %s", exc)
        return {}
