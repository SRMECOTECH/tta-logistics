# TTA MCP Client — separate app that consumes the analytics over MCP

A **standalone application on its own port (8020)** that reads the TTA logistics
analytics **only through the MCP server** at `http://127.0.0.1:8010/mcp` — it never
touches the database, the Excel or the REST API. It's the live demonstration that an
external app or AI agent can integrate with this platform through MCP alone.

## What it does
- Connects to the MCP server, shows connection status and the full **tool catalog** (51 tools: 13 generic + 38 per-figure).
- **Quick-action buttons** (Dataset overview, Top transporters, Worst lanes, Outliers, AI insight) — one click = one MCP tool call, rendered as an app would (KPI cards, tables, charts, markdown).
- A **"Call any tool"** panel: pick any tool, pass JSON arguments, see the raw MCP response.

## Run it

Prerequisite: the MCP server must be running —
`.venv\Scripts\python.exe -m mcp_server --http --port 8010` (or just `run.bat`, which now
starts this app too).

Standalone:
```bat
.venv\Scripts\python.exe -m streamlit run mcp_client_app/app.py --server.port 8020
```
Then open **http://localhost:8020**.

## Files
- `client.py` — Streamlit-free sync wrapper over the MCP streamable-HTTP client (`list_tools`, `call_tool`, `ping`). Unit-testable on its own.
- `app.py` — the Streamlit UI.

## Ports cheat-sheet
| Port | Service |
|---|---|
| 8000 | REST API + Swagger `/docs` |
| 8010 | MCP server (this app's data source) |
| 8501 | Main dashboard |
| 8020 | **This** MCP client app |

> **Note:** opening `http://127.0.0.1:8010/mcp` in a browser returns
> `"Not Acceptable: Client must accept text/event-stream"`. That is expected — the MCP
> endpoint speaks JSON-RPC/streaming, not HTML. Only an MCP client (like this app) can
> talk to it. Swagger is on **8000**, not 8010.
