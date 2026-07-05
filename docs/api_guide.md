# TTA Logistics Analytics API — Integration Guide

**Version 1.0.0** · Base path `/api/v1` · Interactive docs at `/docs` · Spec at `/api/v1/openapi.json`

This guide is written for the engineer who will consume the API — from a dashboard,
an ERP, or by auto-wrapping the OpenAPI spec into MCP tools. Every number and every
chart in the TTA dashboard is computed **once** on the backend and exposed here, so
anything you can see in the UI you can pull over HTTP.

The dataset behind the demo is one month (**June 2026**) of outbound road-logistics
trips from a steel plant in **Jamshedpur, India**: 6,299 trips, 48 transporters,
161 destinations, with transit times vs plan, on-time delivery, detention, dispatch
lead times, distances, GPS telemetry and speed-violation events.

---

## 1. Conventions

### Base URL & versioning
- Canonical, stable contract: **`/api/v1/…`**
- The old unversioned `/api/…` paths still answer as **deprecated aliases** (so nothing breaks mid-migration), but build against `/api/v1`.
- Machine-readable spec: **`GET /api/v1/openapi.json`** — import into Postman, generate a typed client, or feed to an MCP gateway.

For a shared demo, the host is a tunnel or LAN address instead of localhost, e.g.
`https://tta.example.com`. Everything below is relative to `<BASE>` (locally
`http://127.0.0.1:8000`).

### Authentication
Every `/api/v1/*` endpoint requires an **`X-API-Key`** request header.

```
X-API-Key: tta_xxxxxxxxxxxxxxxxxxxxxxxx
```

- Get the key from the platform owner (it is shown on **Settings → 🔑 API access** in the dashboard, or pinned via the `TTA_API_KEY` environment variable).
- In Swagger (`/docs`): click **Authorize**, paste the key, done.
- **Open (no key):** `GET /health`, `/docs`, `/redoc`, `/api/v1/openapi.json`.
- Missing/invalid key → `401` with a helpful body:
  ```json
  { "detail": "Missing or invalid X-API-Key header. Get the key from the platform owner." }
  ```

### Filters (shared by every analytics endpoint)
All analytics endpoints accept the same optional filter query params. Omit them for
the full dataset; combine any of them to narrow the slice.

| Param | Type | Meaning |
|---|---|---|
| `date_from` | ISO date | Trips departing on/after this date, e.g. `2026-06-01` |
| `date_to` | ISO date | Trips departing on/before this date (inclusive), e.g. `2026-06-30` |
| `transporters` | `\|\|`-list | Transporter names, e.g. `Hind Transport\|\|AKR LOGISTICS` |
| `destinations` | `\|\|`-list | Destination cities, e.g. `RANCHI\|\|JAIPUR` |
| `vehicle_categories` | `\|\|`-list | e.g. `HEAVY VEHICLE\|\|LIGHT VEHICLE` |
| `own_market` | `\|\|`-list | `Own` and/or `Market` |
| `consignors` | `\|\|`-list | Consignor names, e.g. `TATA STEEL - HSM` |

> **Why `||`?** Transporter and consignee names contain commas and ampersands, so
> multi-value params are joined with a double-pipe `||`, not a comma. URL-encode it
> as `%7C%7C` if your client doesn't do it for you.

**Always call `GET /api/v1/meta` first** — it returns the exact valid values for every
one of these filters, plus the date range, so you can populate dropdowns or validate input.

### Response format
JSON everywhere. Floats are rounded (usually 2 dp); missing values are JSON `null`;
timestamps in record endpoints are `YYYY-MM-DD HH:MM` strings. Note `speed_violations`
counts telemetry **events**, not trips, so its totals are large (millions).

---

## 2. Endpoint reference

21 endpoints, grouped as they appear in Swagger. `GET` unless noted.

