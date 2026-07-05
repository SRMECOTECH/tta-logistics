"""Figure-level data providers — one function per dashboard visual.

Every chart, map and table in the Streamlit dashboard has a matching function
here that returns *exactly* the data that figure plots. Both the REST API
(`backend/figures_api.py`) and the MCP server (`mcp_server/server.py`) call
these, so the named REST endpoint and the named MCP tool for a figure always
return identical data. All functions take an already-filtered DataFrame and
reuse `backend/analytics.py` — this module adds naming and light shaping only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import analytics

RECORD_COLS = [
    "trip_id", "dept_dt", "transporter", "vehicle_no", "vehicle_category", "own_market",
    "consignor", "consignee", "destination", "distance_km", "transit_hours",
    "planned_transit_hours", "detention_hours", "avg_speed_kmph", "speed_violations",
    "gps_uptime", "delivery_status", "delivery_delta_hours", "driver_name", "trip_closed_reason",
]


# ============================================================ Executive Overview
def kpi_summary(df: pd.DataFrame, f: dict) -> dict:
    """KPI cards block (current + previous window + deltas)."""
    return analytics.kpis(df, f)


def dispatch_volume_trend(df: pd.DataFrame, granularity: str = "D", ma_window: int = 7) -> list[dict]:
    """Trips per period + a moving average (the daily dispatch-volume chart)."""
    d = pd.DataFrame(analytics.timeseries(df, granularity))
    if d.empty:
        return []
    d["moving_avg"] = d["trips"].rolling(ma_window, min_periods=1).mean().round(1)
    return d[["period", "trips", "moving_avg"]].to_dict("records")


def otd_vs_target(df: pd.DataFrame, f: dict, target_pct: float) -> dict:
    """OTD % vs the company target (the gauge)."""
    otd = analytics.kpis(df, f)["current"].get("otd_pct")
    return {
        "otd_pct": otd, "target_pct": target_pct,
        "gap_pct": round(otd - target_pct, 1) if otd is not None else None,
        "meets_target": bool(otd is not None and otd >= target_pct),
    }


def transit_vs_otd_trend(df: pd.DataFrame, granularity: str = "D") -> list[dict]:
    """Average transit hours vs OTD % per period (dual-axis line)."""
    return [{"period": r["period"], "avg_transit_hours": r.get("avg_transit_hours"),
             "otd_pct": r.get("otd_pct")} for r in analytics.timeseries(df, granularity)]


def delivery_status_split(df: pd.DataFrame) -> dict:
    """On-time vs delayed counts and shares (the delivery-status donut)."""
    s = df["is_on_time"].dropna()
    n = int(len(s))
    on = int(s.sum()) if n else 0
    return {"total": n, "on_time": on, "delayed": n - on,
            "on_time_pct": round(100 * on / n, 1) if n else None,
            "delayed_pct": round(100 * (n - on) / n, 1) if n else None}


def top_destinations(df: pd.DataFrame, limit: int = 10) -> list[dict]:
    """Top-N destinations by trip volume with OTD % (the top-destinations bar)."""
    rows = analytics.group_summary(df, "destination", 1)[:limit]
    return [{"destination": r["destination"], "trips": r["trips"], "otd_pct": r.get("otd_pct")} for r in rows]


def transporter_volume_share(df: pd.DataFrame, limit: int = 10) -> list[dict]:
    """Top-N transporters by volume share (the transporter share pie)."""
    rows = analytics.group_summary(df, "transporter", 1)[:limit]
    return [{"transporter": r["transporter"], "trips": r["trips"], "share_pct": r.get("share_pct")} for r in rows]


def trip_lifecycle_funnel(df: pd.DataFrame) -> list[dict]:
    """Trip counts at each lifecycle stage (the funnel)."""
    return analytics.funnel(df)


# ==================================================================== Trends
def otd_trend(df: pd.DataFrame, granularity: str = "D") -> list[dict]:
    """OTD % per period (the OTD trend line)."""
    return [{"period": r["period"], "otd_pct": r.get("otd_pct")} for r in analytics.timeseries(df, granularity)]


def transit_detention_trend(df: pd.DataFrame, granularity: str = "D") -> list[dict]:
    """Average transit and detention hours per period."""
    return [{"period": r["period"], "avg_transit_hours": r.get("avg_transit_hours"),
             "avg_detention_hours": r.get("avg_detention_hours")} for r in analytics.timeseries(df, granularity)]


def dispatch_lead_trend(df: pd.DataFrame, granularity: str = "D") -> list[dict]:
    """Average dispatch lead time (booking → gate-out) per period."""
    return [{"period": r["period"], "avg_dispatch_lead_hours": r.get("avg_dispatch_lead_hours")}
            for r in analytics.timeseries(df, granularity)]


def distance_trend(df: pd.DataFrame, granularity: str = "D") -> list[dict]:
    """Total kilometres driven per period."""
    return [{"period": r["period"], "total_km": r.get("total_km")} for r in analytics.timeseries(df, granularity)]


def speed_violations_trend(df: pd.DataFrame, granularity: str = "D") -> list[dict]:
    """Speed-violation events per period."""
    return [{"period": r["period"], "speed_violations": r.get("speed_violations")}
            for r in analytics.timeseries(df, granularity)]


# ============================================================ Transporters
def transporter_scorecard(df: pd.DataFrame, min_trips: int = 1, limit: int = 200) -> list[dict]:
    """Full per-transporter league table."""
    return analytics.group_summary(df, "transporter", min_trips)[:limit]


def transporter_best_worst_otd(df: pd.DataFrame, min_trips: int = 20, n: int = 10) -> dict:
    """Best- and worst-OTD transporters among those with enough trips."""
    rows = [r for r in analytics.group_summary(df, "transporter", min_trips) if r.get("otd_pct") is not None]
    slim = lambda L: [{"transporter": r["transporter"], "otd_pct": r["otd_pct"], "trips": r["trips"]} for r in L]
    return {"min_trips": min_trips,
            "best": slim(sorted(rows, key=lambda r: r["otd_pct"], reverse=True)[:n]),
            "worst": slim(sorted(rows, key=lambda r: r["otd_pct"])[:n])}


def transporter_risk_map(df: pd.DataFrame, min_trips: int = 20) -> list[dict]:
    """Transit vs OTD bubble data per transporter (bubble=trips, colour=detention)."""
    rows = analytics.group_summary(df, "transporter", min_trips)
    return [{"transporter": r["transporter"], "avg_transit_hours": r.get("avg_transit_hours"),
             "otd_pct": r.get("otd_pct"), "trips": r["trips"],
             "avg_detention_hours": r.get("avg_detention_hours")} for r in rows]


def transporter_transit_boxplot(df: pd.DataFrame, top: int = 10) -> list[dict]:
    """Transit-time spread per transporter (top-N by volume) for box plots."""
    return analytics.boxdata(df, "transporter", "transit_hours", top)


# =============================================================== Routes & Lanes
def lane_performance(df: pd.DataFrame, min_trips: int = 3, limit: int = 200) -> list[dict]:
    """Full per-destination (lane) performance table."""
    return analytics.group_summary(df, "destination", min_trips)[:limit]


def distance_vs_transit(df: pd.DataFrame, min_trips: int = 3) -> dict:
    """Distance vs transit per lane + a fitted network pace (the regression scatter)."""
    rows = [r for r in analytics.group_summary(df, "destination", min_trips)
            if r.get("avg_distance_km") is not None and r.get("avg_transit_hours") is not None]
    points = [{"destination": r["destination"], "avg_distance_km": r["avg_distance_km"],
               "avg_transit_hours": r["avg_transit_hours"], "trips": r["trips"],
               "otd_pct": r.get("otd_pct")} for r in rows]
    trend: dict = {}
    if len(points) > 3:
        xs = np.array([p["avg_distance_km"] for p in points], dtype=float)
        ys = np.array([p["avg_transit_hours"] for p in points], dtype=float)
        slope, intercept = np.polyfit(xs, ys, 1)
        trend = {"pace_hours_per_km": round(float(slope), 4),
                 "implied_kmph": round(1 / slope, 1) if slope else None,
                 "intercept_hours": round(float(intercept), 2)}
    return {"points": points, "trend": trend}


def slowest_corridors(df: pd.DataFrame, min_trips: int = 10, n: int = 10) -> list[dict]:
    """Lanes with the lowest effective km/h (door-to-door)."""
    rows = [r for r in analytics.group_summary(df, "destination", min_trips) if r.get("avg_speed_kmph") is not None]
    rows = sorted(rows, key=lambda r: r["avg_speed_kmph"])[:n]
    return [{"destination": r["destination"], "avg_speed_kmph": r["avg_speed_kmph"],
             "avg_transit_hours": r.get("avg_transit_hours"), "trips": r["trips"]} for r in rows]


def schedule_variance_lanes(df: pd.DataFrame, min_trips: int = 5, n: int = 10) -> dict:
    """Lanes running most behind plan and most ahead of plan."""
    rows = [r for r in analytics.group_summary(df, "destination", min_trips)
            if r.get("schedule_variance_hours") is not None]
    slim = lambda L: [{"destination": r["destination"], "schedule_variance_hours": r["schedule_variance_hours"],
                       "avg_transit_hours": r.get("avg_transit_hours"),
                       "avg_planned_transit_hours": r.get("avg_planned_transit_hours"),
                       "trips": r["trips"]} for r in L]
    return {"behind_plan": slim(sorted(rows, key=lambda r: r["schedule_variance_hours"], reverse=True)[:n]),
            "ahead_of_plan": slim(sorted(rows, key=lambda r: r["schedule_variance_hours"])[:n])}


def lane_volume_treemap(df: pd.DataFrame, top: int = 40) -> list[dict]:
    """Destination volume + OTD for the lane treemap."""
    rows = analytics.group_summary(df, "destination", 1)[:top]
    return [{"destination": r["destination"], "trips": r["trips"], "otd_pct": r.get("otd_pct")} for r in rows]


# ========================================================================= Geo
def geo_points(df: pd.DataFrame) -> dict:
    """Origin + per-destination map points with performance."""
    return analytics.geo_points(df)


# ==================================================================== Heatmaps
def departure_rhythm(df: pd.DataFrame) -> dict:
    """Weekday × hour departure matrix."""
    return analytics.heatmap_dow_hour(df)


def transporter_month_heatmap(df: pd.DataFrame, metric: str = "otd_pct", top: int = 12) -> dict:
    """Top transporters × month matrix for a chosen metric."""
    return analytics.heatmap_pivot(df, "transporter", "dept_month", metric, top)


def destination_month_heatmap(df: pd.DataFrame, top: int = 15) -> dict:
    """Top destinations × month trip-volume matrix."""
    return analytics.heatmap_pivot(df, "destination", "dept_month", "trips", top)


def correlation_matrix(df: pd.DataFrame) -> dict:
    """Correlation matrix across numeric trip metrics."""
    return analytics.correlation(df)


# ========================================================= Distributions & Outliers
def metric_distribution(df: pd.DataFrame, metric: str, bins: int = 20) -> dict:
    """Summary stats + histogram for one numeric metric (histogram/violin/ECDF)."""
    if metric not in analytics.NUMERIC_METRICS:
        return {"error": f"metric must be one of {analytics.NUMERIC_METRICS}"}
    dist = analytics.distribution(df, metric, max_points=100000)
    values = dist["values"]
    hist: list[dict] = []
    if values:
        counts, edges = np.histogram(values, bins=bins)
        hist = [{"bin_start": round(float(edges[i]), 2), "bin_end": round(float(edges[i + 1]), 2),
                 "count": int(c)} for i, c in enumerate(counts)]
    return {"metric": metric, "stats": dist["stats"], "histogram": hist}


def metric_boxplot_by_group(df: pd.DataFrame, group_by: str = "transporter",
                            metric: str = "transit_hours", top: int = 10) -> list[dict]:
    """(group, value) samples for grouped box plots."""
    return analytics.boxdata(df, group_by, metric, top)


def transit_outliers(df: pd.DataFrame, z: float = 3.0, limit: int = 200) -> list[dict]:
    """Trips whose transit is anomalous vs their lane's average (per-lane z-score)."""
    return analytics.outliers(df, z)[:limit]


