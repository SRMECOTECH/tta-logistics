# TTA Master Reporting & AI Analytics Platform

A standalone client-demo platform for **Transit Time Analysis (TTA)** of outbound road
logistics: FastAPI analytics backend + Streamlit dashboard frontend + LangChain AI layer
+ **MCP server** so other applications and AI agents can consume the same analytics.

- **Fully standalone** — on first run it creates a SQLite database (`data/tta.db`), builds
  all tables, and imports `data/TTA.xlsx` through a cleaning/feature-engineering ETL.
  After that the Excel is no longer needed (re-import / upload anytime from the UI).
- **AI everywhere** — every page has a "✨ Generate AI insights" button. The computed
  aggregates shown on screen are sent through a LangChain pipeline
  (`ChatPromptTemplate → chat model → StrOutputParser`) to whichever provider is active.
- **Provider switchable from the UI** (Settings page): Hugging Face free tier,
  Azure OpenAI, or standard OpenAI — paste the key, hit *Test connection*, done.

## Quick start

> 🎤 **Presenting this to a client?** See
> **[`docs/PRESENTATION_GUIDE.md`](docs/PRESENTATION_GUIDE.md)** — what the data is, how
> the app works, and a page-by-page tour of every map and figure with the exact data
> behind it, plus a 5-minute demo script.

```bat
run.bat
```

(or `python run.py` with the venv active). Starts all three services:

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| REST API (FastAPI) | http://127.0.0.1:8000/docs |
| MCP server (streamable HTTP) | http://127.0.0.1:8010/mcp |

## REST API (v1)

The canonical contract is **`/api/v1/…`** (the old `/api/…` paths still answer as
hidden compatibility aliases). Interactive docs at `/docs`, machine-readable spec at
`/api/v1/openapi.json` — import it into Postman or auto-wrap the endpoints as MCP
tools (e.g. FastMCP `from_openapi`).

📖 **Full integration guide with real request/response examples for every endpoint:
[`docs/API_GUIDE.md`](docs/API_GUIDE.md)** — includes the dashboard-chart ↔ endpoint
map (every visual is exposed) and the AI-insight usage pattern.

- **Auth:** every `/api/v1` endpoint requires an **`X-API-Key`** header
  (`/health`, `/docs` and the spec are open). The key comes from the `TTA_API_KEY`
  env var; if unset, the backend generates one on first start, logs it once, and
  shows it on **Settings → 🔑 API access** in the UI.
- **Filters:** all analytics endpoints share `date_from`/`date_to` (ISO dates) and
  the multi-value params `transporters`, `destinations`, `vehicle_categories`,
  `own_market`, `consignors` as **`||`-separated strings**
  (e.g. `transporters=Hind Transport||AKR LOGISTICS`). Valid values: `GET /api/v1/meta`.

```python
import requests
kpis = requests.get("http://127.0.0.1:8000/api/v1/kpis",
                    headers={"X-API-Key": "<your-key>"},
                    params={"transporters": "Hind Transport"}).json()
print(kpis["current"]["otd_pct"])
```

### Sharing the API with a client

The client can't Swagger-test `localhost` on your laptop. For a demo session:

1. Run the backend on all interfaces:
   `python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000`
   (same LAN → hand them `http://<your-ip>:8000/docs`), **or**
2. Tunnel it out: `cloudflared tunnel --url http://127.0.0.1:8000`,
   `ngrok http 8000`, or `ssh -R` to a VM you control.

Then hand over three things: the `https://<host>/docs` URL, the API key
(Settings → 🔑 API access), and the `https://<host>/api/v1/openapi.json` URL —
that spec is the integration artifact their MCP gateway consumes directly.

## Pages