| Tag | Method & path | What it gives you |
|---|---|---|
| Meta | `GET /health` | Liveness + row count (no auth) |
| Meta | `GET /api/v1/meta` | Date range + valid filter values + last-import summary |
| KPIs | `GET /api/v1/kpis` | Headline metric block + period-over-period deltas |
| KPIs | `GET /api/v1/funnel` | Trip lifecycle stage counts |
| Time Series | `GET /api/v1/timeseries` | Daily/weekly/monthly trend rows |
| Rankings | `GET /api/v1/group` | League table by any grouping field |
| Rankings | `GET /api/v1/fleet` | Fleet mix, GPS compliance, top violators |
| Geo | `GET /api/v1/geo` | Origin + per-destination points w/ performance |
| Heatmaps | `GET /api/v1/heatmap/dow_hour` | 7×24 weekday×hour departure matrix |
| Heatmaps | `GET /api/v1/heatmap/pivot` | Custom top-N pivot matrix |
| Statistics | `GET /api/v1/correlation` | Metric correlation matrix |
| Statistics | `GET /api/v1/distribution` | Stats + sampled values for one metric |
| Statistics | `GET /api/v1/boxdata` | Box-plot samples per group |
| Statistics | `GET /api/v1/outliers` | Per-lane z-score anomalous trips |
| Records | `GET /api/v1/records` | Trip-level raw rows |
| AI | `POST /api/v1/ai/insight` | LLM narrative over any data you pass |
| AI | `POST /api/v1/ai/test` | Ping the configured AI provider |
| Settings | `GET /api/v1/settings` | Runtime settings (secrets masked) |
| Settings | `PUT /api/v1/settings` | Update settings |
| Data Management | `POST /api/v1/data/reload` | Re-run ETL from the source Excel |
| Data Management | `POST /api/v1/data/upload` | Upload a new Excel + import it |

Everything below assumes the header `X-API-Key: <key>` is sent.

---

### Meta

#### `GET /health`  *(no auth)*
```json
{ "status": "ok", "rows": 6299 }
```

#### `GET /api/v1/meta`
The dictionary for the whole dataset. Call it first.
```json
{
  "rows": 6299,
  "date_min": "2026-06-01",
  "date_max": "2026-06-30",
  "transporters": ["AKR LOGISTICS", "ASHMI LOGISTICS", "..."],
  "destinations": ["TIRUNINRAVUR", "JAIPUR", "PATNA CITY", "..."],
  "vehicle_categories": ["HEAVY VEHICLE", "LIGHT VEHICLE", "SPEC/OTHER"],
  "consignors": ["TATA STEEL - HSM", "TATA STEEL- BARA", "..."],
  "own_market": ["Market", "Own"],
  "last_import": { "rows_imported": 6299, "geo_mapped_pct": 100.0, "imported_at": "2026-07-04T23:02:51" }
}
```

---

### KPIs

#### `GET /api/v1/kpis`  ·  filters
Executive metric block for the slice, plus `previous` (the immediately preceding
window of equal length) and `delta_pct` (% change per metric). `previous`/`delta_pct`
are empty when there is no earlier data (the demo is June-2026 only, so an unfiltered
call has no prior window).
```json
{
  "current": {
    "trips": 6299, "transporters": 48, "vehicles": 3500, "destinations": 161,
    "total_km": 5230456.0, "avg_km_per_trip": 928.4, "otd_pct": 88.5,
    "avg_transit_hours": 80.4, "median_transit_hours": 81.8,
    "avg_delay_when_late_hours": 25.4, "avg_detention_hours": 13.2,
    "avg_plant_vivo_hours": 14.8, "avg_dispatch_lead_hours": 13.5,
    "speed_violations": 1667158, "avg_violations_per_trip": 264.7,
    "avg_gps_uptime": 96.0, "avg_speed_kmph": 37.9, "market_share_pct": 92.2
  },
  "previous": {},
  "delta_pct": {}
}
```

