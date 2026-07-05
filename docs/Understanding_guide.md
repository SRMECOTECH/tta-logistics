# TTA Analytics — Presentation Guide

*A walkthrough you can present from: what the data is, how the app works, and — page by
page — every map and figure with the exact data it is plotted on.*

---

## 1. The one-line pitch

> **A complete decision cockpit for outbound steel logistics.** It takes a raw monthly
> trip export from the plant's transport system, cleans and enriches it automatically,
> and turns it into an interactive dashboard, a REST API, and an AI analyst — so a
> manager can see *what* is happening, *where*, and *what to do about it*, in minutes.

Everything is computed from **one real dataset**; nothing on screen is mocked.

---

## 2. What the data is about

**Source:** a single monthly Excel export (`data/TTA.xlsx`) from the plant's
transporter-tracking system — the kind of file a logistics team already produces today.

**Scope of the demo dataset (June 2026):**

| | |
|---|---|
| Trips (loaded truckloads) | **6,299** |
| Origin | **JAMSHEDPUR** steel plant (all trips start here) |
| Destinations across India | **161** |
| Transport partners (carriers) | **48** |
| Unique vehicles | **~3,500** |
| Date range | 1–30 June 2026 |

**Each row = one outbound trip**, with ~40 raw fields. The important ones:

- **Who & what:** transporter, vehicle number & type, driver, consignor (which plant unit shipped), consignee (customer), own-vs-market fleet flag.
- **Where:** destination city, distance travelled (km), pin code.
- **When:** booking, plant departure, ETA (promised), ATA (actual arrival), gate-out, trip close, delivery date.
- **How well:** transit time, detention (wait-to-unload), plant "vivo" (time inside our own plant), run vs stop time, delivery status (On-time / Delay), GPS uptime, speed-violation event count.

