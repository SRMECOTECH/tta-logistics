#!/usr/bin/env python3
"""TTA Analytics MCP server.

Exposes the cleaned & computed logistics analytics (SQLite `data/tta.db`,
built by the FastAPI/ETL app) to any MCP client: Claude Desktop, Claude Code,
agent frameworks, or other applications.

Transports:
    python -m mcp_server                 # stdio (local clients)
    python -m mcp_server --http          # streamable HTTP at http://127.0.0.1:8010/mcp
    python -m mcp_server --http --port N

All tools are read-only and operate on the already-imported database — the
Excel file is never touched here.
"""
import json
import re
import sqlite3
import sys
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from backend import analytics, figures  # noqa: E402
from backend.config import DB_PATH  # noqa: E402

mcp = FastMCP(
    "tta_analytics_mcp",
    instructions=(
        "Analytics over outbound road-logistics trips of a steel plant in Jamshedpur, India "
        "(transporters, lanes, transit times in hours, detention, distances in km, GPS telemetry, "
        "speed alerts, on-time delivery). Start with tta_dataset_overview to learn the data range "
        "and available filter values, then drill down with the specific tools. "
        "All tools are read-only."
    ),
    host="127.0.0.1",
    port=8010,
    stateless_http=True,
    json_response=True,
)

READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