#### `GET /api/v1/funnel`  ·  filters
Trips reaching each lifecycle stage — drop-offs reveal tracking gaps.
```json
[
  { "stage": "Booked", "count": 6299 },
  { "stage": "Departed plant", "count": 6299 },
  { "stage": "Arrived at destination", "count": 5635 },
  { "stage": "Unloaded (gate-out)", "count": 5453 },
  { "stage": "Trip closed", "count": 6287 },
  { "stage": "Delivery status recorded", "count": 5635 }
]
```

---

### Time Series

#### `GET /api/v1/timeseries`  ·  filters
Extra param: `granularity` = `D` (daily, default), `W` (weekly), `M` (monthly).
One row per period.
```json
[
  {
    "period": "2026-W23", "trips": 1404, "otd_pct": 89.7,
    "avg_transit_hours": 80.63, "avg_detention_hours": 14.58,
    "total_km": 1175704.53, "speed_violations": 374810, "avg_dispatch_lead_hours": 14.82
  }
]
```

---

### Rankings

#### `GET /api/v1/group`  ·  filters
The workhorse league table. Params:
- `by` — grouping field: `transporter` (default), `destination`, `vehicle_category`, `own_market`, `consignor`, `device_type`
- `min_trips` — drop groups with fewer than N trips (default 1)

`schedule_variance_hours` = actual − planned transit (negative = faster than plan);
`violations_per_trip` and `share_pct` are derived per group.
```json
[
  {
    "transporter": "CJ DARCL Logistics Limited", "trips": 693, "otd_pct": 84.6,
    "avg_transit_hours": 114.53, "median_transit_hours": 111.18,
    "avg_planned_transit_hours": 153.52, "avg_detention_hours": 14.43,
    "avg_distance_km": 1233.16, "total_km": 810185.79, "avg_speed_kmph": 41.18,
    "speed_violations": 273549, "avg_gps_uptime": 94.67, "vehicles": 485,
    "destinations": 62, "violations_per_trip": 394.7, "share_pct": 11.0,
    "schedule_variance_hours": -39.0
  }
]
```
> Set `by=destination` for the **lane** table, `by=vehicle_category` / `own_market` for fleet cuts.

#### `GET /api/v1/fleet`  ·  filters
One call for the whole fleet view. Returns an object with:
`vehicle_category`, `own_market`, `device_type`, `asset_make` (each a `group`-style
list), plus `top_violating_vehicles` (15) and `low_gps_vehicles` (uptime < 80%).
```json
{
  "vehicle_category": [ /* group rows */ ],
  "own_market": [ /* group rows */ ],
  "device_type": [ /* group rows */ ],
  "asset_make": [ /* group rows */ ],
  "top_violating_vehicles": [
    { "vehicle_no": "JH05DN1629", "trips": 4, "violations": 10500,
      "avg_gps_uptime": 100.0, "total_km": 6483.08, "transporter": "FRONTLINE ASSOCIATES" }
  ],
  "low_gps_vehicles": [ /* … */ ]
}
```

---

### Geo

#### `GET /api/v1/geo`  ·  filters
Map-ready. Origin (Jamshedpur) + one point per geocoded destination with performance.
`unmapped` lists destinations the offline geocoder couldn't place; `mapped_pct` is the
drawable share.
```json
{
  "origin": { "name": "JAMSHEDPUR", "lat": 22.8046, "lon": 86.2029 },
  "points": [
    { "destination": "ABHOYAPUR", "dest_lat": 26.14, "dest_lon": 91.74,
      "trips": 19, "otd_pct": 81.2, "avg_transit_hours": 126.15,
      "avg_distance_km": 1221.48, "total_km": 19543.73 }
  ],
  "unmapped": [],
  "mapped_pct": 100.0
}
```

---

### Heatmaps

