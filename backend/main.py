"""FastAPI backend — auto-creates the SQLite DB, auto-imports the Excel on
first run, then serves all analytics + AI endpoints.

Public contract: everything under **/api/v1** (the old /api/* paths keep
working as hidden compatibility aliases). All /api/v1 routes require an
X-API-Key header; /health, /docs and the OpenAPI spec are open."""
import json
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import (APIRouter, Body, Depends, FastAPI, HTTPException, Query,
                     Security, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from sqlalchemy import text

from . import ai, analytics, etl
from .config import DATA_DIR, SECRET_KEYS
from .database import engine, init_db
from .figures_api import FIGURE_TAGS, build_figures_router
from .settings_store import get_settings, save_settings, seed_settings

log = logging.getLogger("uvicorn.error")


# ---------------------------------------------------------------- lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_settings()
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM trips")).scalar()
    if count == 0:
        excel = get_settings().get("excel_path", "")
        if Path(excel).exists():
            summary = etl.load_excel_to_db(excel, speed_cap=float(get_settings()["speed_cap_kmph"]))
            save_settings({"last_import": json.dumps(summary)})
    if not get_settings().get("api_key"):
        key = "tta_" + secrets.token_urlsafe(24)
        save_settings({"api_key": key})
        log.info("Generated API key (send as X-API-Key header): %s "
                 "— also shown on the Settings → API access page; "
                 "set TTA_API_KEY in .env to pin your own.", key)
    yield


# ------------------------------------------------------------ API metadata ---
API_DESCRIPTION = """
Analytics service over outbound road-logistics trips from a steel plant in
**Jamshedpur, India** — the demo dataset covers **June 2026**: 6,299 trips,
48 transporters, 161 destinations, with transit times vs plan, on-time
delivery, detention, dispatch lead times, distances, GPS telemetry and
speed-violation events.

### Authentication
Every `/api/v1/*` endpoint requires an **`X-API-Key`** header. In Swagger,
click **Authorize** and paste the key (available from the platform owner, or
on the Settings → API access page of the dashboard). `/health`, this page and
the OpenAPI spec are open.

### Filter convention (shared by all analytics endpoints)
- `date_from` / `date_to` — ISO dates (`2026-06-01`), inclusive, matched on the plant departure timestamp.
- `transporters`, `destinations`, `vehicle_categories`, `own_market`, `consignors` —
  multi-value filters passed as **`||`-separated strings**, e.g.
  `transporters=Hind Transport||AKR LOGISTICS` (names may contain commas, so `||` is the separator).
- Valid values for every filter come from **`GET /api/v1/meta`** — call it first.

### Integrating
The machine-readable spec lives at [`/api/v1/openapi.json`](/api/v1/openapi.json).
Import it into Postman, generate a typed client, or auto-wrap the endpoints as
MCP tools (e.g. FastMCP's `from_openapi`) — endpoint descriptions in this page
become tool descriptions automatically.
"""

OPENAPI_TAGS = [
    {"name": "Meta", "description": "Service health and the dataset dictionary — date range and valid filter values. Start here."},
    {"name": "KPIs", "description": "Headline metrics for any filtered slice, with period-over-period deltas, plus the trip lifecycle funnel."},
    {"name": "Time Series", "description": "Daily / weekly / monthly trend lines for volume, OTD and operational metrics."},
    {"name": "Rankings", "description": "League tables grouped by transporter, destination (lane), vehicle category, own/market or consignor; fleet summaries."},
    {"name": "Geo", "description": "Map-ready origin/destination points with per-destination performance."},
    {"name": "Heatmaps", "description": "Matrix views: weekday×hour departure rhythm and custom top-N pivots."},
    {"name": "Statistics", "description": "Distributions, correlations, box-plot samples and per-lane z-score outliers."},
    {"name": "Records", "description": "Trip-level raw records for exports and drill-downs."},
    {"name": "AI", "description": "LLM-generated narrative insights over the computed aggregates (provider configured in Settings)."},
    {"name": "Settings", "description": "Runtime configuration: AI provider, analytics thresholds, data source. Secrets are masked."},
    {"name": "Data Management", "description": "Re-import or replace the source Excel; the ETL rebuilds the trips table in seconds."},
    {"name": "Figures", "description": "Named, per-dashboard-figure endpoints under /api/v1/figures/* — one route per visual, so the API mirrors the dashboard. Grouped by page below."},
] + FIGURE_TAGS

app = FastAPI(
    title="TTA Logistics Analytics API",
    version="1.0.0",
    description=API_DESCRIPTION,
    contact={"name": "TTA Analytics platform owner", "email": "sanjoyrsearch@gmail.com"},
    openapi_tags=OPENAPI_TAGS,
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# -------------------------------------------------------------------- auth ---
api_key_header = APIKeyHeader(
    name="X-API-Key", auto_error=False,
    description="API key for all /api/v1 endpoints. Get it from the platform owner "
                "(or the Settings → API access page of the dashboard).",
)


def require_api_key(provided: Optional[str] = Security(api_key_header)) -> None:
    expected = get_settings().get("api_key", "")
    if not (provided and expected and secrets.compare_digest(str(provided), str(expected))):
        raise HTTPException(401, "Missing or invalid X-API-Key header. Get the key from the platform owner.")


# ----------------------------------------------------------------- filters ---
def _split(v: Optional[str]) -> Optional[list[str]]:
    return [x for x in v.split("||") if x] if v else None


def filtered_df(
    date_from: Optional[str] = Query(None, description="Only trips departing on/after this ISO date, e.g. `2026-06-01`.", example="2026-06-01"),
    date_to: Optional[str] = Query(None, description="Only trips departing on/before this ISO date (inclusive), e.g. `2026-06-30`.", example="2026-06-30"),
    transporters: Optional[str] = Query(None, description="`||`-separated transporter names, e.g. `Hind Transport||AKR LOGISTICS`. Valid values: `/api/v1/meta`."),
    destinations: Optional[str] = Query(None, description="`||`-separated destination cities, e.g. `PUNE||CHENNAI`. Valid values: `/api/v1/meta`."),
    vehicle_categories: Optional[str] = Query(None, description="`||`-separated vehicle categories. Valid values: `/api/v1/meta`."),
    own_market: Optional[str] = Query(None, description="`||`-separated fleet ownership classes (e.g. `Own||Market`). Valid values: `/api/v1/meta`."),
    consignors: Optional[str] = Query(None, description="`||`-separated consignor names. Valid values: `/api/v1/meta`."),
):
    """Shared filter dependency: parses the common query params and returns the
    filtered trips DataFrame plus the parsed filter dict."""
    f = {
        "date_from": date_from, "date_to": date_to,
        "transporters": _split(transporters), "destinations": _split(destinations),
        "vehicle_categories": _split(vehicle_categories), "own_market": _split(own_market),
        "consignors": _split(consignors),
    }
    return analytics.apply_filters(analytics.load_df(), f), f


def _example(payload) -> dict:
    """responses= block showing a realistic 200 example in Swagger."""
    return {200: {"description": "Successful response",
                  "content": {"application/json": {"example": payload}}}}


# ----------------------------------------------------- response examples -----
KPIS_EXAMPLE = {
    "current": {
        "trips": 6299, "transporters": 48, "vehicles": 2716, "destinations": 161,
        "total_km": 5230648.0, "avg_km_per_trip": 830.4, "otd_pct": 88.5,
        "avg_transit_hours": 80.4, "median_transit_hours": 71.2,
        "avg_delay_when_late_hours": 27.9, "avg_detention_hours": 12.6,
        "avg_plant_vivo_hours": 9.8, "avg_dispatch_lead_hours": 6.4,
        "speed_violations": 1667176, "avg_violations_per_trip": 264.7,
        "avg_gps_uptime": 92.3, "avg_speed_kmph": 21.6, "market_share_pct": 71.4,
    },
    "previous": {},
    "delta_pct": {},
}

TIMESERIES_EXAMPLE = [
    {"period": "2026-06-01", "trips": 216, "otd_pct": 90.3, "avg_transit_hours": 78.9,
     "avg_detention_hours": 12.4, "total_km": 178450.0, "speed_violations": 56110,
     "avg_dispatch_lead_hours": 6.1},
    {"period": "2026-06-02", "trips": 231, "otd_pct": 87.4, "avg_transit_hours": 82.5,
     "avg_detention_hours": 13.1, "total_km": 190322.0, "speed_violations": 61240,
     "avg_dispatch_lead_hours": 6.6},
]

GROUP_EXAMPLE = [
    {"transporter": "Hind Transport", "trips": 412, "otd_pct": 91.2,
     "avg_transit_hours": 76.3, "median_transit_hours": 69.0,
     "avg_planned_transit_hours": 74.8, "avg_detention_hours": 11.9,
     "avg_distance_km": 812.5, "total_km": 334750.0, "avg_speed_kmph": 22.4,
     "speed_violations": 98420, "avg_gps_uptime": 93.1, "vehicles": 188,
     "destinations": 42, "violations_per_trip": 238.9, "share_pct": 6.5,
     "schedule_variance_hours": 1.5},
]

GEO_EXAMPLE = {
    "origin": {"name": "JAMSHEDPUR", "lat": 22.8046, "lon": 86.2029},
    "points": [
        {"destination": "PUNE", "dest_lat": 18.5204, "dest_lon": 73.8567,
         "trips": 142, "otd_pct": 84.5, "avg_transit_hours": 118.2,
         "avg_distance_km": 1621.0, "total_km": 230182.0},
    ],
    "unmapped": [{"destination": "KOSI KALAN", "trips": 12}],
    "mapped_pct": 96.8,
}

OUTLIERS_EXAMPLE = [
    {"trip_id": 28175710, "dept_dt": "2026-06-03 14:22",
     "transporter": "UTILITY TRANSPORT COMPANY", "vehicle_no": "JH05DL4831",
     "destination": "CHENNAI", "distance_km": 1712.0, "transit_hours": 500.2,
     "lane_mean_transit": 109.4, "z_score": 10.5, "delivery_status": "Delay",
     "driver_name": "R KUMAR"},
]


# ------------------------------------------------------------------ router ---
# All business endpoints live on this router; it is mounted at /api/v1 (the
# documented contract) and again at /api (hidden legacy aliases).
router = APIRouter(dependencies=[Security(require_api_key)])


@app.get("/health", tags=["Meta"], summary="Service liveness (no auth)",
         description="Open health probe: confirms the API is up and reports how many "
                     "trips are loaded in the database. The only endpoint that never "
                     "requires the API key.",
         responses=_example({"status": "ok", "rows": 6299}))
def health():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT COUNT(*) FROM trips")).scalar()
    return {"status": "ok", "rows": rows}


@router.get("/meta", tags=["Meta"], summary="Dataset dictionary and valid filter values",
            description="The entry point for any integration: returns the date range covered by "
                        "the data and the complete value lists for every filter parameter "
                        "(transporters, destinations, vehicle categories, own/market, consignors). "
                        "Use these lists to populate dropdowns or validate filter inputs before "
                        "calling the analytics endpoints. Also includes a summary of the last "
                        "Excel import (row counts, geocoding coverage).")
def api_meta():
    df = analytics.load_df()
    m = analytics.meta(df)
    m["last_import"] = json.loads(get_settings().get("last_import", "{}") or "{}")
    return m


@router.get("/kpis", tags=["KPIs"], summary="Headline KPIs with period-over-period deltas",
            description="Computes the executive metric block for the filtered slice: trip count, "
                        "on-time-delivery %, average/median transit hours, detention, dispatch "
                        "lead time, distance totals, speed-violation counts and GPS uptime. "
                        "`previous` repeats the block for the immediately preceding window of "
                        "equal length and `delta_pct` gives the % change per metric — both are "
                        "empty when no earlier data exists (the demo dataset covers June 2026 "
                        "only, so unfiltered calls have no prior window). Note: "
                        "`speed_violations` counts telemetry events, not trips, so values are large.",
            responses=_example(KPIS_EXAMPLE))
def kpis_endpoint(dff=Depends(filtered_df)):
    df, f = dff
    return analytics.kpis(df, f)


@router.get("/timeseries", tags=["Time Series"], summary="Trend lines by day, week or month",
            description="Buckets the filtered trips by departure date and returns one row per "
                        "period with volume, OTD %, average transit and detention hours, total "
                        "km, speed-violation events and dispatch lead time. Ideal for plotting "
                        "trends or feeding anomaly detection on daily operations.",
            responses=_example(TIMESERIES_EXAMPLE))
def timeseries_endpoint(
        granularity: str = Query("D", description="Bucket size: `D` daily, `W` weekly, `M` monthly."),
        dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.timeseries(df, granularity)


@router.get("/group", tags=["Rankings"], summary="League table for any grouping field",
            description="Ranks groups (default: transporters) by volume with per-group OTD %, "
                        "transit vs plan, detention, distance, speed and GPS metrics. "
                        "`schedule_variance_hours` is actual minus planned transit (positive = "
                        "slower than plan); `violations_per_trip` and `share_pct` are derived "
                        "per group. Use `min_trips` to drop statistically thin groups. This one "
                        "endpoint powers transporter scorecards, lane tables and fleet-mix views.",
            responses=_example(GROUP_EXAMPLE))
def group_endpoint(
        by: str = Query("transporter", description=f"Grouping field, one of: {', '.join(analytics.GROUP_FIELDS)}."),
        min_trips: int = Query(1, description="Only return groups with at least this many trips."),
        dff=Depends(filtered_df)):
    if by not in analytics.GROUP_FIELDS:
        raise HTTPException(400, f"'by' must be one of {analytics.GROUP_FIELDS}")
    df, _ = dff
    return analytics.group_summary(df, by, min_trips)


@router.get("/geo", tags=["Geo"], summary="Map-ready destination points with performance",
            description="Returns the plant origin (Jamshedpur) plus one point per geocoded "
                        "destination with lat/lon, trip volume, OTD %, average transit hours and "
                        "distance — ready to draw flow maps or bubble maps. Destinations the "
                        "offline geocoder could not place are listed under `unmapped`; "
                        "`mapped_pct` gives the share of trips that are drawable.",
            responses=_example(GEO_EXAMPLE))
def geo_endpoint(dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.geo_points(df)


@router.get("/heatmap/dow_hour", tags=["Heatmaps"], summary="Departure rhythm: weekday × hour matrix",
            description="Counts plant departures in a 7×24 matrix (rows Mon–Sun, columns hour of "
                        "day). Shows the operational rhythm of the plant — dispatch peaks, quiet "
                        "windows, weekend behaviour.",
            responses=_example({"rows": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                                "cols": [0, 1, 2], "values": [[12, 8, 15], [10, 6, 18], [11, 9, 14],
                                                              [13, 7, 16], [9, 5, 17], [8, 4, 12], [7, 3, 10]]}))
def heatmap_dow_hour_endpoint(dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.heatmap_dow_hour(df)


@router.get("/heatmap/pivot", tags=["Heatmaps"], summary="Custom pivot matrix (top-N rows × columns)",
            description="Builds an arbitrary matrix: pick a row field, a column field and a "
                        "metric, and get the top-N rows by volume as a ready-to-plot grid "
                        "(nulls where a cell has no data). Example: transporter × month with "
                        "`otd_pct` shows who is improving or slipping over time.")
def heatmap_pivot_endpoint(
        rows: str = Query("transporter", description=f"Row field, e.g. one of: {', '.join(analytics.GROUP_FIELDS)}."),
        cols: str = Query("dept_month", description="Column field, e.g. `dept_month`, `dept_week`, `dept_dow`."),
        metric: str = Query("otd_pct", description="Cell value: `trips`, `otd_pct`, or any numeric trip metric "
                                                   f"({', '.join(analytics.NUMERIC_METRICS)})."),
        top: int = Query(12, description="Keep only the top-N row values by trip volume."),
        dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.heatmap_pivot(df, rows, cols, metric, top)


@router.get("/correlation", tags=["Statistics"], summary="Correlation matrix across trip metrics",
            description="Pearson correlation between all numeric trip metrics (transit, detention, "
                        "distance, speed, violations, GPS uptime, …) on the filtered slice. Useful "
                        "for spotting drivers — e.g. does detention correlate with late delivery?")
def correlation_endpoint(dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.correlation(df)


@router.get("/distribution", tags=["Statistics"], summary="Distribution stats + sample for one metric",
            description="Summary statistics (mean, median, std, min/max, P10/P90/P95, skew) plus "
                        "up to 4,000 sampled raw values for histogram/violin plotting of any "
                        "numeric trip metric on the filtered slice.")
def distribution_endpoint(
        metric: str = Query("transit_hours", description=f"One of: {', '.join(analytics.NUMERIC_METRICS)}."),
        dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.distribution(df, metric)


@router.get("/boxdata", tags=["Statistics"], summary="Box-plot samples of a metric per group",
            description="Raw (group, value) pairs for the top-N groups by volume — feed directly "
                        "into a box/violin plot to compare, e.g., transit-time spread per "
                        "transporter. Sampled to at most 4,000 points.")
def boxdata_endpoint(
        group_by: str = Query("transporter", description=f"One of: {', '.join(analytics.GROUP_FIELDS)}."),
        metric: str = Query("transit_hours", description=f"One of: {', '.join(analytics.NUMERIC_METRICS)}."),
        top: int = Query(10, description="Keep only the top-N groups by trip volume."),
        dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.boxdata(df, group_by, metric, top)


@router.get("/fleet", tags=["Rankings"], summary="Fleet mix, GPS compliance and top violators",
            description="One call for the fleet view: summaries by vehicle category, own vs "
                        "market, GPS device type and asset make, plus the 15 vehicles with the "
                        "most speed-violation events and vehicles with GPS uptime below 80%.")
def fleet_endpoint(dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.fleet(df)


@router.get("/outliers", tags=["Statistics"], summary="Anomalous trips by per-lane z-score",
            description="Flags trips whose transit time deviates from their own lane's "
                        "(destination's) average by at least `z` standard deviations — lanes need "
                        "8+ trips to qualify, so a 500-hour trip to a 109-hour lane surfaces "
                        "immediately (z≈10). Returns up to 200 trips, most extreme first, with "
                        "the lane average and z-score attached for context.",
            responses=_example(OUTLIERS_EXAMPLE))
def outliers_endpoint(
        z: Optional[float] = Query(None, description="Z-score threshold; omit to use the configured default (Settings, initially 3.0)."),
        dff=Depends(filtered_df)):
    df, _ = dff
    z_val = z if z is not None else float(get_settings()["outlier_z"])
    return analytics.outliers(df, z_val)


@router.get("/funnel", tags=["KPIs"], summary="Trip lifecycle funnel",
            description="Counts trips at each lifecycle stage: booked → departed plant → arrived "
                        "at destination → unloaded (gate-out) → trip closed → delivery status "
                        "recorded. Drop-offs reveal tracking gaps — in the demo data ~10% of "
                        "trips never record an arrival (ATA).",
            responses=_example([{"stage": "Booked", "count": 6299},
                                {"stage": "Departed plant", "count": 6299},
                                {"stage": "Arrived at destination", "count": 5665}]))
def funnel_endpoint(dff=Depends(filtered_df)):
    df, _ = dff
    return analytics.funnel(df)


@router.get("/records", tags=["Records"], summary="Trip-level records, newest first",
            description="Raw filtered trips with the operationally useful columns (IDs, "
                        "timestamps, transporter, vehicle, destination, distance, transit vs "
                        "plan, detention, speed, violations, GPS uptime, delivery status/delta, "
                        "driver). Sorted by departure descending; `limit` is capped at 5,000. "
                        "Timestamps are `YYYY-MM-DD HH:MM` strings; nulls are JSON `null`.")
def records_endpoint(
        limit: int = Query(500, description="Maximum rows to return (hard cap 5,000)."),
        dff=Depends(filtered_df)):
    df, _ = dff
    cols = ["trip_id", "dept_dt", "transporter", "vehicle_no", "vehicle_category", "own_market",
            "consignor", "consignee", "destination", "distance_km", "transit_hours",
            "planned_transit_hours", "detention_hours", "avg_speed_kmph", "speed_violations",
            "gps_uptime", "delivery_status", "delivery_delta_hours", "driver_name", "trip_closed_reason"]
    out = df.sort_values("dept_dt", ascending=False).head(min(limit, 5000))[cols]
    return analytics.clean_records(out)


# ---------------------------------------------------------------------- AI ---
@router.post("/ai/insight", tags=["AI"], summary="Narrative insight from the configured LLM",
             description="Sends your context + data (typically the JSON output of another "
                         "endpoint) through a LangChain pipeline to the configured provider "
                         "(Azure OpenAI / OpenAI / Hugging Face) and returns a business-language "
                         "analysis. Numeric endpoints never depend on this — if no provider is "
                         "configured you get a clear 400 pointing to Settings.")
def ai_insight(payload: dict = Body(
        ...,
        example={"context": "Transporter performance review",
                 "data": {"worst_otd": {"transporter": "UTILITY TRANSPORT COMPANY", "otd_pct": 39.1}},
                 "question": "Which transporters need a performance conversation?"},
        description="`context` (string, required-ish), optional `data` (any JSON to analyse), "
                    "`question` (string) and `filters` (echoed for the prompt).")):
    settings = get_settings()
    try:
        return ai.generate_insight(
            settings,
            context=payload.get("context", "General analysis"),
            data=payload.get("data"),
            question=payload.get("question"),
            filters=payload.get("filters"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"AI provider call failed: {e}")


@router.post("/ai/test", tags=["AI"], summary="Ping the configured AI provider",
             description="Fires a one-line test prompt at the active provider and returns the "
                         "provider name, response snippet and round-trip time. Use it to verify "
                         "keys after changing Settings.")
def ai_test():
    try:
        return ai.test_connection(get_settings())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"AI provider call failed: {e}")


# ---------------------------------------------------------------- settings ---
@router.get("/settings", tags=["Settings"], summary="Read runtime settings (secrets masked)",
            description="Returns all runtime settings. Secret values (API keys) are masked to "
                        "their last 4 characters, with a companion `<key>_set` boolean indicating "
                        "whether a value exists.")
def settings_get():
    s = get_settings()
    out = {}
    for k, v in s.items():
        if k in SECRET_KEYS:
            out[k] = ("••••••••" + v[-4:]) if v else ""
            out[f"{k}_set"] = bool(v)
        else:
            out[k] = v
    return out


@router.put("/settings", tags=["Settings"], summary="Update runtime settings",
            description="Partial update: send only the keys you want to change. For secret keys, "
                        "send the sentinel value `__keep__` to leave the stored secret unchanged "
                        "(this is what the dashboard does when a masked field is untouched).")
def settings_put(updates: dict = Body(..., example={"otd_target_pct": "95", "azure_api_key": "__keep__"})):
    clean: dict[str, Any] = {}
    for k, v in updates.items():
        if k in SECRET_KEYS and v == "__keep__":
            continue
        clean[k] = v
    save_settings(clean)
    return {"saved": sorted(clean.keys())}


# -------------------------------------------------------------------- data ---
@router.post("/data/reload", tags=["Data Management"], summary="Re-import from the source Excel",
             description="Wipes the trips table and re-runs the full ETL pipeline (clean, derive, "
                         "geocode) from the configured Excel path. Returns an import summary with "
                         "row counts and geocoding coverage. Takes a few seconds.")
def data_reload():
    settings = get_settings()
    try:
        summary = etl.load_excel_to_db(settings["excel_path"], speed_cap=float(settings["speed_cap_kmph"]))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    save_settings({"last_import": json.dumps(summary)})
    return summary


@router.post("/data/upload", tags=["Data Management"], summary="Upload a new Excel and import it",
             description="Multipart upload of an .xlsx with the same column layout as the TTA "
                         "export. The file replaces the current dataset and becomes the new "
                         "configured source. Returns the same import summary as `/data/reload`.")
async def data_upload(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Please upload an .xlsx file")
    dest = DATA_DIR / "uploaded.xlsx"
    dest.write_bytes(await file.read())
    settings = get_settings()
    summary = etl.load_excel_to_db(dest, speed_cap=float(settings["speed_cap_kmph"]))
    save_settings({"excel_path": str(dest), "last_import": json.dumps(summary)})
    return summary


# Named per-figure endpoints (one route per dashboard visual), same auth + filters.
figures_router = build_figures_router(filtered_df, require_api_key)
router.include_router(figures_router)

# /api/v1 is the documented contract; /api/* answers as a hidden legacy alias
# so existing consumers and mid-demo browser tabs keep working.
app.include_router(router, prefix="/api/v1")
app.include_router(router, prefix="/api", include_in_schema=False)