# ------------------------------------------------------------------ inputs ---
class TripFilters(BaseModel):
    """Optional filters applied before aggregation. Omit a field to not filter on it.

    Valid values for the list fields come from tta_dataset_overview."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    date_from: Optional[str] = Field(default=None, description="Earliest departure date, ISO format e.g. '2026-06-01'")
    date_to: Optional[str] = Field(default=None, description="Latest departure date (inclusive), e.g. '2026-06-30'")
    transporters: Optional[List[str]] = Field(default=None, description="Exact transporter names, e.g. ['Hind Transport']")
    destinations: Optional[List[str]] = Field(default=None, description="Exact destination names, e.g. ['JAIPUR']")
    vehicle_categories: Optional[List[str]] = Field(default=None, description="e.g. ['TRAILER', 'HEAVY VEHICLE']")
    own_market: Optional[List[str]] = Field(default=None, description="'Own' and/or 'Market'")
    consignors: Optional[List[str]] = Field(default=None, description="Exact consignor (loading point) names")


def _df(filters: Optional[TripFilters]) -> pd.DataFrame:
    f = filters.model_dump() if filters else {}
    return analytics.apply_filters(analytics.load_df(), f)


def _json(data: Any) -> str:
    return json.dumps(data, default=str, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------- tools ---
@mcp.tool(name="tta_dataset_overview", annotations={"title": "Dataset Overview", **READ_ONLY_ANNOTATIONS})
def tta_dataset_overview() -> str:
    """Entry-point tool: describes the dataset and all valid filter values.

    Call this first. Returns row count, departure-date range, and the exact
    lists of transporters, destinations, vehicle categories, consignors and
    own/market values that other tools accept as filters, plus headline KPIs
    for the full dataset.

    Returns:
        str: JSON with keys:
        {
          "rows": int, "date_min": "YYYY-MM-DD", "date_max": "YYYY-MM-DD",
          "transporters": [str], "destinations": [str],
          "vehicle_categories": [str], "consignors": [str], "own_market": [str],
          "headline_kpis": {"trips": int, "otd_pct": float,
                            "avg_transit_hours": float, "total_km": float, ...}
        }
    """
    df = analytics.load_df()
    meta = analytics.meta(df)
    meta["headline_kpis"] = analytics.kpis(df, {})["current"]
    meta.pop("last_import", None)
    return _json(meta)


@mcp.tool(name="tta_get_kpis", annotations={"title": "KPI Summary", **READ_ONLY_ANNOTATIONS})
def tta_get_kpis(filters: Optional[TripFilters] = None) -> str:
    """Compute the full KPI block for any slice of trips.

    KPIs: trips, transporters, vehicles, destinations, total_km, avg_km_per_trip,
    otd_pct (on-time delivery %), avg/median transit hours, avg_delay_when_late_hours,
    avg_detention_hours, avg_plant_vivo_hours (loading time), avg_dispatch_lead_hours,
    speed_violations, avg_violations_per_trip, avg_gps_uptime, avg_speed_kmph,
    market_share_pct.

    Args:
        filters: Optional TripFilters to slice by date/transporter/destination/etc.

    Returns:
        str: JSON {"current": {...kpis}, "previous": {...same-length prior window},
                   "delta_pct": {kpi: % change vs previous}}
    """
    df = _df(filters)
    if df.empty:
        return "No trips match these filters. Check valid values via tta_dataset_overview."
    return _json(analytics.kpis(df, filters.model_dump() if filters else {}))


@mcp.tool(name="tta_get_timeseries", annotations={"title": "Time Series", **READ_ONLY_ANNOTATIONS})
def tta_get_timeseries(
    granularity: str = Field(default="D", description="'D' daily, 'W' weekly, or 'M' monthly"),
    filters: Optional[TripFilters] = None,
) -> str:
    """Trips, OTD %, transit/detention hours, km and speed violations per period.

    Returns:
        str: JSON list of {"period", "trips", "otd_pct", "avg_transit_hours",
             "avg_detention_hours", "total_km", "speed_violations",
             "avg_dispatch_lead_hours"} sorted by period ascending.
    """
    if granularity not in ("D", "W", "M"):
        return "Error: granularity must be 'D', 'W' or 'M'."
    return _json(analytics.timeseries(_df(filters), granularity))


@mcp.tool(name="tta_group_summary", annotations={"title": "Group Summary / Rankings", **READ_ONLY_ANNOTATIONS})
def tta_group_summary(
    by: str = Field(description="Dimension: 'transporter', 'destination', 'vehicle_category', 'own_market', 'consignor' or 'device_type'"),
    min_trips: int = Field(default=1, ge=1, description="Only include groups with at least this many trips"),
    limit: int = Field(default=25, ge=1, le=200, description="Max groups returned (sorted by trip volume desc)"),
    filters: Optional[TripFilters] = None,
) -> str:
    """Per-group performance scorecard — the workhorse comparison tool.

    Use for questions like "which transporter has the worst OTD" or
    "compare Own vs Market fleet" or "rank destinations by volume".

    Returns:
        str: JSON list per group: {"<by>", "trips", "share_pct", "otd_pct",
             "avg_transit_hours", "median_transit_hours", "avg_planned_transit_hours",
             "schedule_variance_hours" (actual minus planned; positive = behind plan),
             "avg_detention_hours", "avg_distance_km", "total_km", "avg_speed_kmph",
             "speed_violations", "violations_per_trip", "avg_gps_uptime",
             "vehicles", "destinations"}
    """
    if by not in analytics.GROUP_FIELDS:
        return f"Error: 'by' must be one of {analytics.GROUP_FIELDS}."
    rows = analytics.group_summary(_df(filters), by, min_trips)[:limit]
    return _json({"count": len(rows), "groups": rows})


@mcp.tool(name="tta_get_geo_points", annotations={"title": "Geo Destination Points", **READ_ONLY_ANNOTATIONS})
def tta_get_geo_points(filters: Optional[TripFilters] = None) -> str:
    """Destination coordinates + performance, for maps or regional analysis.

    Returns:
        str: JSON {"origin": {name, lat, lon}, "mapped_pct": float,
             "points": [{"destination", "dest_lat", "dest_lon", "trips",
                         "otd_pct", "avg_transit_hours", "avg_distance_km", "total_km"}],
             "unmapped": [{"destination", "trips"}]}
    """
    return _json(analytics.geo_points(_df(filters)))


@mcp.tool(name="tta_get_heatmap", annotations={"title": "Heatmap Matrix", **READ_ONLY_ANNOTATIONS})
def tta_get_heatmap(
    kind: str = Field(
        default="pivot",
        description="'dow_hour' = departures by weekday x hour-of-day; 'pivot' = custom rows x cols matrix",
    ),
    rows: str = Field(default="transporter", description="(pivot only) 'transporter', 'destination', 'vehicle_category', 'consignor' or 'own_market'"),
    cols: str = Field(default="dept_month", description="(pivot only) 'dept_month', 'dept_week', 'dept_date' or 'dept_dow'"),
    metric: str = Field(default="otd_pct", description="(pivot only) 'trips', 'otd_pct', 'transit_hours', 'detention_hours' or 'gps_uptime'"),
    top: int = Field(default=12, ge=1, le=50, description="(pivot only) keep the top-N rows by trip volume"),
    filters: Optional[TripFilters] = None,
) -> str:
    """Matrix data for heatmaps (or any rows x columns cross-tab).

    Returns:
        str: JSON {"rows": [labels], "cols": [labels], "values": [[cell...]]}
        where values align to rows x cols; null cells mean no data.
    """
    df = _df(filters)
    if kind == "dow_hour":
        return _json(analytics.heatmap_dow_hour(df))
    return _json(analytics.heatmap_pivot(df, rows, cols, metric, top))


@mcp.tool(name="tta_get_correlation", annotations={"title": "Correlation Matrix", **READ_ONLY_ANNOTATIONS})
def tta_get_correlation(filters: Optional[TripFilters] = None) -> str:
    """Pearson correlation matrix across all numeric trip metrics
    (transit, planned transit, detention, run/stop hours, distance, speed,
    speed violations, GPS uptime, delivery delay, dispatch lead time).

    Returns:
        str: JSON {"labels": [metric names], "values": [[corr -1..1]]}
    """
    return _json(analytics.correlation(_df(filters)))


@mcp.tool(name="tta_get_distribution", annotations={"title": "Metric Distribution", **READ_ONLY_ANNOTATIONS})
def tta_get_distribution(
    metric: str = Field(description=f"One of: {', '.join(analytics.NUMERIC_METRICS)}"),
    bins: int = Field(default=20, ge=5, le=60, description="Histogram bin count"),
    filters: Optional[TripFilters] = None,
) -> str:
    """Statistical distribution of a numeric metric: summary stats + histogram.

    delivery_delta_hours is signed: negative = delivered early, positive = late.

    Returns:
        str: JSON {"metric": str,
             "stats": {"count","mean","median","std","min","max","p10","p90","p95","skew"},
             "histogram": [{"bin_start": float, "bin_end": float, "count": int}]}
    """
    if metric not in analytics.NUMERIC_METRICS:
        return f"Error: metric must be one of {analytics.NUMERIC_METRICS}."
    dist = analytics.distribution(_df(filters), metric, max_points=100000)
    values = dist["values"]
    hist: list[dict] = []
    if values:
        counts, edges = np.histogram(values, bins=bins)
        hist = [{"bin_start": round(float(edges[i]), 2), "bin_end": round(float(edges[i + 1]), 2),
                 "count": int(c)} for i, c in enumerate(counts)]
    return _json({"metric": metric, "stats": dist["stats"], "histogram": hist})


@mcp.tool(name="tta_get_outliers", annotations={"title": "Anomalous Trips", **READ_ONLY_ANNOTATIONS})
def tta_get_outliers(
    z_threshold: float = Field(default=3.0, ge=1.0, le=6.0, description="Z-score cutoff; lower = more sensitive"),
    limit: int = Field(default=25, ge=1, le=200),
    filters: Optional[TripFilters] = None,
) -> str:
    """Trips whose transit time is anomalous vs their own lane's average
    (per-destination z-score, lanes with >= 8 trips).

    Returns:
        str: JSON {"count": int, "trips": [{"trip_id", "dept_dt", "transporter",
             "vehicle_no", "destination", "distance_km", "transit_hours",
             "lane_mean_transit", "z_score", "delivery_status", "driver_name"}]}
        sorted by |z_score| descending.
    """
    rows = analytics.outliers(_df(filters), z_threshold)[:limit]
    return _json({"count": len(rows), "trips": rows})


@mcp.tool(name="tta_get_fleet_summary", annotations={"title": "Fleet & Compliance Summary", **READ_ONLY_ANNOTATIONS})
def tta_get_fleet_summary(filters: Optional[TripFilters] = None) -> str:
    """Fleet composition & telematics compliance: own-vs-market and
    vehicle-category scorecards, GPS device types, asset makes, the top
    speed-violating vehicles, and vehicles with GPS uptime below 80%.

    Returns:
        str: JSON {"vehicle_category": [...], "own_market": [...],
             "device_type": [...], "asset_make": [...],
             "top_violating_vehicles": [...], "low_gps_vehicles": [...]}
    """
    return _json(analytics.fleet(_df(filters)))


@mcp.tool(name="tta_get_trips", annotations={"title": "List Trip Records", **READ_ONLY_ANNOTATIONS})
def tta_get_trips(
    limit: int = Field(default=20, ge=1, le=200, description="Rows per page"),
    offset: int = Field(default=0, ge=0, description="Rows to skip (pagination)"),
    search: Optional[str] = Field(default=None, description="Case-insensitive substring match across vehicle no, driver, destination, transporter, consignee"),
    filters: Optional[TripFilters] = None,
) -> str:
    """Raw trip records (latest departures first), paginated.

    Returns:
        str: JSON {"total": int, "count": int, "offset": int, "has_more": bool,
             "next_offset": int|null, "trips": [{trip_id, dept_dt, transporter,
             vehicle_no, destination, distance_km, transit_hours,
             delivery_status, driver_name, ...}]}
    """
    df = _df(filters).sort_values("dept_dt", ascending=False)
    cols = ["trip_id", "dept_dt", "transporter", "vehicle_no", "vehicle_category", "own_market",
            "consignor", "consignee", "destination", "distance_km", "transit_hours",
            "planned_transit_hours", "detention_hours", "avg_speed_kmph", "speed_violations",
            "gps_uptime", "delivery_status", "delivery_delta_hours", "driver_name"]
    sub = df[cols]
    if search:
        hay = ["vehicle_no", "driver_name", "destination", "transporter", "consignee"]
        mask = sub[hay].astype(str).apply(
            lambda c: c.str.contains(re.escape(search), case=False, na=False)).any(axis=1)
        sub = sub[mask]
    total = len(sub)
    page = analytics.clean_records(sub.iloc[offset:offset + limit])
    has_more = total > offset + len(page)
    return _json({"total": total, "count": len(page), "offset": offset,
                  "has_more": has_more, "next_offset": offset + len(page) if has_more else None,
                  "trips": page})


@mcp.tool(name="tta_sql_query", annotations={"title": "Read-Only SQL Query", **READ_ONLY_ANNOTATIONS})
def tta_sql_query(
    sql: str = Field(description="A single SELECT (or WITH...SELECT) statement against the 'trips' table"),
    limit: int = Field(default=50, ge=1, le=500, description="Hard cap on returned rows"),
) -> str:
    """Escape hatch: run an arbitrary read-only SQL SELECT on the trips table.

    The database is opened in read-only mode; only a single SELECT/WITH
    statement is accepted. Useful for ad-hoc questions the other tools don't
    cover. Key columns: trip_id, dept_dt, transporter, vehicle_no,
    vehicle_category, own_market, consignor, consignee, destination, pin_code,
    distance_km, transit_hours, planned_transit_hours, detention_hours,
    run_hours, stop_hours, plant_vivo_hours, dispatch_lead_hours,
    delivery_delta_hours, avg_speed_kmph, speed_violations, gps_uptime,
    delivery_status, is_on_time (1/0), dest_lat, dest_lon, lane, dept_date,
    dept_hour, dept_dow (0=Mon), dept_month, dept_week, driver_name.

    Returns:
        str: JSON {"columns": [str], "row_count": int, "rows": [[...]]}
             or "Error: ..." explaining what to fix.
    """
    stmt = sql.strip().rstrip(";")
    if ";" in stmt:
        return "Error: only a single SQL statement is allowed."
    if not re.match(r"^\s*(select|with)\b", stmt, re.IGNORECASE):
        return "Error: only SELECT (or WITH...SELECT) statements are allowed."
    try:
        conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
        try:
            cur = conn.execute(stmt)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(limit)
        finally:
            conn.close()
    except sqlite3.Error as e:
        return f"Error: SQL failed — {e}. Check column names via the tool description."
    return _json({"columns": columns, "row_count": len(rows), "rows": [list(r) for r in rows]})


@mcp.tool(
    name="tta_ai_insight",
    annotations={"title": "AI Narrative Insight", "readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": False, "openWorldHint": True},
)
def tta_ai_insight(
    scope: str = Field(
        default="overview",
        description="Aggregate pack to analyse: 'overview', 'transporters', 'lanes', 'fleet' or 'outliers'",
    ),
    question: Optional[str] = Field(default=None, description="Optional specific question to answer about the data"),
    filters: Optional[TripFilters] = None,
) -> str:
    """Generate a narrative insight (key findings, risks, recommendations) via
    the app's LangChain layer, using whichever LLM provider is enabled in the
    app's Settings (Azure OpenAI / OpenAI / Hugging Face).

    Calls an external LLM. Fails with a clear message if no provider is
    configured — the numeric tools keep working regardless.

    Returns:
        str: markdown insight text, or "Error: ..." if no AI provider is enabled.
    """
    from backend import ai
    from backend.settings_store import get_settings

    settings = get_settings()

    df = _df(filters)
    packs = {
        "overview": lambda: {"kpis": analytics.kpis(df, {})["current"],
                             "weekly": analytics.timeseries(df, "W")},
        "transporters": lambda: {"scorecard": analytics.group_summary(df, "transporter")[:20]},
        "lanes": lambda: {"lanes": analytics.group_summary(df, "destination", 3)[:20]},
        "fleet": lambda: analytics.fleet(df),
        "outliers": lambda: {"outliers": analytics.outliers(df)[:20]},
    }
    if scope not in packs:
        return f"Error: scope must be one of {sorted(packs)}."
    try:
        result = ai.generate_insight(settings, context=f"TTA {scope} analysis",
                                     data=packs[scope](), question=question,
                                     filters=filters.model_dump() if filters else None)
        return f"{result['markdown']}\n\n---\n_Generated by {result['provider']} in {result['elapsed_s']}s_"
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: AI provider call failed — {e}"


# ======================================================================
# Per-figure named tools — one MCP tool per dashboard visual. These wrap
# backend.figures (the same functions the REST /api/v1/figures/* endpoints
# call), so every chart, map and table has a proper, self-describing tool.
# The generic tools above remain as broad aliases.
# ======================================================================
_FIG = READ_ONLY_ANNOTATIONS
_GRAN = "Bucket size: 'D' daily, 'W' weekly, 'M' monthly."


def _fdict(filters: Optional[TripFilters]) -> dict:
    return filters.model_dump() if filters else {}


# ---- Executive Overview ----
@mcp.tool(name="tta_kpi_summary", annotations={"title": "KPI Cards", **_FIG})
def tta_kpi_summary(filters: Optional[TripFilters] = None) -> str:
    """Executive Overview KPI cards: headline KPI block with prior-window deltas."""
    return _json(figures.kpi_summary(_df(filters), _fdict(filters)))


@mcp.tool(name="tta_dispatch_volume_trend", annotations={"title": "Dispatch Volume Trend", **_FIG})
def tta_dispatch_volume_trend(granularity: str = Field(default="D", description=_GRAN),
                              filters: Optional[TripFilters] = None) -> str:
    """Dispatch-volume chart: trips per period plus a moving average."""
    return _json(figures.dispatch_volume_trend(_df(filters), granularity))


@mcp.tool(name="tta_otd_vs_target", annotations={"title": "OTD vs Target", **_FIG})
def tta_otd_vs_target(filters: Optional[TripFilters] = None) -> str:
    """OTD gauge: on-time-delivery % vs the configured target, with the gap."""
    from backend.settings_store import get_settings
    tgt = float(get_settings().get("otd_target_pct", 95))
    return _json(figures.otd_vs_target(_df(filters), _fdict(filters), tgt))


@mcp.tool(name="tta_transit_vs_otd_trend", annotations={"title": "Transit vs OTD Trend", **_FIG})
def tta_transit_vs_otd_trend(granularity: str = Field(default="D", description=_GRAN),
                             filters: Optional[TripFilters] = None) -> str:
    """Dual-axis line: average transit hours vs OTD % per period."""
    return _json(figures.transit_vs_otd_trend(_df(filters), granularity))


@mcp.tool(name="tta_delivery_status_split", annotations={"title": "Delivery Status Split", **_FIG})
def tta_delivery_status_split(filters: Optional[TripFilters] = None) -> str:
    """Delivery-status donut: on-time vs delayed counts and shares."""
    return _json(figures.delivery_status_split(_df(filters)))


@mcp.tool(name="tta_top_destinations", annotations={"title": "Top Destinations", **_FIG})
def tta_top_destinations(limit: int = Field(default=10, ge=1, le=100), filters: Optional[TripFilters] = None) -> str:
    """Top-destinations bar: top-N destinations by trip volume with OTD %."""
    return _json(figures.top_destinations(_df(filters), limit))


@mcp.tool(name="tta_transporter_volume_share", annotations={"title": "Transporter Volume Share", **_FIG})
def tta_transporter_volume_share(limit: int = Field(default=10, ge=1, le=100), filters: Optional[TripFilters] = None) -> str:
    """Volume-share pie: top-N transporters by share of trips."""
    return _json(figures.transporter_volume_share(_df(filters), limit))


@mcp.tool(name="tta_trip_lifecycle_funnel", annotations={"title": "Trip Lifecycle Funnel", **_FIG})
def tta_trip_lifecycle_funnel(filters: Optional[TripFilters] = None) -> str:
    """Funnel: trip counts at each lifecycle stage (booked→departed→…→delivered)."""
    return _json(figures.trip_lifecycle_funnel(_df(filters)))


# ---- Time & Trends ----
@mcp.tool(name="tta_otd_trend", annotations={"title": "OTD Trend", **_FIG})
def tta_otd_trend(granularity: str = Field(default="D", description=_GRAN), filters: Optional[TripFilters] = None) -> str:
    """OTD trend line: on-time-delivery % per period."""
    return _json(figures.otd_trend(_df(filters), granularity))


@mcp.tool(name="tta_transit_detention_trend", annotations={"title": "Transit & Detention Trend", **_FIG})
def tta_transit_detention_trend(granularity: str = Field(default="D", description=_GRAN), filters: Optional[TripFilters] = None) -> str:
    """Average transit and detention hours per period."""
    return _json(figures.transit_detention_trend(_df(filters), granularity))


@mcp.tool(name="tta_dispatch_lead_trend", annotations={"title": "Dispatch Lead-Time Trend", **_FIG})
def tta_dispatch_lead_trend(granularity: str = Field(default="D", description=_GRAN), filters: Optional[TripFilters] = None) -> str:
    """Average dispatch lead time (booking → gate-out) per period."""
    return _json(figures.dispatch_lead_trend(_df(filters), granularity))


@mcp.tool(name="tta_distance_trend", annotations={"title": "Distance Trend", **_FIG})
def tta_distance_trend(granularity: str = Field(default="D", description=_GRAN), filters: Optional[TripFilters] = None) -> str:
    """Total kilometres driven per period."""
    return _json(figures.distance_trend(_df(filters), granularity))


@mcp.tool(name="tta_speed_violations_trend", annotations={"title": "Speed-Violations Trend", **_FIG})
def tta_speed_violations_trend(granularity: str = Field(default="D", description=_GRAN), filters: Optional[TripFilters] = None) -> str:
    """Speed-violation events per period."""
    return _json(figures.speed_violations_trend(_df(filters), granularity))


# ---- Transporter Scorecard ----
@mcp.tool(name="tta_transporter_scorecard", annotations={"title": "Transporter League Table", **_FIG})
def tta_transporter_scorecard(min_trips: int = Field(default=1, ge=1), limit: int = Field(default=50, ge=1, le=200),
                              filters: Optional[TripFilters] = None) -> str:
    """League table: full per-transporter scorecard."""
    return _json(figures.transporter_scorecard(_df(filters), min_trips, limit))


@mcp.tool(name="tta_transporter_best_worst_otd", annotations={"title": "Best/Worst OTD Transporters", **_FIG})
def tta_transporter_best_worst_otd(min_trips: int = Field(default=20, ge=1), n: int = Field(default=10, ge=1, le=50),
                                   filters: Optional[TripFilters] = None) -> str:
    """The best- and worst-OTD carriers among those with enough trips."""
    return _json(figures.transporter_best_worst_otd(_df(filters), min_trips, n))


@mcp.tool(name="tta_transporter_risk_map", annotations={"title": "Transporter Risk Map", **_FIG})
def tta_transporter_risk_map(min_trips: int = Field(default=20, ge=1), filters: Optional[TripFilters] = None) -> str:
    """Risk bubble map: transit vs OTD per transporter (bubble=trips, colour=detention)."""
    return _json(figures.transporter_risk_map(_df(filters), min_trips))


@mcp.tool(name="tta_transporter_transit_boxplot", annotations={"title": "Transit Spread per Transporter", **_FIG})
def tta_transporter_transit_boxplot(top: int = Field(default=10, ge=1, le=30), filters: Optional[TripFilters] = None) -> str:
    """Box-plot samples of transit time for the top-N transporters by volume."""
    return _json(figures.transporter_transit_boxplot(_df(filters), top))


# ---- Routes & Lanes ----
@mcp.tool(name="tta_lane_performance", annotations={"title": "Lane Performance Table", **_FIG})
def tta_lane_performance(min_trips: int = Field(default=3, ge=1), limit: int = Field(default=50, ge=1, le=200),
                         filters: Optional[TripFilters] = None) -> str:
    """Lane table: full per-destination performance."""
    return _json(figures.lane_performance(_df(filters), min_trips, limit))


@mcp.tool(name="tta_distance_vs_transit", annotations={"title": "Distance vs Transit", **_FIG})
def tta_distance_vs_transit(min_trips: int = Field(default=3, ge=1), filters: Optional[TripFilters] = None) -> str:
    """Regression scatter: per-lane distance vs transit + a fitted network pace."""
    return _json(figures.distance_vs_transit(_df(filters), min_trips))


@mcp.tool(name="tta_slowest_corridors", annotations={"title": "Slowest Corridors", **_FIG})
def tta_slowest_corridors(min_trips: int = Field(default=10, ge=1), n: int = Field(default=10, ge=1, le=50),
                          filters: Optional[TripFilters] = None) -> str:
    """Lanes with the lowest effective km/h, door to door."""
    return _json(figures.slowest_corridors(_df(filters), min_trips, n))


@mcp.tool(name="tta_schedule_variance_lanes", annotations={"title": "Schedule-Variance Lanes", **_FIG})
def tta_schedule_variance_lanes(min_trips: int = Field(default=5, ge=1), n: int = Field(default=10, ge=1, le=50),
                                filters: Optional[TripFilters] = None) -> str:
    """Lanes running most behind plan and most ahead of plan."""
    return _json(figures.schedule_variance_lanes(_df(filters), min_trips, n))


@mcp.tool(name="tta_lane_volume_treemap", annotations={"title": "Lane Volume Treemap", **_FIG})
def tta_lane_volume_treemap(top: int = Field(default=40, ge=1, le=200), filters: Optional[TripFilters] = None) -> str:
    """Treemap data: destination volume + OTD."""
    return _json(figures.lane_volume_treemap(_df(filters), top))


# ---- Geo ----
@mcp.tool(name="tta_geo_points", annotations={"title": "Geo Destination Points", **_FIG})
def tta_geo_points(filters: Optional[TripFilters] = None) -> str:
    """Map data: origin + per-destination points with performance (flow/bubble map)."""
    return _json(figures.geo_points(_df(filters)))


# ---- Heatmaps ----
@mcp.tool(name="tta_departure_rhythm", annotations={"title": "Departure Rhythm", **_FIG})
def tta_departure_rhythm(filters: Optional[TripFilters] = None) -> str:
    """Weekday × hour departure matrix (7×24)."""
    return _json(figures.departure_rhythm(_df(filters)))


@mcp.tool(name="tta_transporter_month_heatmap", annotations={"title": "Transporter × Month Heatmap", **_FIG})
def tta_transporter_month_heatmap(metric: str = Field(default="otd_pct", description="'otd_pct','trips','transit_hours','detention_hours','gps_uptime'"),
                                  top: int = Field(default=12, ge=1, le=50), filters: Optional[TripFilters] = None) -> str:
    """Top transporters × month matrix for a chosen metric."""
    return _json(figures.transporter_month_heatmap(_df(filters), metric, top))


@mcp.tool(name="tta_destination_month_heatmap", annotations={"title": "Destination × Month Heatmap", **_FIG})
def tta_destination_month_heatmap(top: int = Field(default=15, ge=1, le=50), filters: Optional[TripFilters] = None) -> str:
    """Top destinations × month trip-volume matrix."""
    return _json(figures.destination_month_heatmap(_df(filters), top))


@mcp.tool(name="tta_correlation_matrix", annotations={"title": "Correlation Matrix", **_FIG})
def tta_correlation_matrix(filters: Optional[TripFilters] = None) -> str:
    """Correlation matrix across numeric trip metrics."""
    return _json(figures.correlation_matrix(_df(filters)))


# ---- Distributions & Outliers ----
@mcp.tool(name="tta_metric_distribution", annotations={"title": "Metric Distribution", **_FIG})
def tta_metric_distribution(metric: str = Field(description=f"One of: {', '.join(analytics.NUMERIC_METRICS)}"),
                            bins: int = Field(default=20, ge=5, le=60), filters: Optional[TripFilters] = None) -> str:
    """Histogram/violin/ECDF source: summary stats + histogram for one metric."""
    return _json(figures.metric_distribution(_df(filters), metric, bins))


@mcp.tool(name="tta_metric_boxplot_by_group", annotations={"title": "Metric Box Plot by Group", **_FIG})
def tta_metric_boxplot_by_group(group_by: str = Field(default="transporter", description="'transporter','destination','vehicle_category','own_market','consignor','device_type'"),
                                metric: str = Field(default="transit_hours", description=f"One of: {', '.join(analytics.NUMERIC_METRICS)}"),
                                top: int = Field(default=10, ge=1, le=30), filters: Optional[TripFilters] = None) -> str:
    """Grouped box-plot data: (group, value) samples for the top-N groups."""
    return _json(figures.metric_boxplot_by_group(_df(filters), group_by, metric, top))


@mcp.tool(name="tta_transit_outliers", annotations={"title": "Transit Outliers", **_FIG})
def tta_transit_outliers(z: float = Field(default=3.0, ge=1.0, le=6.0), limit: int = Field(default=50, ge=1, le=200),
                         filters: Optional[TripFilters] = None) -> str:
    """Per-lane z-score anomalies: trips whose transit is far from their lane average."""
    return _json(figures.transit_outliers(_df(filters), z, limit))


# ---- Fleet & Vehicles ----
@mcp.tool(name="tta_own_vs_market", annotations={"title": "Own vs Market", **_FIG})
def tta_own_vs_market(filters: Optional[TripFilters] = None) -> str:
    """Own fleet vs market-hired vehicles scorecard."""
    return _json(figures.own_vs_market(_df(filters)))


@mcp.tool(name="tta_vehicle_category_mix", annotations={"title": "Vehicle Category Mix", **_FIG})
def tta_vehicle_category_mix(filters: Optional[TripFilters] = None) -> str:
    """Trips and performance by vehicle category."""
    return _json(figures.vehicle_category_mix(_df(filters)))


@mcp.tool(name="tta_gps_device_types", annotations={"title": "GPS Device Types", **_FIG})
def tta_gps_device_types(filters: Optional[TripFilters] = None) -> str:
    """Trips and GPS quality by device type (permanent vs rental)."""
    return _json(figures.gps_device_types(_df(filters)))


@mcp.tool(name="tta_asset_make_performance", annotations={"title": "Asset Make Performance", **_FIG})
def tta_asset_make_performance(filters: Optional[TripFilters] = None) -> str:
    """Trips and OTD by asset make, where telematics metadata exists."""
    return _json(figures.asset_make_performance(_df(filters)))


@mcp.tool(name="tta_top_violating_vehicles", annotations={"title": "Top Violating Vehicles", **_FIG})
def tta_top_violating_vehicles(limit: int = Field(default=15, ge=1, le=100), filters: Optional[TripFilters] = None) -> str:
    """Vehicles with the most speed-violation events."""
    return _json(figures.top_violating_vehicles(_df(filters), limit))


@mcp.tool(name="tta_low_gps_vehicles", annotations={"title": "Low GPS-Uptime Vehicles", **_FIG})
def tta_low_gps_vehicles(limit: int = Field(default=15, ge=1, le=100), filters: Optional[TripFilters] = None) -> str:
    """Vehicles with GPS uptime below 80%."""
    return _json(figures.low_gps_vehicles(_df(filters), limit))


@mcp.tool(name="tta_gps_uptime_distribution", annotations={"title": "GPS Uptime Distribution", **_FIG})
def tta_gps_uptime_distribution(bins: int = Field(default=40, ge=5, le=60), filters: Optional[TripFilters] = None) -> str:
    """Distribution of GPS uptime across trips."""
    return _json(figures.gps_uptime_distribution(_df(filters), bins))


# ---- Records ----
@mcp.tool(name="tta_trip_records", annotations={"title": "Trip Records", **_FIG})
def tta_trip_records(limit: int = Field(default=100, ge=1, le=5000), filters: Optional[TripFilters] = None) -> str:
    """Data Explorer table: trip-level records, newest first."""
    return _json(figures.trip_records(_df(filters), limit))


def main() -> None:
    if "--http" in sys.argv:
        if "--port" in sys.argv:
            mcp.settings.port = int(sys.argv[sys.argv.index("--port") + 1])
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # stdio


if __name__ == "__main__":
    main()
