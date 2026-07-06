# pyWinBots API & Plugin Development Guide

## 1. Overview

pyWinBots is a Windows automation runtime that exposes app automation tools
via the **Model Context Protocol (MCP)** using **Streamable HTTP** transport.
This document describes how to write custom app plugins and use the MCP API.

---

## 2. Plugin Development

### 2.1 Directory Structure

Each plugin lives in its own directory under `apptools/`:

```
apptools/
├── apptool.py               # Base class (do not modify)
├── appmgt.py                # Plugin manager (do not modify)
└── your_app/                # Your plugin directory
    ├── __init__.py           # (empty or re-export)
    ├── your_app.py           # Plugin implementation
    ├── manifest.json         # Plugin manifest
    └── prompt.md             # LLM prompt / usage guide
```

### 2.2 The Plugin Class

Create a subclass of `AppTool`:

```python
# apptools/your_app/your_app.py
from __future__ import annotations
from typing import Any
from apptools.apptool import AppTool, ToolMap


class YourAppTool(AppTool):
    """Automation plugin for YourApp."""

    @property
    def name(self) -> str:
        return "your_app"

    @property
    def manifest(self) -> dict[str, Any]:
        return self._load_manifest()

    async def initialize(self) -> bool:
        # Setup: check deps, load config, etc.
        return True

    def get_tool_definitions(self) -> ToolMap:
        return {
            "your_app_do_something": (
                self.do_something,
                {"description": "Does something useful"},
            ),
        }

    def do_something(self, param: str) -> str:
        """Tool implementation. Type annotations are required."""
        return f"Done: {param}"

    def _load_manifest(self) -> dict[str, Any]:
        import json
        from pathlib import Path
        path = Path(__file__).parent / "manifest.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}
```

### 2.3 manifest.json

```json
{
  "name": "your_app",
  "display_name": "YourApp",
  "version": "1.0.0",
  "description": "Describe what your plugin does.",
  "app_path": "C:\\Program Files\\YourApp\\YourApp.exe",
  "backend": "uia",
  "capabilities": [
    "your_app_do_something"
  ],
  "tools": {
    "your_app_do_something": {
      "description": "Does something useful",
      "params": [
        {
          "name": "param",
          "type": "string",
          "description": "Parameter description"
        }
      ]
    }
  }
}
```

### 2.4 prompt.md

Write a markdown file that describes your plugin's capabilities to the LLM:

```markdown
# YourApp 自动化插件

## 可用工具
| 工具名 | 功能 | 参数 |
|--------|------|------|
| `your_app_do_something` | 描述 | `param`: 参数说明 |

## 使用说明
1. 调用 your_app_do_something
2. ...
```

### 2.5 Tool function conventions

- **Always add type annotations** – they generate the MCP JSON schema.
- Return a string (the MCP SDK serialises other types automatically, but
  string is the safest cross-platform format).
- Sync functions run in a thread pool; async functions are awaited.
- Use `self._app_ops`, `self._window_ops`, `self._ui_ops` helpers
  from `automation/` for common operations.

### 2.6 Using the Automation API

Your plugin can use the ready-made automation helpers:

```python
from automation.app import AppOperations
from automation.windows import WindowOperations
from automation.ui import UIOperations

self.app_ops = AppOperations(backend="uia")
self.window_ops = WindowOperations(backend="uia")
self.ui_ops = UIOperations()

# Launch an app
self.app_ops.app_launch("C:\\path\\to\\app.exe", "myapp")

# Find a window
win = self.window_ops.window_find(title="My App Window")

# Click a button
self.ui_ops.button_click(win, title="Submit")

# Type text
self.ui_ops.text_set_text(win, text="Hello", auto_id="inputField")
```

---

## 3. MCP API (for AI Agents)

### 3.1 Connecting

The server runs at `http://<host>:<port>/mcp` using Streamable HTTP
transport.

**Python MCP client:**

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async with streamable_http_client(url="http://localhost:8000/mcp") as (r, w):
    async with ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool("tool_name", {"key": "value"})
```

### 3.2 Available Tools

#### Built-in

| Tool | Description |
|------|-------------|
| `pywinbots_list_plugins` | List all loaded plugins |
| `pywinbots_get_plugin_info` | Get detailed plugin info |
| `pywinbots_enable_plugin` | Enable a plugin |
| `pywinbots_disable_plugin` | Disable a plugin |
| `pywinbots_server_info` | Get server status |

#### Plugin tools (example: WeChat)

| Tool | Description |
|------|-------------|
| `weixin_launch` | Launch/connect WeChat |
| `weixin_search_contact` | Search and open contact chat |
| `weixin_send_message` | Send message to contact |
| `weixin_get_main_window` | Get main window info |

---

## 4. Configuration

### 4.1 Server

```bash
python pywinbots.py --port 8000 --host 0.0.0.0 --log-level INFO
```

### 4.2 Plugin enable/disable

Via MCP tools:
```
pywinbots_disable_plugin(plugin_name="weixin")
pywinbots_enable_plugin(plugin_name="weixin")
```

Via Web UI: open `http://localhost:8080` in a browser.

### 4.3 Logging

Logs are written to `~/.pywinbots/logs/pywinbots_<timestamp>.log`.
View them with the Web UI at `/logs` or directly from the filesystem.