**What the app derives on import** (this is the analytical value-add — the raw file
doesn't contain these):

| Derived field | Meaning |
|---|---|
| `transit_hours` | Actual door-to-door journey time, parsed from "5 Days 23:51"–style text |
| `planned_transit_hours` | The *promised* transit (ETA − departure) |
| `schedule_variance` | Actual − planned (are we honest about delivery windows?) |
| `delivery_delta_hours` | Hours early/late vs promise (negative = early) |
| `dispatch_lead_hours` | Booking → gate-out (internal planning friction) |
| `avg_speed_kmph` | Effective door-to-door pace, capped to filter GPS noise |
| `is_on_time` | Clean on-time flag → drives the OTD % everywhere |
| `dest_lat` / `dest_lon` | Geocoded destination (offline — ~160 Indian cities + pincode fallback, **no paid map API**) |
| calendar keys | departure date / hour / weekday / week / month for trend & heatmap views |

**Headline numbers this month (talking points):**
- **On-time delivery: 88.5%** — 11.5% of loads miss the promised date.
- **Average transit: 80.4 h**; median 81.8 h.
- **5.23 million km** driven; ~928 km per trip.
- **1.67 million speed-violation events** (≈ 265 per trip) — a safety story.
- **92% of volume rides on hired "market" trucks**, not the own fleet — a control question.
- **100% of trips geolocated** for the map.

**Honest data caveats worth naming to the client** (shows rigour):
- Duplicate transporter spellings exist in the source (e.g. two "Utility Transport" entries) — the app surfaces this rather than hiding it.
- ~10% of trips never record an actual arrival (ATA) — a tracking-discipline gap the funnel makes visible.
- Speed "violations" are raw GPS event counts, so totals are large by nature.

---

## 3. How the application works

```
  data/TTA.xlsx                 (raw monthly export — the only input)
        │
        ▼  ETL: clean · parse durations · derive metrics · geocode
  SQLite  data/tta.db           (auto-created on first run; Excel no longer needed)
        │
        ▼  backend/analytics.py — ONE aggregation engine (pandas)
        │
   ┌────┴───────────────┬────────────────────────┐
   ▼                    ▼                         ▼
 FastAPI REST API   MCP server              (both are just consumers
 :8000  /api/v1/*   :8010  tta_* tools       of the same engine)
   │                    │
   ▼                    ▼
 Streamlit dashboard   external AI agents / the client's own apps
 :8501  (this demo)
        │
        ▼  backend/ai.py — LangChain → Azure OpenAI (live) / OpenAI / HuggingFace
   "✨ Generate AI insights" on every page
```

**Three things to stress in the pitch:**
1. **Every number is computed once** in one engine, then exposed three ways (dashboard for humans, REST API for apps, MCP for AI agents). No number is calculated only inside a chart.
2. **It's fully standalone** — first launch builds the database from the Excel and geocodes every destination offline. Re-import or upload a new month from the Settings page in seconds.
3. **AI is layered on, not bolted in** — the numbers never depend on the LLM; the AI reads the computed aggregates and writes the narrative. Provider is switchable from the UI (Azure is live).

**To run it for the demo:** `run.bat` → opens the dashboard at
`http://localhost:8501`, REST docs at `http://127.0.0.1:8000/docs`, MCP at
`http://127.0.0.1:8010/mcp`. Use the **filters in the left sidebar** (date range,
transporter, destination, vehicle type, own/market, consignor) live during the talk —
every page reacts instantly.

---

## 4. The dashboard, page by page — figures & the data behind them

The dashboard has **11 pages**. Below, each figure is listed with its chart type and the
**exact data it is plotted on**. Every chart also carries a plain-English "what this
shows / what to make of it" note on screen (for the non-technical audience).

> **Demo flow tip:** present in this order — **Executive Overview → Geo Map (the wow shot)
> → Distributions & Outliers (the 500-hour finding) → AI Studio (live narrative) →
> Settings/Integrations (the "plug into anything" closer).**

---

### 🏭 Page 1 — Executive Overview  *(the landing page)*
*The story: one-screen health check — volume, reliability, and where money/reputation leak.*

| Figure | Type | Plotted on |
|---|---|---|
| 8 KPI cards (trips, OTD %, transit, distance, transporters, vehicles, detention, speed alerts/trip) | Metric cards with period-over-period deltas | `/api/v1/kpis` → `current` + `delta_pct` |
| Daily dispatch volume | Area line + 7-day moving average | `/api/v1/timeseries?granularity=D` (`trips` per day) |
| OTD vs target | Gauge with target threshold | `kpis.otd_pct` vs `settings.otd_target_pct` |
| Transit time vs on-time performance | Dual-axis line (transit h + OTD %) | `/api/v1/timeseries` (`avg_transit_hours`, `otd_pct`) |
| Delivery status split | Donut (on-time vs delayed) | `kpis.otd_pct` |
| Top 10 destinations | Horizontal bar, colour = OTD % | `/api/v1/group?by=destination` (`trips`, `otd_pct`) |
| Volume share — top 10 transporters | Donut | `/api/v1/group?by=transporter` (`trips`) |
| Trip lifecycle funnel | Funnel | `/api/v1/funnel` (booked→departed→arrived→unloaded→closed→delivered) |
| ✨ Executive summary | AI narrative | `POST /api/v1/ai/insight` over the KPIs + top lanes/transporters |

---

### 📈 Page 2 — Time & Trends
*The story: is the operation getting better or worse? Direction over any single number. (Daily/Weekly/Monthly toggle.)*

| Figure | Type | Plotted on |
|---|---|---|
| Trip volume | Bar + 3-period moving average | `/api/v1/timeseries` (`trips`) |
| On-time delivery % trend | Line vs 95% target line | `timeseries.otd_pct` |
| Transit & detention hours | Two overlaid area/lines | `timeseries.avg_transit_hours`, `avg_detention_hours` |
| Dispatch lead time | Line | `timeseries.avg_dispatch_lead_hours` |
| Distance covered | Area | `timeseries.total_km` |
| Speed violations | Bar | `timeseries.speed_violations` |
| Underlying data + CSV | Table / download | the same `timeseries` rows |
| ✨ Trend analysis | AI narrative | `ai/insight` over the last 40 periods |

---

### 🚚 Page 3 — Transporter Scorecard
*The story: a report card per carrier — who earns more volume, who needs a conversation.*

| Figure | Type | Plotted on |
|---|---|---|
| League table (12 columns, progress bars, sortable) | Data table | `/api/v1/group?by=transporter` |
| Best OTD % / Worst OTD % | Two horizontal bars | same data, filtered by a **min-trips slider** |
| Risk map: transit vs OTD | Bubble scatter (size=trips, colour=detention) | `group` (`avg_transit_hours`, `otd_pct`, `trips`, `avg_detention_hours`) |
| Head-to-head radar | Radar/spider (2–4 selected carriers, 5 metrics normalised 0–100) | `group` rows for picked transporters |
| Transit time spread | Box plots, top 10 carriers | `/api/v1/boxdata?group_by=transporter&metric=transit_hours` |
| ✨ Benchmarking | AI narrative | `ai/insight` over the scorecard |

---

### 🛣️ Page 4 — Routes & Lanes
*The story: every delivery corridor judged on speed, reliability, and whether promised windows are realistic. Where SLA renegotiations start.*

| Figure | Type | Plotted on |
|---|---|---|
| Lane performance table (lanes ≥ 3 trips) | Table w/ actual vs planned vs variance | `/api/v1/group?by=destination&min_trips=3` |
| Distance vs transit time | Bubble scatter + fitted trend line ("h per km" pace) | `group` (`avg_distance_km`, `avg_transit_hours`, `trips`, `otd_pct`) |
| Slowest corridors | Horizontal bar (effective km/h) | `group.avg_speed_kmph`, lanes ≥ 10 trips |
| Lanes most behind plan | Horizontal bar | `group.schedule_variance_hours` (largest positive) |
| Lanes with most buffer | Horizontal bar | `group.schedule_variance_hours` (largest negative) |
| Lane volume treemap | Treemap (size=trips, colour=OTD %) | `group` top 40 destinations |
| ✨ Corridor analysis | AI narrative | `ai/insight` over top lanes + worst-variance lanes |

---

### 🗺️ Page 5 — Geo Intelligence Map  *(the wow shot)*
*The story: the whole delivery network on a live, rotatable map of India — freight flowing out of Jamshedpur.*

**Rendering:** pydeck / deck.gl 3-D map. Toggles for arcs, bubbles, heatmap; a
dropdown recolours bubbles by OTD %, transit, or distance. Hover any bubble for its
numbers; drag to rotate, scroll to zoom.

| Map layer / element | Type | Plotted on |
|---|---|---|
| Flow arcs (Jamshedpur → each destination) | ArcLayer, width ∝ trips | `/api/v1/geo` → `points` (`dest_lat/lon`, `trips`) + `origin` |
| Volume bubbles | ScatterplotLayer, radius ∝ √trips, colour = selected metric | `geo.points` (`trips`, `otd_pct`/`avg_transit_hours`/`avg_distance_km`) |
| Density heatmap (optional) | HeatmapLayer, weight = trips | `geo.points` |
| Origin marker | Fixed point | `geo.origin` (Jamshedpur 22.80, 86.20) |
| Destination detail table | Table | `geo.points` |
| Not-geolocated list | Table | `geo.unmapped` |
| ✨ Geographic analysis | AI narrative | `ai/insight` over origin + destinations |

*Talking point: 100% of trips are placed on the map using a fully offline geocoder — no
Google Maps bill, works air-gapped.*

---

### 🔥 Page 6 — Heatmaps & Correlations
*The story: patterns that averages hide — when trucks leave, how carriers trend monthly, which factors move together.*

| Figure | Type | Plotted on |
|---|---|---|
| Departure rhythm | 7×24 heatmap (weekday × hour) | `/api/v1/heatmap/dow_hour` |
| Top transporters × month | Heatmap, metric selectable (OTD/volume/transit/detention/GPS) | `/api/v1/heatmap/pivot?rows=transporter&cols=dept_month` |
| Top destinations × month | Heatmap (trip volume) | `/api/v1/heatmap/pivot?rows=destination&cols=dept_month&metric=trips` |
| Correlation matrix | Heatmap, every metric × every metric (−1…+1) | `/api/v1/correlation` |
| ✨ Rhythm & correlation read | AI narrative | `ai/insight` over the departure grid + correlation matrix |

*Talking point: the correlation matrix tells you which lever actually moves which
outcome — e.g. if "stop hours" links to "delay hours" but "speed" doesn't, cutting
en-route stops fixes lateness, not driving faster.*

---

### 🚛 Page 7 — Fleet & Vehicles
*The story: the trucks themselves — own vs hired, tracking quality, and the specific vehicles creating safety risk.*

| Figure | Type | Plotted on |
|---|---|---|
| Own vs Market metric cards | Metric cards | `/api/v1/fleet` → `own_market` |
| Own vs Market side-by-side KPIs | Grouped bar (5 metrics) | `fleet.own_market` |
| Trips by vehicle category | Donut | `fleet.vehicle_category` |
| GPS device type (permanent vs rental) | Bar labelled with GPS uptime | `fleet.device_type` |
| Asset make | Bar coloured by OTD % | `fleet.asset_make` |
| Top speed-violating vehicles | Table | `fleet.top_violating_vehicles` (15 worst) |
| Low GPS-uptime vehicles (<80%) | Table | `fleet.low_gps_vehicles` |
| GPS uptime distribution | Histogram | `/api/v1/distribution?metric=gps_uptime` |
| ✨ Fleet & safety review | AI narrative | `ai/insight` over the fleet blocks |

---

### 📊 Page 8 — Distributions & Outliers  *(the "500-hour" finding)*
*The story: averages lie — show the full spread, then automatically flag individual abnormal trips.*

Metric selector drives every chart (transit, distance, detention, delivery delta, speed,
plant-vivo, dispatch lead, GPS uptime).

| Figure | Type | Plotted on |
|---|---|---|
| 8 stat cards (count, mean, median, std, P10, P90, P95, skew) | Metric cards | `/api/v1/distribution?metric=…` → `stats` |
| Histogram (mean & median lines) | Histogram | `distribution.values` |
| Violin + box | Violin | `distribution.values` |
| Cumulative distribution (ECDF) | Line — "% of trips ≤ x" | derived from `distribution.values` |
| Grouped box comparison | Box plots by transporter/destination/category/… | `/api/v1/boxdata?group_by=…&metric=…` |
| **Automated anomaly table** | Table w/ z-score slider | `/api/v1/outliers?z=…` — per-lane z-score on transit |
| ✨ Distribution + anomaly read | AI narrative | `ai/insight` over stats + flagged trips |

*The killer demo moment: slide the z-score down and surface **trip 28175710 to
TIRUNINRAVUR — 500.6 hours against a lane average of 108.8 h (z = 10.5)**, run by Utility
Transport Company. A once-in-hundreds anomaly the summary reports would never show.*

---

### 🔎 Page 9 — Data Explorer
*The story: the raw trips behind every chart — searchable, filterable, exportable.*

| Figure | Type | Plotted on |
|---|---|---|
| Raw trip table (newest first) + quick search | Table + CSV download | `/api/v1/records?limit=…` |

---

### 🤖 Page 10 — AI Insights Studio
*The story: ask the data questions in plain English; get a management-ready written brief.*

Five one-click **analysis packs** (Executive summary · Transporter deep-dive · Lane
deep-dive · Fleet & safety · Risk & anomaly) plus a free-form question box. Each pack
pulls the relevant endpoints, sends the aggregates to the LLM via LangChain, and returns
markdown (Key insights / Risks / Recommendations) with a download button.

| Element | Plotted/served by |
|---|---|
| Provider status banner | `/api/v1/settings` (`ai_provider`) |
| Analysis packs | pull `/api/v1/kpis`, `/timeseries`, `/group`, `/fleet`, `/outliers` then `POST /ai/insight` |
| "Aggregates sent to the LLM" expander | the exact JSON passed to the model (transparency) |

---

### ⚙️ Page 11 — Settings + 🔌 Integrations
*The story: it's a product, not a script.*

- **Settings:** switch AI provider & paste keys (test-connection button), tune thresholds (OTD target, outlier sensitivity, speed cap), **re-import or upload a new month's Excel**, and copy the **REST API key** (🔑 API access tab).
- **Integrations:** live status of the REST API and MCP server, connection recipes (Claude Desktop, Claude Code, Python, any MCP client), and the tool catalog.

*Closer talking point: the same analytics are exposed as a documented REST API
(`/docs`) and an MCP server, so the client can plug this into their own apps or AI agents
— see `docs/API_GUIDE.md`.*

---

## 5. Suggested 5-minute demo script

1. **Open on Executive Overview.** "One screen: 6,299 trips, 88.5% on-time, 5.2 million km. Green deltas are improvements." Point at the funnel: "notice ~10% of trips never confirm arrival — a tracking gap, already visible."
2. **Apply a filter live** (pick the worst transporter from the sidebar). Watch every number move. "It's fully interactive and filterable."
3. **Jump to the Geo Map.** Rotate it. "The whole network, 100% mapped offline. Red bubbles = poorly served regions."
4. **Distributions & Outliers.** Drag the z-slider. "The system just flagged a 500-hour trip on a 109-hour lane, by itself."
5. **AI Studio.** Run "Executive summary." "Now the AI reads those same numbers and writes the management brief — provider is live Azure OpenAI."
6. **Settings → Integrations.** "And every number is a documented API your team can consume directly." Done.

---

## 6. Why this wins (the value story)

- **Real data, real findings** — not a template; it exposes genuine issues (the 500-hour trip, the 92% market-fleet dependence, the arrival-tracking gap).
- **Speaks to non-technical stakeholders** — every chart is annotated in plain English.
- **Standalone & reusable** — drop in next month's Excel, get a fresh dashboard in seconds.
- **Open architecture** — dashboard, REST API, and MCP all serve the same engine, so it integrates with anything the client already runs.
- **AI that's grounded** — insights are written strictly from the computed numbers, never invented.
```
