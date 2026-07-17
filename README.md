# pyWinBots

**Windows Compute Use Runtime for AI Agents**

pyWinBots is a **Model Context Protocol (MCP) server** that lets AI agents
directly control Windows applications. It provides a plugin-based architecture
for Windows automation – launch apps, click buttons, type text, send messages,
and more – all through the standard MCP protocol.

## Features

- **MCP Server** – Streamable HTTP transport, compatible with any MCP client
- **Plugin System** – Hot-pluggable app modules with manifest + LLM prompts
- **Automation Engine** – Built on pywinauto + uiautomation + pyautogui
- **WeChat Plugin** – Launch, search contacts, send messages (example)
- **Web UI** – Single-page application dashboard (FastAPI + vanilla ES modules)
  - Plugin management (enable/disable, search, detail inspection)
  - **Config editor** – Edit plugin `manifest.json` via web interface
  - **Live logs** – Auto-refreshing runtime log viewer with level highlighting
- **Comprehensive Logging** – Console + file output with timestamps

## Quick Start

### Prerequisites

- Python 3.10+
- Windows (for automation features; MCP server works on Linux for dev)

### Installation

```bash
git clone <repo> pywinbots
cd pywinbots
pip install -r requirements.txt
```

On Linux, the Windows-only packages (`pywinauto`, `uiautomation`, `pywin32`)
will fail to install. Install only the cross-platform dependencies instead:

```bash
pip install fastapi uvicorn jinja2 python-multipart mcp
```

### Run the full server (MCP + Web UI)

```bash
python pywinbots.py
```

| Service | Address | Default port |
|---------|---------|--------------|
| MCP server | `http://0.0.0.0:8000/mcp` | `8000` |
| Web dashboard | `http://0.0.0.0:6565` | `6565` |

Use `--port` / `--web-port` to customise:

```bash
python pywinbots.py --port 9000 --web-port 8080
python pywinbots.py --no-web                  # MCP only, no dashboard
python pywinbots.py --log-level DEBUG          # verbose logging
```

### Run the Web UI standalone (Linux dev)

```bash
python -m webui.webui --port 8080
```

Open `http://localhost:8080` – dashboard, logs, and config editor all work
without Windows automation dependencies.

### Run the test client

Ensure the server is running, then:

```bash
python test.py
```

## Project Structure

```
pywinbots/
├── pywinbots.py               # Main entry point
├── test.py                    # MCP test client
├── test.json                  # Test configuration
├── requirements.txt           # Dependencies
├── README.md                  # This file
├── API.md                     # Plugin development guide
│
├── base/                      # Basic utilities
│   ├── debug.py               #   Logging
│   ├── kb.py                  #   Keyboard operations
│   └── mouse.py               #   Mouse operations
│
├── automation/                # Automation engine
│   ├── app.py                 #   App lifecycle (launch/close/connect)
│   ├── windows.py             #   Window discovery & tree dump
│   └── ui.py                  #   UI element operations (click, type)
│
├── apptools/                  # Plugin system
│   ├── apptool.py             #   Base class for plugins
│   ├── appmgt.py              #   Plugin manager (scan/load/manage)
│   └── weixin/                #   WeChat (微信) plugin
│       ├── weixin.py          #     Plugin implementation
│       ├── manifest.json      #     App metadata & capabilities
│       └── prompt.md          #     LLM usage instructions
│
├── mcp_server/                # MCP protocol layer
│   └── server.py              #   FastMCP + Streamable HTTP
│
└── webui/                     # Configuration management UI
    ├── webui.py               #   FastAPI application
    ├── static/js/             #   ES modules (SPA)
    │   ├── api.js             #     fetch helper
    │   ├── app.js             #     routing, init, event delegation
    │   ├── dashboard.js       #     stats, plugin grid, toggle
    │   ├── logs.js            #     live log viewer
    │   └── modal.js           #     detail + config editor
    └── templates/
        └── index.html         #   SPA shell
```

## Creating a Plugin

See [API.md](API.md) for the full plugin development guide.

Short version:

1. Create `apptools/<your_app>/` directory
2. Write `manifest.json`
3. Subclass `AppTool` and implement `get_tool_definitions()`
4. Write `prompt.md` for AI agent guidance
5. Restart pyWinBots – your plugin is auto-discovered

## Architecture

```
┌─────────────┐  MCP Streamable HTTP   ┌──────────────────────┐
│  AI Agent   │ ◄──────────────────────►│    pyWinBots         │
│  (MCP Client)│   /mcp                 │                       │
└─────────────┘                         │  ┌─────────────────┐  │
                                        │  │  MCP Server      │  │
                                        │  │  (FastMCP)       │  │
                                        │  └────────┬────────┘  │
                                        │           │           │
                                        │  ┌────────▼────────┐  │
                                        │  │  Plugin Manager  │  │
                                        │  │  (AppManager)    │  │
                                        │  └──┬────┬────┬────┘  │
                                        │  ┌──▼┐ ┌▼──┐ ┌▼──┐   │
                                        │  │App│ │App│ │App│   │
                                        │  │Tool│ │Tool│ │Tool│   │
                                        │  └──┬┘ └┬──┘ └┬──┘   │
                                        │     │    │     │       │
                                        │  ┌──▼────▼─────▼──┐   │
                                        │  │  Automation     │   │
                                        │  │  (UI/Window/App)│   │
                                        │  └────────┬───────┘   │
                                        │           │           │
                                        │  ┌────────▼───────┐   │
                                        │  │  Base           │   │
                                        │  │  (KB/Mouse/Log) │   │
                                        │  └────────────────┘   │
                                        └───────────────────────┘
```

## Locations

Each plugin's `manifest.json` can include a `locations` record that maps
named UI element offsets (relative to the main window top-left) to `[x, y]`
pixel coordinates. Plugins read these at startup to locate buttons, inputs,
and other controls.

```json
{
  "locations": {
    "searchbox_offset": [320, 100],
    "messageinput_offset": [810, 1376],
    "custom_button": [100, 500]
  }
}
```

| Key | Value | Description |
|-----|-------|-------------|
| Any name | `[x, y]` | Pixel offset from the app's main window top-left corner |

Plugins access these via `manifest["locations"]["<key>"]` during
`initialize()`. You can add or change entries through the Web UI config
editor — no code changes required.

## Logging

- **Dual output**: console (stdout) + file
- **File location**: `~/.pywinbots/logs/pywinbots_{YYYYMMDD}_{HHMMSS}.log`
- **Format**: `2026-07-06 00:21:04.108 [INFO   ] pyWinBots: message`
- **Level**: `--log-level DEBUG|INFO|WARNING|ERROR` (default: `INFO`)
- **Web UI** has a live log viewer with auto-refresh and level highlighting

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `PYWINBOTS_LOG_DIR` | `~/.pywinbots/logs/` | Log directory |
| `PYWINBOTS_PORT` | `8000` | MCP server port |

## License

MIT