#### `GET /api/v1/heatmap/dow_hour`  ·  filters
Departure rhythm as a 7×24 grid (`values[dow][hour]`).
```json
{ "rows": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
  "cols": [0,1,2, "…", 23],
  "values": [[46,74,51, "…"], "… 7 rows"] }
```

#### `GET /api/v1/heatmap/pivot`  ·  filters
Arbitrary matrix. Params: `rows` (field), `cols` (field, e.g. `dept_week`,
`dept_month`, `dept_dow`), `metric` (`trips`, `otd_pct`, or any numeric trip metric),
`top` (keep top-N rows by volume, default 12). `null` where a cell has no data.
```json
{ "rows": ["CJ DARCL Logistics Limited", "SAIZAR Enterprise Pvt. Ltd.", "…"],
  "cols": ["2026-W23","2026-W24","2026-W25","2026-W26","2026-W27"],
  "values": [[87.2, 86.5, 80.2, 86.6, 77.8], "…"] }
```

---

### Statistics

#### `GET /api/v1/correlation`  ·  filters
Pearson correlation across numeric trip metrics. `values` is a square matrix aligned to `labels`.
```json
{ "labels": ["transit_hours","planned_transit_hours","detention_hours","run_hours","…"],
  "values": [[1.0, 0.81, 0.14, 0.79, "…"], "…"] }
```

#### `GET /api/v1/distribution`  ·  filters
Param `metric` (default `transit_hours`). Summary stats + up to 4,000 sampled raw
values for a histogram/violin.
```json
{
  "stats": { "count": 5597, "mean": 80.42, "median": 81.77, "std": 52.47,
             "min": 0.02, "max": 500.6, "p10": 11.46, "p90": 145.85, "p95": 164.84, "skew": 0.61 },
  "values": [149.47, 112.38, 73.52, "…"]
}
```

#### `GET /api/v1/boxdata`  ·  filters
Raw `(group, value)` pairs for the top-N groups — feed straight into a box/violin plot.
Params: `group_by`, `metric`, `top` (default 10).
```json
[ { "group": "CJ DARCL Logistics Limited", "value": 143.85 },
  { "group": "CJ DARCL Logistics Limited", "value": 153.27 } ]
```

#### `GET /api/v1/outliers`  ·  filters
Trips whose transit deviates ≥ `z` standard deviations from their **own lane's** mean
(lanes need 8+ trips). Param `z` (omit to use the configured default). Up to 200 rows,
most extreme first.
```json
[
  { "trip_id": 28175710, "dept_dt": "2026-06-05 03:18",
    "transporter": "UTILITY TRANSPORT COMPANY", "vehicle_no": "NL01AK1939",
    "destination": "TIRUNINRAVUR", "distance_km": 1624.79, "transit_hours": 500.6,
    "lane_mean_transit": 108.8, "z_score": 10.53,
    "delivery_status": "Delay Delivery", "driver_name": "JITENDRA KUMAR" }
]
```

---

### Records

#### `GET /api/v1/records`  ·  filters
Trip-level rows, newest first. Param `limit` (default 500, capped 5,000).
```json
[
  { "trip_id": 28613535, "dept_dt": "2026-06-30 23:58",
    "transporter": "NITIN ENTERPRISES", "vehicle_no": "NL01AD3635",
    "vehicle_category": "HEAVY VEHICLE", "own_market": "Market",
    "consignor": "TATA STEEL-ISWP", "consignee": "MOTI INFRAHEIGHTS PRIVATE LIMITED",
    "destination": "RANCHI", "distance_km": 157.59, "transit_hours": 14.82,
    "planned_transit_hours": 48.0, "detention_hours": 3.27, "avg_speed_kmph": 35.5,
    "speed_violations": 55, "gps_uptime": 100.0, "delivery_status": "On Time Delivery",
    "delivery_delta_hours": -33.18, "driver_name": "AMIT MANDAL",
    "trip_closed_reason": "DESTINATION REACHED" }
]
```