# ================================================================ Fleet & Vehicles
def own_vs_market(df: pd.DataFrame) -> list[dict]:
    """Own fleet vs market-hired vehicles scorecard."""
    return analytics.group_summary(df, "own_market")


def vehicle_category_mix(df: pd.DataFrame) -> list[dict]:
    """Trips and performance by vehicle category."""
    return analytics.group_summary(df, "vehicle_category")


def gps_device_types(df: pd.DataFrame) -> list[dict]:
    """Trips and GPS quality by device type (permanent vs rental)."""
    return analytics.group_summary(df, "device_type")


def asset_make_performance(df: pd.DataFrame) -> list[dict]:
    """Trips and OTD by asset make (where telematics metadata exists)."""
    return analytics.group_summary(df.dropna(subset=["asset_make"]), "asset_make")


def top_violating_vehicles(df: pd.DataFrame, limit: int = 15) -> list[dict]:
    """Vehicles with the most speed-violation events."""
    return analytics.fleet(df)["top_violating_vehicles"][:limit]


def low_gps_vehicles(df: pd.DataFrame, limit: int = 15) -> list[dict]:
    """Vehicles with GPS uptime below 80%."""
    return analytics.fleet(df)["low_gps_vehicles"][:limit]


def gps_uptime_distribution(df: pd.DataFrame, bins: int = 40) -> dict:
    """Distribution of GPS uptime across trips."""
    return metric_distribution(df, "gps_uptime", bins)


# ======================================================================= Records
def trip_records(df: pd.DataFrame, limit: int = 500) -> list[dict]:
    """Trip-level records, newest first (the Data Explorer table)."""
    out = df.sort_values("dept_dt", ascending=False).head(min(limit, 5000))[RECORD_COLS]
    return analytics.clean_records(out)
