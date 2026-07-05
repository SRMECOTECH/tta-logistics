# CLAUDE HANDOFF — TTA Analytics Platform

> **Audience:** a fresh Claude (or developer) session with zero prior context.
> **Read this fully before touching code.** Section 1–5 = what exists and why.
> Section 6 = **the task you must now execute** (client-driven API productization).
> Section 7 = definition of done. Section 8 = gotchas that will bite you if skipped.

---

## 1. What this project is

A **client-demo prototype** built to win a logistics-analytics project. The data
(`data/TTA.xlsx`) is one month (June 2026) of outbound road-logistics trips from a
steel plant in Jamshedpur, India: 6,299 trips, 48 transporters, 161 destinations —
transit times, ETAs/ATAs, detention, distances, GPS telemetry, speed violations,
on-time-delivery status.

It is a working prototype, not production software. Priorities, in order:
**visual/demo impact → correctness → clean API contract → depth**. The end audience
of the UI is non-technical (every chart carries a plain-English explanation — keep
that convention for anything you add).

## 2. Architecture (all working, all tested)

```
data/TTA.xlsx ──ETL──▶ SQLite data/tta.db (auto-created on first backend start)
                              │
                    backend/analytics.py  ← single aggregation engine (pandas)
                       │              │
        FastAPI :8000 /api/*     MCP server :8010 /mcp (13 tta_* tools)
               │                      │
      Streamlit UI :8501       external AI agents / apps
               │
     backend/ai.py — LangChain → Azure OpenAI (LIVE) / OpenAI / HuggingFace
```

- **Run everything:** `run.bat` (→ `run.py`) starts backend :8000, MCP :8010, UI :8501.
- **Standalone:** first backend start creates all tables and imports the Excel via
  `backend/etl.py`. After that the Excel is only needed for re-import
  (Settings → Data in the UI, or `POST /api/data/reload`).
- Python venv: `.venv\Scripts\python.exe` (Windows). Deps: `requirements.txt`.

### File map

| Path | Purpose |
|---|---|
| `backend/config.py` | paths, `.env` loading, `DEFAULT_SETTINGS`, `SECRET_KEYS` |
| `backend/database.py`, `models.py` | SQLAlchemy engine + `trips`, `app_settings` tables |
| `backend/etl.py` | Excel → clean → derive → SQLite (duration parsing, geo, calendar cols) |
| `backend/geo.py` | offline geocoder: ~160 Indian city coords + pincode-prefix fallback |
| `backend/analytics.py` | ALL aggregations (KPIs+deltas, timeseries, group summaries, heatmaps, correlation, distribution, per-lane z-score outliers, funnel, geo) |
| `backend/settings_store.py` | get/save/seed settings (see gotcha 8.1) |
| `backend/ai.py` | LangChain provider factory + insight prompt; custom `HuggingFaceChat` |
| `backend/main.py` | FastAPI app, all endpoints, lifespan auto-ETL |
| `mcp_server/server.py` | FastMCP `tta_analytics_mcp`, 13 read-only tools; stdio + streamable HTTP |
| `mcp_server/evaluation.xml` | 10 verified Q&A pairs for MCP eval |
| `frontend/Home.py` + `frontend/pages/1..11_*.py` | Streamlit UI (11 pages) |
| `frontend/lib/api.py` | REST client (`BASE_URL` = `TTA_API_URL` env or `http://127.0.0.1:8000`) |
| `frontend/lib/ui.py` | shared: filters sidebar, KPI cards, plotly theme (`style_fig`), `explain()` / `page_intro()` business-note components |
| `tests/smoke_api.py`, `smoke_pages.py`, `smoke_mcp.py` | run after ANY change (see §7) |

## 3. What has been delivered so far (chronological)

1. **Full platform**: ETL + SQLite + FastAPI (17 endpoints) + Streamlit (11 pages:
   Executive Overview, Trends, Transporters, Routes/Lanes, Geo Map (pydeck arcs),
   Heatmaps, Fleet, Distributions/Outliers, Data Explorer, AI Studio, Settings,
   Integrations) + LangChain AI layer with per-page "Generate AI insights" buttons.
2. **AI providers switchable from Settings UI**: Azure OpenAI / OpenAI / HuggingFace
   free tier. **Azure is LIVE** — key in `.env`, provider set to `azure_openai` in DB,
   verified end-to-end (gpt-4.1 deployment, ~2.5s round trip).
3. **MCP server** so other apps/agents consume the analytics (13 tools, both
   transports, guarded read-only SQL tool, eval file). Tested with a real MCP client.
