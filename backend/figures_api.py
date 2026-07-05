"""Named, per-figure REST endpoints — one route per dashboard visual.

`build_figures_router(filtered_df, require_api_key)` returns an APIRouter with a
route for every figure in `backend/figures.py`, grouped by dashboard page. It is
mounted by `backend/main.py` at `/api/v1` (and `/api` as a hidden alias), so each
figure is reachable at e.g. `GET /api/v1/figures/otd_trend`. The router shares the
same API-key security and filter parsing as the rest of the API.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Security

from . import figures
from .settings_store import get_settings

# tag names (also registered in main.OPENAPI_TAGS for descriptions)
T_OVERVIEW = "Figures · Overview"
T_TRENDS = "Figures · Trends"
T_TRANSPORTERS = "Figures · Transporters"
T_LANES = "Figures · Lanes"
T_GEO = "Figures · Geo"
T_HEATMAPS = "Figures · Heatmaps"
T_STATS = "Figures · Distributions"
T_FLEET = "Figures · Fleet"
T_RECORDS = "Figures · Records"

FIGURE_TAGS = [
    {"name": T_OVERVIEW, "description": "Executive Overview page — one endpoint per figure (KPI cards, gauges, trend, splits, funnel)."},
    {"name": T_TRENDS, "description": "Time & Trends page — one endpoint per trend line."},
    {"name": T_TRANSPORTERS, "description": "Transporter Scorecard page figures."},
    {"name": T_LANES, "description": "Routes & Lanes page figures."},
    {"name": T_GEO, "description": "Geo Intelligence map data."},
    {"name": T_HEATMAPS, "description": "Heatmaps & Correlations page figures."},
    {"name": T_STATS, "description": "Distributions & Outliers page figures."},
    {"name": T_FLEET, "description": "Fleet & Vehicles page figures."},
    {"name": T_RECORDS, "description": "Data Explorer — raw trip records."},
]

_GRAN = Query("D", description="Bucket size: `D` daily, `W` weekly, `M` monthly.")


def build_figures_router(filtered_df, require_api_key) -> APIRouter:
    r = APIRouter(prefix="/figures", dependencies=[Security(require_api_key)])

    # ---------------------------------------------------------- Overview
    @r.get("/kpi_summary", tags=[T_OVERVIEW], summary="KPI cards",
           description="Headline KPI block (current + prior window + deltas) — the Executive Overview cards.")
    def kpi_summary(dff=Depends(filtered_df)):
        df, f = dff
        return figures.kpi_summary(df, f)

    @r.get("/dispatch_volume_trend", tags=[T_OVERVIEW], summary="Daily dispatch volume",
           description="Trips per period plus a moving average — the dispatch-volume area chart.")
    def dispatch_volume_trend(granularity: str = _GRAN, dff=Depends(filtered_df)):
        return figures.dispatch_volume_trend(dff[0], granularity)

    @r.get("/otd_vs_target", tags=[T_OVERVIEW], summary="OTD vs target gauge",
           description="On-time-delivery % against the configured target — the gauge. Includes the gap and a meets-target flag.")
    def otd_vs_target(dff=Depends(filtered_df)):
        df, f = dff
        return figures.otd_vs_target(df, f, float(get_settings().get("otd_target_pct", 95)))

    @r.get("/transit_vs_otd_trend", tags=[T_OVERVIEW], summary="Transit vs OTD trend",
           description="Average transit hours and OTD % per period — the dual-axis line.")
    def transit_vs_otd_trend(granularity: str = _GRAN, dff=Depends(filtered_df)):
        return figures.transit_vs_otd_trend(dff[0], granularity)

    @r.get("/delivery_status_split", tags=[T_OVERVIEW], summary="Delivery status split",
           description="On-time vs delayed counts and shares — the delivery-status donut.")
    def delivery_status_split(dff=Depends(filtered_df)):
        return figures.delivery_status_split(dff[0])

    @r.get("/top_destinations", tags=[T_OVERVIEW], summary="Top destinations",
           description="Top-N destinations by trip volume with OTD % — the top-destinations bar.")
    def top_destinations(limit: int = Query(10, description="How many destinations."), dff=Depends(filtered_df)):
        return figures.top_destinations(dff[0], limit)

    @r.get("/transporter_volume_share", tags=[T_OVERVIEW], summary="Transporter volume share",
           description="Top-N transporters by share of trips — the volume-share pie.")
    def transporter_volume_share(limit: int = Query(10, description="How many transporters."), dff=Depends(filtered_df)):
        return figures.transporter_volume_share(dff[0], limit)

    @r.get("/trip_lifecycle_funnel", tags=[T_OVERVIEW], summary="Trip lifecycle funnel",
           description="Trip counts at each lifecycle stage — the funnel.")
    def trip_lifecycle_funnel(dff=Depends(filtered_df)):
        return figures.trip_lifecycle_funnel(dff[0])

    # ---------------------------------------------------------- Trends
    @r.get("/otd_trend", tags=[T_TRENDS], summary="OTD % trend",
           description="On-time-delivery % per period — the OTD trend line.")
    def otd_trend(granularity: str = _GRAN, dff=Depends(filtered_df)):
        return figures.otd_trend(dff[0], granularity)

    @r.get("/transit_detention_trend", tags=[T_TRENDS], summary="Transit & detention trend",
           description="Average transit and detention hours per period.")
    def transit_detention_trend(granularity: str = _GRAN, dff=Depends(filtered_df)):
        return figures.transit_detention_trend(dff[0], granularity)

    @r.get("/dispatch_lead_trend", tags=[T_TRENDS], summary="Dispatch lead-time trend",
           description="Average booking→gate-out hours per period.")
    def dispatch_lead_trend(granularity: str = _GRAN, dff=Depends(filtered_df)):
        return figures.dispatch_lead_trend(dff[0], granularity)

    @r.get("/distance_trend", tags=[T_TRENDS], summary="Distance trend",
           description="Total kilometres driven per period.")
    def distance_trend(granularity: str = _GRAN, dff=Depends(filtered_df)):
        return figures.distance_trend(dff[0], granularity)

    @r.get("/speed_violations_trend", tags=[T_TRENDS], summary="Speed-violations trend",
           description="Speed-violation events per period.")
    def speed_violations_trend(granularity: str = _GRAN, dff=Depends(filtered_df)):
        return figures.speed_violations_trend(dff[0], granularity)

    # ---------------------------------------------------------- Transporters
    @r.get("/transporter_scorecard", tags=[T_TRANSPORTERS], summary="Transporter league table",
           description="Full per-transporter scorecard — the league table.")
    def transporter_scorecard(min_trips: int = Query(1), limit: int = Query(200), dff=Depends(filtered_df)):
        return figures.transporter_scorecard(dff[0], min_trips, limit)

    @r.get("/transporter_best_worst_otd", tags=[T_TRANSPORTERS], summary="Best/worst OTD transporters",
           description="Best- and worst-OTD carriers among those with enough trips — the two ranking bars.")
    def transporter_best_worst_otd(min_trips: int = Query(20), n: int = Query(10), dff=Depends(filtered_df)):
        return figures.transporter_best_worst_otd(dff[0], min_trips, n)

    @r.get("/transporter_risk_map", tags=[T_TRANSPORTERS], summary="Transporter risk map",
           description="Transit vs OTD bubble data per transporter (bubble=trips, colour=detention).")
    def transporter_risk_map(min_trips: int = Query(20), dff=Depends(filtered_df)):
        return figures.transporter_risk_map(dff[0], min_trips)

    @r.get("/transporter_transit_boxplot", tags=[T_TRANSPORTERS], summary="Transit spread per transporter",
           description="Transit-time samples for the top-N carriers — box-plot data.")
    def transporter_transit_boxplot(top: int = Query(10), dff=Depends(filtered_df)):
        return figures.transporter_transit_boxplot(dff[0], top)

    # ---------------------------------------------------------- Lanes
    @r.get("/lane_performance", tags=[T_LANES], summary="Lane performance table",
           description="Full per-destination (lane) performance table.")
    def lane_performance(min_trips: int = Query(3), limit: int = Query(200), dff=Depends(filtered_df)):
        return figures.lane_performance(dff[0], min_trips, limit)

    @r.get("/distance_vs_transit", tags=[T_LANES], summary="Distance vs transit",
           description="Per-lane distance vs transit points plus a fitted network pace — the regression scatter.")
    def distance_vs_transit(min_trips: int = Query(3), dff=Depends(filtered_df)):
        return figures.distance_vs_transit(dff[0], min_trips)

    @r.get("/slowest_corridors", tags=[T_LANES], summary="Slowest corridors",
           description="Lanes with the lowest effective km/h, door to door.")
    def slowest_corridors(min_trips: int = Query(10), n: int = Query(10), dff=Depends(filtered_df)):
        return figures.slowest_corridors(dff[0], min_trips, n)

    @r.get("/schedule_variance_lanes", tags=[T_LANES], summary="Schedule-variance lanes",
           description="Lanes running most behind plan and most ahead of plan.")
    def schedule_variance_lanes(min_trips: int = Query(5), n: int = Query(10), dff=Depends(filtered_df)):
        return figures.schedule_variance_lanes(dff[0], min_trips, n)

    @r.get("/lane_volume_treemap", tags=[T_LANES], summary="Lane volume treemap",
           description="Destination volume + OTD for the treemap.")
    def lane_volume_treemap(top: int = Query(40), dff=Depends(filtered_df)):
        return figures.lane_volume_treemap(dff[0], top)

    # ---------------------------------------------------------- Geo
    @r.get("/geo_points", tags=[T_GEO], summary="Geo destination points",
           description="Origin + per-destination map points with performance — the flow/bubble map data.")
    def geo_points(dff=Depends(filtered_df)):
        return figures.geo_points(dff[0])

    # ---------------------------------------------------------- Heatmaps
    @r.get("/departure_rhythm", tags=[T_HEATMAPS], summary="Departure rhythm (weekday×hour)",
           description="7×24 weekday × hour-of-day departure matrix.")
    def departure_rhythm(dff=Depends(filtered_df)):
        return figures.departure_rhythm(dff[0])

    @r.get("/transporter_month_heatmap", tags=[T_HEATMAPS], summary="Transporter × month heatmap",
           description="Top transporters × month matrix for a chosen metric.")
    def transporter_month_heatmap(metric: str = Query("otd_pct", description="`otd_pct`, `trips`, `transit_hours`, `detention_hours`, `gps_uptime`."),
                                  top: int = Query(12), dff=Depends(filtered_df)):
        return figures.transporter_month_heatmap(dff[0], metric, top)

    @r.get("/destination_month_heatmap", tags=[T_HEATMAPS], summary="Destination × month heatmap",
           description="Top destinations × month trip-volume matrix.")
    def destination_month_heatmap(top: int = Query(15), dff=Depends(filtered_df)):
        return figures.destination_month_heatmap(dff[0], top)

    @r.get("/correlation_matrix", tags=[T_HEATMAPS], summary="Correlation matrix",
           description="Correlation across numeric trip metrics.")
    def correlation_matrix(dff=Depends(filtered_df)):
        return figures.correlation_matrix(dff[0])

    # ---------------------------------------------------------- Distributions
    @r.get("/metric_distribution", tags=[T_STATS], summary="Metric distribution",
           description="Stats + histogram for one numeric metric — the histogram/violin/ECDF source.")
    def metric_distribution(metric: str = Query("transit_hours", description=f"One of: {', '.join(figures.analytics.NUMERIC_METRICS)}."),
                            bins: int = Query(20), dff=Depends(filtered_df)):
        return figures.metric_distribution(dff[0], metric, bins)

    @r.get("/metric_boxplot_by_group", tags=[T_STATS], summary="Metric box plot by group",
           description="(group, value) samples for grouped box plots.")
    def metric_boxplot_by_group(group_by: str = Query("transporter"), metric: str = Query("transit_hours"),
                                top: int = Query(10), dff=Depends(filtered_df)):
        return figures.metric_boxplot_by_group(dff[0], group_by, metric, top)

    @r.get("/transit_outliers", tags=[T_STATS], summary="Transit outliers",
           description="Trips whose transit is anomalous vs their lane average — per-lane z-score anomalies.")
    def transit_outliers(z: float = Query(3.0), limit: int = Query(200), dff=Depends(filtered_df)):
        return figures.transit_outliers(dff[0], z, limit)

    # ---------------------------------------------------------- Fleet
    @r.get("/own_vs_market", tags=[T_FLEET], summary="Own vs market",
           description="Own fleet vs market-hired vehicles scorecard.")
    def own_vs_market(dff=Depends(filtered_df)):
        return figures.own_vs_market(dff[0])

    @r.get("/vehicle_category_mix", tags=[T_FLEET], summary="Vehicle category mix",
           description="Trips and performance by vehicle category.")
    def vehicle_category_mix(dff=Depends(filtered_df)):
        return figures.vehicle_category_mix(dff[0])

    @r.get("/gps_device_types", tags=[T_FLEET], summary="GPS device types",
           description="Trips and GPS quality by device type (permanent vs rental).")
    def gps_device_types(dff=Depends(filtered_df)):
        return figures.gps_device_types(dff[0])

    @r.get("/asset_make_performance", tags=[T_FLEET], summary="Asset make performance",
           description="Trips and OTD by asset make, where telematics metadata exists.")
    def asset_make_performance(dff=Depends(filtered_df)):
        return figures.asset_make_performance(dff[0])

    @r.get("/top_violating_vehicles", tags=[T_FLEET], summary="Top speed-violating vehicles",
           description="Vehicles with the most speed-violation events.")
    def top_violating_vehicles(limit: int = Query(15), dff=Depends(filtered_df)):
        return figures.top_violating_vehicles(dff[0], limit)

    @r.get("/low_gps_vehicles", tags=[T_FLEET], summary="Low GPS-uptime vehicles",
           description="Vehicles with GPS uptime below 80%.")
    def low_gps_vehicles(limit: int = Query(15), dff=Depends(filtered_df)):
        return figures.low_gps_vehicles(dff[0], limit)

    @r.get("/gps_uptime_distribution", tags=[T_FLEET], summary="GPS uptime distribution",
           description="Distribution of GPS uptime across trips.")
    def gps_uptime_distribution(bins: int = Query(40), dff=Depends(filtered_df)):
        return figures.gps_uptime_distribution(dff[0], bins)

    # ---------------------------------------------------------- Records
    @r.get("/trip_records", tags=[T_RECORDS], summary="Trip records",
           description="Trip-level records, newest first — the Data Explorer table.")
    def trip_records(limit: int = Query(500), dff=Depends(filtered_df)):
        return figures.trip_records(dff[0], limit)

    return r
