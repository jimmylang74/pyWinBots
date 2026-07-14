"""WeChat (微信) Windows automation plugin.

Provides MCP tools to launch WeChat, search contacts, and send messages
using pywinauto (uia backend).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from apptools.apptool import AppTool, ToolMap
from automation.app import AppOperations
from automation.ui import UIOperations
from automation.windows import WindowOperations
from base.debug import get_logger

logger = get_logger()

_HAS_PYWINAUTO = False
try:
    import pywinauto
    from pywinauto import Application, Desktop, ElementNotFoundError

    _HAS_PYWINAUTO = True
except ImportError:
    pywinauto = None  # type: ignore[assignment]
    Application = object  # placeholder


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

    async def initialize(self) -> bool:
        self._manifest_data = self._load_manifest()
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

        # Wait for main window
        try:
            win = result.window(title_re="(WeChat|微信)")
            win.wait("visible", timeout=30)
            self._main_window = win
            logger.info("WeChat launched successfully")
            return "微信启动成功，请在手机上扫码登录"
        except Exception as exc:
            try:
                windows = result.windows()
                titles = [w.window_text() for w in windows]
                logger.warning(
                    "WeChat launched but main window not found: %s. "
                    "Top-level windows: %s",
                    exc, titles,
                )
            except Exception:
                logger.warning("WeChat launched but main window not found: %s", exc)
            raise RuntimeError("微信已启动，但未能检测到主窗口")

    def search_contact(self, name: str) -> str:
        """Search for a contact and open their chat window."""
        if not self._ensure_ready():
            raise RuntimeError("微信未启动或主窗口不可用")

        try:
            self._main_window.set_focus()
            time.sleep(0.5)

            # WeChat search is typically at the top of the main window
            # It's an Edit control with specific automation properties
            search_box = self._main_window.child_window(
                control_type="Edit", found_index=0
            )
            search_box.wait("enabled", timeout=5)
            search_box.click_input()
            search_box.type_keys("^a{DELETE}", with_spaces=True)
            time.sleep(0.3)
            search_box.type_keys(name, with_spaces=True)
            time.sleep(1.5)

            # Click the matching contact in search results
            # Try ListItem first, then fallback to Text
            try:
                result_item = self._main_window.child_window(
                    title=name,
                    control_type="ListItem",
                )
                if result_item.exists(timeout=3):
                    result_item.click_input()
                    time.sleep(0.5)
                    logger.info("Contact found: %s", name)
                    return f"已找到联系人: {name}"
            except Exception:
                pass

            # Fallback: try clicking the list item
            try:
                from pywinauto import Desktop

                desktop = Desktop(backend="uia")
                items = desktop.windows(control_type="ListItem")
                for item in items:
                    txt = item.window_text()
                    if name in txt:
                        item.click_input()
                        time.sleep(0.5)
                        logger.info("Contact found (fallback): %s", name)
                        return f"已找到联系人: {name}"
            except Exception as exc:
                logger.warning("Fallback search failed: %s", exc)

            raise RuntimeError(f"未找到联系人: {name}")

        except Exception as exc:
            logger.error("search_contact failed: %s", exc)
            raise

    def send_message(self, contact: str, message: str) -> str:
        """Send a text message to a contact."""
        if not self._ensure_ready():
            raise RuntimeError("微信未启动或主窗口不可用")

        try:
            self.search_contact(contact)
            time.sleep(1)

            # The message input box is typically the last Edit control
            # in the chat window.  WeChat uses a rich-edit control.
            self._main_window.set_focus()
            time.sleep(0.5)

            edits = self._main_window.descendants(control_type="Edit")
            if not edits:
                # Try RichEdit or custom edit
                edits = self._main_window.descendants(control_type="Document")

            if edits:
                # Usually the last edit control is the message input
                input_box = edits[-1]
                input_box.click_input()
                time.sleep(0.3)
                input_box.type_keys(message, with_spaces=True)
                time.sleep(0.5)

                # Send with Enter
                import pyautogui

                pyautogui.press("enter")
                logger.info(
                    "Message sent to %s (%d chars)", contact, len(message)
                )
                return f"消息已成功发送给 {contact}"
            else:
                raise RuntimeError("未找到消息输入框")

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

    def _ensure_ready(self) -> bool:
        """Try to connect or re-connect to the WeChat main window."""
        if self._main_window is not None:
            try:
                if self._main_window.exists():
                    return True
            except Exception:
                pass

        # Re-connect attempt
        try:
            app = Application(backend="uia")
            app.connect(title_re="(WeChat|微信)")
            self._app_ops._apps["weixin"] = app
            self._main_window = app.window(title_re="(WeChat|微信)")
            self._main_window.wait("visible", timeout=5)
            return True
        except Exception:
            logger.warning("Cannot connect to WeChat")
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