4. **Business annotations**: every chart has `ui.explain(what, takeaway)` under it and
   every page has `ui.page_intro(...)` — written for non-technical readers, no label
   prefixes ("What this shows:" text was explicitly removed by user request).
5. **Chart layout fixes**: `ui.style_fig()` pins titles top-left with big top margin,
   horizontal legends below the title for regular charts, vertical right-side legends
   for pies; never set a layout title position when the fig has no title (renders
   literal "undefined").

## 4. The data (so numbers you see make sense)

- June 2026 only; all trips originate JAMSHEDPUR; `Trip Status` is always "Close".
- Headline (unfiltered): OTD 88.5%, avg transit 80.4h, 5.23M km total,
  647 late deliveries, avg 264.7 speed alerts/trip (alerts are event counts — large).
- Known data quirks worth mentioning to the client, not "fixing":
  duplicate transporter spellings ("Utility Transport Company" ≠ "UTILITY TRANSPORT
  COMPANY" — 65.1% vs 39.1% OTD); ~10% of trips have no ATA (never tracked to arrival);
  `speed_violations` sums to 1.67M events.
- Trip-level derived columns (see `models.py`): `transit_hours`,
  `planned_transit_hours` (ETA−departure), `schedule_variance` = actual−planned,
  `delivery_delta_hours` (negative = early), `dispatch_lead_hours`, `avg_speed_kmph`
  (capped at settings `speed_cap_kmph`, default 110), `is_on_time`, `dest_lat/lon`,
  calendar keys `dept_date/hour/dow/month/week`.

## 5. The client requirement that drives YOUR task

Client's words (Hinglish): *"nahi main api se services access karna chahta hu..
swagger se test karke. api jarur expose kar dijiyega.. fir main mcp me add kar lunga."*

Decoded — and this framing was agreed with the user:

1. **The REST API is the product** — not the UI, not our MCP server. The client has
   their own AI/agent stack and MCP infrastructure; they want a clean, documented
   data service they control. Sophisticated buyer avoiding lock-in.
2. **Swagger (`/docs`) is the sales demo.** Their technical team will evaluate by
   opening the docs page and firing requests. Endpoint names, parameter descriptions
   and response examples ARE the first impression.
3. **They'll wrap our OpenAPI into MCP themselves** — most MCP gateways (incl.
   FastMCP) auto-generate tools from an OpenAPI spec, so `openapi.json` is the
   handover artifact. Good FastAPI docstrings become good MCP tool descriptions
   on their side automatically.
