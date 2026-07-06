"""pyWinBots - AppTools Plugin System

Application plugins for Windows app automation. Every sub-directory
containing a manifest.json is a discoverable plugin.

Built-in plugins:
  weixin/   - 微信 (WeChat) automation
"""

from apptools.apptool import AppTool
from apptools.appmgt import AppManager

__all__ = ["AppTool", "AppManager"]