| Page | What it shows |
|---|---|
| 🏭 Executive Overview | KPI cards with period-over-period deltas, volume trend, OTD gauge vs target, delivery split, top destinations, transporter share, trip lifecycle funnel |
| 📈 Time & Trends | Daily/weekly/monthly volumes, OTD trend vs target, transit & detention trends, dispatch lead time, distance, violations |
| 🚚 Transporter Scorecard | League table with progress bars, best/worst OTD rankings, risk bubble map, head-to-head radar, transit box plots |
| 🛣️ Routes & Lanes | Lane table, distance-vs-transit regression, slowest corridors, schedule variance (behind/ahead of plan), volume treemap |
| 🗺️ Geo Intelligence | pydeck India map — flow arcs from Jamshedpur, volume bubbles colored by OTD/transit, density heatmap (offline geocoder, no API) |
| 🔥 Heatmaps | Weekday×hour departure rhythm, transporter×month & destination×month heatmaps, full correlation matrix |
| 🚛 Fleet & Vehicles | Own vs market comparison, vehicle categories, GPS device types, top violators, low-GPS-uptime vehicles |
| 📊 Distributions & Outliers | Histogram/violin/ECDF for any metric, grouped box plots, per-lane z-score anomaly detection with CSV export |
| 🔎 Data Explorer | Filtered raw trips with search + CSV export |
| 🤖 AI Insights Studio | One-click analysis packs (executive summary, transporter deep-dive, lane deep-dive, fleet review, risk report) + free-form questions |
| ⚙️ Settings | AI provider + keys, temperature/tokens, OTD target, outlier sensitivity, speed cap, re-import / upload Excel |

## Architecture

```
data/TTA.xlsx ──ETL──▶ SQLite (auto-created) ──▶ backend/analytics.py (single engine)
                                                   │                │
                                       FastAPI /api/*        MCP tta_* tools (:8010/mcp)
                                                   │                │
                                            Streamlit UI      Claude / agents / other apps
                                                   │
                                   LangChain (Azure OpenAI / OpenAI / HF)
```

## MCP server (integrations)

`mcp_server/server.py` exposes **51 read-only tools** — 13 generic
(`tta_dataset_overview`, `tta_get_kpis`, `tta_group_summary`, `tta_sql_query`,
`tta_ai_insight`, …) plus **38 per-figure tools** (`tta_kpi_summary`, `tta_otd_trend`,
`tta_distance_vs_transit`, `tta_departure_rhythm`, …), one for every dashboard visual,
each mirroring a `/api/v1/figures/*` REST endpoint — over both transports:

```bash
python -m mcp_server                    # stdio — for Claude Desktop
python -m mcp_server --http --port 8010 # streamable HTTP — for remote apps/agents
```

Connect Claude Code: `claude mcp add --transport http tta-analytics http://127.0.0.1:8010/mcp`
Full connection recipes (Claude Desktop config, Python client, Inspector) are on the
**🔌 Integrations** page inside the app. Evaluation set: `mcp_server/evaluation.xml`.

- `backend/etl.py` — parses `dd-mm-yyyy` timestamps, "5 Days 23:51" durations,
  "Before By / Delay By" delivery deltas; derives transit vs plan, effective speed,
  dispatch lead time, calendar features and lat/lon per destination.
- `backend/analytics.py` — all aggregations (KPIs + deltas, timeseries, group summaries,
  heatmap pivots, correlation, distributions, z-score outliers, funnel, geo).
- `backend/ai.py` — LangChain provider factory; Hugging Face runs through a custom
  LangChain `BaseChatModel` over the free serverless Inference API (no torch install).
- `frontend/lib/ui.py` — shared filters, KPI cards, plotly theme, AI insight block.

## AI keys

| Provider | Where to get a key | Notes |
|---|---|---|
| GLM / Zhipu | z.ai → sign up → API Keys | **Free** models `glm-4.5-flash` / `glm-4.7-flash`; `glm-4.6` / `glm-5.2` paid but cheap. OpenAI-compatible |
| Hugging Face | huggingface.co → Settings → Access Tokens | Free tier, works today |
| Azure OpenAI | your Azure portal | endpoint/deployment pre-filled in `.env` |
| OpenAI | platform.openai.com | any chat model |

GLM env overrides (optional): `GLM_API_KEY`, `GLM_MODEL` (default `glm-4.5-flash`),
`GLM_BASE_URL` (default `https://api.z.ai/api/paas/v4/`; use
`https://open.bigmodel.cn/api/paas/v4/` for mainland China).

Keys can be pasted in the **Settings page** (stored in local SQLite) or in `.env`.
