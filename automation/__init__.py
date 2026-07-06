"""pyWinBots - Automation Module

Provides reusable automation primitives for Windows applications:
- ui: UI element operations (click, type, select)
- windows: Window management (find, dump, control navigation)
- app: Application lifecycle (launch, close, connect)

All operations gracefully degrade when pywinauto / uiautomation
are not available (e.g. on Linux).
"""

from automation.ui import UIOperations
from automation.windows import WindowOperations
from automation.app import AppOperations

__all__ = ["UIOperations", "WindowOperations", "AppOperations"]