---

### AI — narrative insights over any endpoint

The AI layer is **decoupled on purpose**: the numeric endpoints never depend on the
LLM (they stay fast and always work), and the AI endpoint is a separate call you make
when you want a business-language write-up. This means **you can get an AI narrative
for the output of *any* endpoint above** — you choose what to analyse.

#### `POST /api/v1/ai/insight`
**Body:**
```json
{
  "context": "Transporter performance review",   // required-ish: what the reader is looking at
  "data":    { /* paste the JSON from any endpoint, or your own subset */ },
  "question": "Which transporters need a performance conversation?",  // optional
  "filters": { "date_from": "2026-06-01" }        // optional, echoed into the prompt
}
```
**Response:**
```json
{
  "markdown": "### Key insights\n- …\n### Risks & watch-outs\n- …\n### Recommendations\n- …",
  "provider": "Azure OpenAI · gpt-4.1",
  "elapsed_s": 2.5
}
```
The `markdown` field is a ready-to-render report with three fixed sections (Key
insights / Risks & watch-outs / Recommendations), grounded strictly in the numbers
you send. **Typical pattern:** call a data endpoint, then POST its JSON here.

```python
import requests
BASE, H = "http://127.0.0.1:8000", {"X-API-Key": "<key>"}

# 1) get the numbers
kpis = requests.get(f"{BASE}/api/v1/kpis", headers=H).json()

# 2) get the narrative about those numbers
insight = requests.post(f"{BASE}/api/v1/ai/insight", headers=H, json={
    "context": "Executive overview for June 2026",
    "data": kpis,
    "question": "What are the top three operational risks?",
}).json()
print(insight["markdown"])
```

#### `POST /api/v1/ai/test`
Fires a one-line prompt at the configured provider — use it to verify keys.
```json
{ "provider": "Azure OpenAI · gpt-4.1", "response": "CONNECTION OK", "elapsed_s": 1.9 }
```

> **On errors:** if no provider is configured you get a clean `400` pointing to
> Settings. If the provider is configured but the upstream call fails (rate limit,
> content filter, network blip) you get a `502` whose body carries the reason — these
> are transient; **retry**. The provider is switchable at runtime from the dashboard
> Settings page (Azure OpenAI / OpenAI / Hugging Face free tier).

---

### Settings & Data Management
- `GET /api/v1/settings` — all runtime settings; secret keys masked to last 4 chars with a companion `<key>_set` boolean.
- `PUT /api/v1/settings` — partial update; send `"__keep__"` for a secret to leave it unchanged.
- `POST /api/v1/data/reload` — re-run the ETL from the configured Excel; returns an import summary.
- `POST /api/v1/data/upload` — multipart `.xlsx` upload (same column layout as the TTA export), replaces the dataset.

---

## 2b. Per-figure endpoints — one named route per dashboard visual

Alongside the coarse endpoints above, **every dashboard figure has its own named
endpoint** under **`/api/v1/figures/…`** (tag groups `Figures · Overview`, `· Trends`,
`· Transporters`, `· Lanes`, `· Geo`, `· Heatmaps`, `· Distributions`, `· Fleet`,
`· Records`). Same auth and same filters; each returns exactly the data that figure
plots. Use these when you want a route that maps 1:1 to a chart rather than composing
the generic endpoints yourself.

