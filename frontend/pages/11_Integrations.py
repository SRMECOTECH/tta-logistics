"""Integrations — how external applications consume this platform
(REST API + MCP server), with live status checks."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import requests
import streamlit as st

from lib import api, ui

ui.setup_page("Integrations — API & MCP", "🔌")

st.markdown(
    "Every number in this app is computed once and exposed **three ways**, so any external "
    "application or AI agent can reuse it:\n"
    "1. **REST API** (FastAPI) — for dashboards, ERPs, custom apps\n"
    "2. **MCP server** (Model Context Protocol) — for AI agents like Claude, or any MCP client\n"
    "3. **This Streamlit UI** — for humans\n\n"
    "📖 **Full REST guide** (every endpoint, real examples, chart→endpoint map, AI-insight "
    "pattern): `docs/API_GUIDE.md` in the project. Hand it to the client's integration engineer "
    "alongside the Swagger link, API key and `openapi.json`."
)

# ------------------------------------------------------------- live status --
c1, c2 = st.columns(2)
with c1:
    st.subheader("🌐 REST API — port 8000")
    try:
        h = requests.get("http://127.0.0.1:8000/health", timeout=3).json()
        st.success(f"Online — {h['rows']:,} trips served")
    except Exception:
        st.error("Offline (start with run.bat)")
    st.markdown(
        "- Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) — "
        "click **Authorize** and paste the API key (Settings → 🔑 API access)\n"
        "- OpenAPI spec (import into Postman / auto-wrap as MCP tools): "
        "[/api/v1/openapi.json](http://127.0.0.1:8000/api/v1/openapi.json)\n"
        "- Base path: `/api/v1/…`, auth via `X-API-Key` header"
    )
    st.code(
        'import requests\n'
        'kpis = requests.get("http://127.0.0.1:8000/api/v1/kpis",\n'
        '                    headers={"X-API-Key": "<your-key>"},\n'
        '                    params={"transporters": "Hind Transport"}).json()\n'
        'print(kpis["current"]["otd_pct"])',
        language="python",
    )
with c2:
    st.subheader("🧩 MCP server — port 8010")
    try:
        # POST without a session yields a JSON-RPC error response — proves it's alive
        r = requests.post("http://127.0.0.1:8010/mcp", json={}, timeout=3,
                          headers={"Accept": "application/json, text/event-stream",
                                   "Content-Type": "application/json"})
        st.success(f"Online — endpoint responding (HTTP {r.status_code})")
    except Exception:
        st.error("Offline (start with run.bat)")
    st.markdown("- Endpoint: `http://127.0.0.1:8010/mcp` (streamable HTTP, stateless)")
    st.caption("51 read-only tools: 13 generic (overview, KPIs, timeseries, rankings, geo, "
               "heatmaps, correlation, distributions, outliers, fleet, trip records, safe SQL, "
               "AI insight) + 38 per-figure tools, one for every dashboard chart/map/table.")

st.divider()

# ------------------------------------------------------ connection recipes --
st.subheader("🔗 Connect your client")
tab1, tab2, tab3, tab4 = st.tabs(["Claude Desktop", "Claude Code", "Python agent", "Any MCP client"])
with tab1:
    st.caption("Add to claude_desktop_config.json (Settings → Developer → Edit Config):")
    st.code(
        '{\n'
        '  "mcpServers": {\n'
        '    "tta-analytics": {\n'
        '      "command": "C:\\\\Users\\\\Sanjoy Chattopadhyay\\\\PycharmProjects\\\\TTA_Analysis\\\\.venv\\\\Scripts\\\\python.exe",\n'
        '      "args": ["-m", "mcp_server"],\n'
        '      "cwd": "C:\\\\Users\\\\Sanjoy Chattopadhyay\\\\PycharmProjects\\\\TTA_Analysis"\n'
        '    }\n'
        '  }\n'
        '}',
        language="json",
    )
with tab2:
    st.code('claude mcp add --transport http tta-analytics http://127.0.0.1:8010/mcp', language="bash")
with tab3:
    st.code(
        'import asyncio\n'
        'from mcp import ClientSession\n'
        'from mcp.client.streamable_http import streamablehttp_client\n\n'
        'async def main():\n'
        '    async with streamablehttp_client("http://127.0.0.1:8010/mcp") as (r, w, _):\n'
        '        async with ClientSession(r, w) as s:\n'
        '            await s.initialize()\n'
        '            res = await s.call_tool("tta_group_summary", {"by": "transporter"})\n'
        '            print(res.content[0].text)\n\n'
        'asyncio.run(main())',
        language="python",
    )
with tab4:
    st.markdown(
        "- **Transport**: streamable HTTP (stateless JSON) at `http://127.0.0.1:8010/mcp`, "
        "or stdio via `python -m mcp_server`\n"
        "- **Inspector**: `npx @modelcontextprotocol/inspector` → connect to the URL above\n"
        "- Deploy behind any reverse proxy to share with other teams/apps"
    )

st.divider()

# ------------------------------------------------------------- tool catalog --
st.subheader("🛠️ MCP tool catalog (51 tools)")
st.markdown("**13 generic tools** — flexible, parameterised:")
st.markdown("""
| Tool | Purpose |
|---|---|
| `tta_dataset_overview` | Entry point — data range, valid filter values, headline KPIs |
| `tta_get_kpis` | Full KPI block for any filtered slice, with prior-period deltas |
| `tta_get_timeseries` | Daily/weekly/monthly trends |
| `tta_group_summary` | Rankings by transporter / destination / vehicle / own-market / consignor |
| `tta_get_geo_points` | Destination lat/lon + performance (map-ready) |
| `tta_get_heatmap` | Weekday×hour rhythm or custom pivot matrices |
| `tta_get_correlation` | Metric correlation matrix |
| `tta_get_distribution` | Stats + histogram for any numeric metric |
| `tta_get_outliers` | Per-lane z-score anomalous trips |
| `tta_get_fleet_summary` | Fleet mix, GPS compliance, top violators |
| `tta_get_trips` | Paginated raw records with search |
| `tta_sql_query` | Read-only SELECT escape hatch (guarded) |
| `tta_ai_insight` | LangChain narrative insight via the configured LLM |
""")
st.markdown("**+ 38 per-figure tools** — one for every dashboard chart/map/table, e.g. "
            "`tta_kpi_summary`, `tta_otd_vs_target`, `tta_delivery_status_split`, "
            "`tta_top_destinations`, `tta_transporter_best_worst_otd`, `tta_transporter_risk_map`, "
            "`tta_distance_vs_transit`, `tta_slowest_corridors`, `tta_schedule_variance_lanes`, "
            "`tta_lane_volume_treemap`, `tta_departure_rhythm`, `tta_transporter_month_heatmap`, "
            "`tta_metric_boxplot_by_group`, `tta_own_vs_market`, `tta_top_violating_vehicles`, "
            "`tta_gps_uptime_distribution`, … Each mirrors a `/api/v1/figures/*` endpoint. "
            "Full list: `docs/API_GUIDE.md`.")