4. **Architecture already fits** — backend is decoupled; UI and our MCP server are
   just consumers. Our MCP server stays in the pitch as a bonus ("if you don't want
   to build the wrapper, ours ships ready").

## 6. YOUR TASK — API productization pass (~1 focused session, no re-architecture)

Make `http://127.0.0.1:8000/docs` client-presentable and integration-ready:

### 6.1 OpenAPI polish (the bulk of the work)
- Group endpoints with **tags**: `Meta`, `KPIs`, `Time Series`, `Rankings`,
  `Geo`, `Heatmaps`, `Statistics`, `Records`, `AI`, `Settings`, `Data Management`.
- Every endpoint gets `summary=` (one line) and `description=` (2–4 sentences:
  what it computes, business meaning, example use). Write for the client's
  integration engineer.
- Document every query parameter with `Query(..., description=...)` — especially
  the shared filters: `date_from`/`date_to` (ISO dates), and the multi-value params
  `transporters`, `destinations`, `vehicle_categories`, `own_market`, `consignors`
  which are **`||`-separated strings** (e.g. `transporters=Hind Transport||AKR LOGISTICS`).
  State that valid values come from `/api/v1/meta`.
- Add response examples (via `responses={200: {"content": {"application/json":
  {"example": ...}}}}` or Pydantic `response_model` with `model_config`
  `json_schema_extra`) for at least: kpis, timeseries, group, geo, outliers.
  Real-looking examples — pull realistic values from §4.
- App-level metadata: `title="TTA Logistics Analytics API"`, `version="1.0.0"`,
  `description` (markdown overview: what the dataset is, auth, filters convention,
  link to `/api/v1/openapi.json`), `contact`, tag descriptions via `openapi_tags`.

### 6.2 API-key auth
- `X-API-Key` header via a FastAPI dependency; declare it in OpenAPI as an
  `APIKeyHeader` security scheme so Swagger shows the **Authorize** button.
- Key stored in settings (`settings_store`), key name `api_key`; default comes from
  env `TTA_API_KEY`; if neither is set, **generate one at startup** and log it once.
- Exempt: `/health`, `/docs`, `/openapi.json`, `/redoc`.
- Update `frontend/lib/api.py` to send the header (read `TTA_API_KEY` env, fall back
  to the same default logic — simplest: also expose the key read-only on the
  Settings page so the user can copy it for the client).
- `401` response must be a helpful JSON: `{"detail": "Missing or invalid X-API-Key
  header. Get the key from the platform owner."}`.

### 6.3 Versioned base path
- Canonical prefix becomes **`/api/v1/...`**. Keep the existing `/api/...` paths
  working as deprecated aliases (mount the same router twice or add redirects) so
  nothing breaks mid-demo.
- Update `frontend/lib/api.py` to call `/api/v1/...`, and update the code snippets
  on `frontend/pages/11_Integrations.py` (they show `/api/...` URLs and a curl-less
  Python example) plus `README.md`.

### 6.4 Reachability note (documentation only, no infra work)
Add a short "Sharing the API with a client" section to `README.md`: run backend with
`--host 0.0.0.0`, or tunnel (`ssh -R` / cloudflared / ngrok), hand over
`https://<host>/docs` + the API key + `openapi.json` URL. Do NOT deploy anything.

## 7. Definition of done — run these, all must pass

Backend running (`.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000`):

1. `.venv\Scripts\python.exe tests\smoke_api.py` — update it for `/api/v1` + API key
   as part of the task; legacy `/api/*` aliases should also still answer.
2. `.venv\Scripts\python.exe tests\smoke_pages.py` — all 12 Streamlit pages pass
   (needs the backend; pages call the API through `frontend/lib/api.py`).
3. MCP server up (`-m mcp_server --http --port 8010`) →
   `.venv\Scripts\python.exe tests\smoke_mcp.py` (MCP calls analytics directly, not
   REST — it should be untouched by your changes; this test proves it).
4. Manual: open `/docs` — endpoints grouped under tags, Authorize button present,
   a request without the key returns the helpful 401, with the key returns data.
5. Report results honestly, including anything skipped.

## 8. Gotchas — read before coding

1. **Settings precedence** (`backend/settings_store.py`): DB value wins UNLESS it is
   empty and the `.env` default is non-empty. This exists because the Azure key was
   pasted into `.env` AFTER the DB was seeded with an empty value. Don't "simplify" it.
2. **Secrets**: `.env` contains a real Azure OpenAI key. Never print, commit, or echo
   it. `GET /api/settings` masks secrets; `PUT` uses sentinel `"__keep__"` to leave a
   masked secret unchanged. `SECRET_KEYS` lives in `backend/config.py` — if you add
   `api_key` to settings, decide deliberately whether it belongs there (recommended:
   yes for GET masking, but the Settings page then needs a way to reveal/copy it).
3. **The user often has the app running** (`run.bat`: ports 8000/8010/8501). Check
   `Get-NetTCPConnection -LocalPort <p> -State Listen` before starting servers; do
   NOT kill processes you didn't start — ask or use another port (8502 pattern for a
   second Streamlit; there's a `frontend-check` recipe in git history of
   `.claude/launch.json`).
4. **Streamlit caches imported modules** — after editing `frontend/lib/*`, a running
   Streamlit serves stale code; the user must restart it (tell them explicitly).
5. **Filter param convention**: multi-select filters travel as `||`-joined query
   strings (chosen because transporter names contain commas/ampersands). The
   frontend builds them in `ui.sidebar_filters()`. Keep it consistent in v1 docs.
6. **`ui.style_fig`**: never set layout-title positioning on figures without a title
   (plotly renders the string "undefined"); pies get right-side vertical legends.
7. **Windows/PowerShell 5.1**: no `&&`; venv python is `.venv\Scripts\python.exe`;
   `Invoke-RestMethod` mangles bullet chars in masked secrets — cosmetic only.
8. **Do not rename existing analytics fields** in responses — the Streamlit pages
   and the client's future integrations key on them (`otd_pct`, `avg_transit_hours`,
   `schedule_variance_hours`, `violations_per_trip`, …). Additive changes only.
9. **Every new chart** must ship with `ui.explain(what, takeaway)` — plain English,
   decision-oriented, no stats jargon, no "What this shows:" label prefixes.
10. **AI provider errors** must stay graceful: numeric endpoints/tools never depend
    on the LLM; AI failures return a clear message pointing to Settings.

## 9. Context for the pitch (why quality here matters)

The demo script sells: Executive Overview → Geo arc map (the wow shot) →
Outliers slider (real finding: trip 28175710, 500h vs 109h lane average, z=10.5) →
AI Studio live insight → Settings (upload new Excel, re-import in seconds) →
**and now `/docs` as the "integrate with anything" closer.** Your task makes that
last beat land with a technical buyer who will judge the whole engagement by it.