| Figure endpoint | Figure |
|---|---|
| `GET /api/v1/figures/kpi_summary` | Executive KPI cards |
| `GET /api/v1/figures/dispatch_volume_trend` | Daily dispatch volume + moving avg |
| `GET /api/v1/figures/otd_vs_target` | OTD gauge vs target |
| `GET /api/v1/figures/transit_vs_otd_trend` | Transit vs OTD dual-axis line |
| `GET /api/v1/figures/delivery_status_split` | On-time vs delayed donut |
| `GET /api/v1/figures/top_destinations` | Top-destinations bar |
| `GET /api/v1/figures/transporter_volume_share` | Transporter share pie |
| `GET /api/v1/figures/trip_lifecycle_funnel` | Lifecycle funnel |
| `GET /api/v1/figures/otd_trend` | OTD % trend line |
| `GET /api/v1/figures/transit_detention_trend` | Transit & detention trend |
| `GET /api/v1/figures/dispatch_lead_trend` | Dispatch lead-time trend |
| `GET /api/v1/figures/distance_trend` | Distance trend |
| `GET /api/v1/figures/speed_violations_trend` | Speed-violations trend |
| `GET /api/v1/figures/transporter_scorecard` | Transporter league table |
| `GET /api/v1/figures/transporter_best_worst_otd` | Best/worst OTD bars |
| `GET /api/v1/figures/transporter_risk_map` | Transit-vs-OTD risk bubbles |
| `GET /api/v1/figures/transporter_transit_boxplot` | Transit spread box plots |
| `GET /api/v1/figures/lane_performance` | Lane table |
| `GET /api/v1/figures/distance_vs_transit` | Distance-vs-transit scatter + pace |
| `GET /api/v1/figures/slowest_corridors` | Slowest corridors |
| `GET /api/v1/figures/schedule_variance_lanes` | Behind/ahead of plan |
| `GET /api/v1/figures/lane_volume_treemap` | Lane treemap |
| `GET /api/v1/figures/geo_points` | Map flow/bubble data |
| `GET /api/v1/figures/departure_rhythm` | Weekday×hour heatmap |
| `GET /api/v1/figures/transporter_month_heatmap` | Transporter×month heatmap |
| `GET /api/v1/figures/destination_month_heatmap` | Destination×month heatmap |
| `GET /api/v1/figures/correlation_matrix` | Correlation matrix |
| `GET /api/v1/figures/metric_distribution` | Histogram/violin/ECDF source |
| `GET /api/v1/figures/metric_boxplot_by_group` | Grouped box plots |
| `GET /api/v1/figures/transit_outliers` | Per-lane z-score anomalies |
| `GET /api/v1/figures/own_vs_market` | Own vs market |
| `GET /api/v1/figures/vehicle_category_mix` | Vehicle category mix |
| `GET /api/v1/figures/gps_device_types` | GPS device types |
| `GET /api/v1/figures/asset_make_performance` | Asset make performance |
| `GET /api/v1/figures/top_violating_vehicles` | Top speed violators |
| `GET /api/v1/figures/low_gps_vehicles` | Low GPS-uptime vehicles |
| `GET /api/v1/figures/gps_uptime_distribution` | GPS uptime distribution |
| `GET /api/v1/figures/trip_records` | Data Explorer records |

Every one of these also exists as a same-named **MCP tool** (`tta_kpi_summary`,
`tta_otd_trend`, …) on the MCP server — 51 tools total (13 generic + 38 per-figure).

## 3. Every chart is exposed — dashboard ↔ endpoint map

Each visual in the Streamlit dashboard is driven entirely by these endpoints; there is
no data computed only in the UI. So an integrator can rebuild any of these views, or
new ones, straight from the API. The `/api/v1/figures/*` routes above give you a
one-call shortcut per visual; the table below shows the underlying generic endpoints.

| Dashboard page / chart | Endpoint(s) |
|---|---|
| Executive Overview — KPI cards & deltas | `GET /kpis` |
| Executive Overview — volume trend | `GET /timeseries` |
| Executive Overview — OTD gauge, delivery split, top destinations, transporter share | `GET /kpis`, `GET /group` |
| Executive Overview — trip lifecycle funnel | `GET /funnel` |
| Time & Trends — all trend lines | `GET /timeseries` |
| Transporter Scorecard — league table, rankings, risk bubble | `GET /group?by=transporter` |
| Transporter Scorecard — transit box plots | `GET /boxdata` |
| Routes & Lanes — lane table, slowest corridors, schedule variance, treemap | `GET /group?by=destination` |
| Geo Intelligence — flow arcs, volume bubbles, density | `GET /geo` |
| Heatmaps — weekday×hour rhythm | `GET /heatmap/dow_hour` |
| Heatmaps — transporter×month / destination×month | `GET /heatmap/pivot` |
| Heatmaps — correlation matrix | `GET /correlation` |
| Fleet & Vehicles — mix, GPS, top violators, low-GPS | `GET /fleet`, `GET /distribution?metric=gps_uptime` |
| Distributions & Outliers — histogram/violin/ECDF | `GET /distribution` |
| Distributions & Outliers — grouped box plots | `GET /boxdata` |
| Distributions & Outliers — z-score anomalies + CSV | `GET /outliers` |
| Data Explorer — filtered raw trips + CSV | `GET /records` |
| AI Insights Studio — every analysis pack & free-form Q | `POST /ai/insight` |
| Settings / Integrations | `GET,PUT /settings`, `POST /data/*` |

---

## 4. Errors

| Status | Meaning | Body |
|---|---|---|
| `200` | Success | JSON payload |
| `400` | Bad param (e.g. invalid `by`) or AI provider disabled | `{ "detail": "…" }` |
| `401` | Missing/invalid `X-API-Key` | `{ "detail": "Missing or invalid X-API-Key header. …" }` |
| `404` | Data source file missing (reload) | `{ "detail": "…" }` |
| `502` | AI provider call failed upstream (transient — retry) | `{ "detail": "AI provider call failed: …" }` |

---

## 5. Integrating

### Auto-wrap as MCP tools
The spec at `/api/v1/openapi.json` is the handover artifact. Endpoint summaries and
descriptions become tool descriptions automatically. Example with FastMCP:
```python
from fastmcp import FastMCP
import httpx

client = httpx.AsyncClient(base_url="https://<host>",
                           headers={"X-API-Key": "<key>"})
mcp = FastMCP.from_openapi(
    openapi_spec=httpx.get("https://<host>/api/v1/openapi.json").json(),
    client=client,
)
mcp.run()  # every /api/v1 endpoint is now an MCP tool
```

### Postman / typed clients
Import `/api/v1/openapi.json` into Postman (creates a collection with all endpoints
and examples), or run `openapi-generator` / `openapi-python-client` against it for a
typed SDK. Add the `X-API-Key` header once at the collection/client level.

### Ready-made MCP server (bonus)
If you'd rather not build the wrapper, the platform ships its own MCP server (13
read-only `tta_*` tools over the same analytics), stdio or streamable HTTP on
`:8010/mcp`. See the **🔌 Integrations** page in the dashboard for connection recipes.

---

## 6. Quick reference (copy-paste)

```bash
BASE=http://127.0.0.1:8000        # or your tunnel/LAN host
KEY=tta_xxxxxxxxxxxxxxxxxxxxxxxx

# dictionary of valid filter values — call first
curl -s -H "X-API-Key: $KEY" "$BASE/api/v1/meta"

# headline KPIs for one transporter in the first half of June
curl -s -H "X-API-Key: $KEY" \
  "$BASE/api/v1/kpis?transporters=CJ%20DARCL%20Logistics%20Limited&date_from=2026-06-01&date_to=2026-06-15"

# worst lanes (destinations with >=10 trips)
curl -s -H "X-API-Key: $KEY" "$BASE/api/v1/group?by=destination&min_trips=10"

# anomalous trips at z >= 4
curl -s -H "X-API-Key: $KEY" "$BASE/api/v1/outliers?z=4"

# narrative over whatever you just pulled
curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  "$BASE/api/v1/ai/insight" \
  -d '{"context":"Lane review","data":{"note":"paste endpoint JSON here"},"question":"Which lanes are worst and why?"}'
```
