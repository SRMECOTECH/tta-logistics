"""All analytics computations. Data volume is small (thousands of rows), so we
load the trips table into pandas per request and aggregate there — simple,
flexible, and fast enough for a prototype."""
import numpy as np
import pandas as pd

from .database import engine

DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

NUMERIC_METRICS = [
    "transit_hours", "planned_transit_hours", "detention_hours", "run_hours",
    "stop_hours", "plant_vivo_hours", "delivery_delta_hours", "dispatch_lead_hours",
    "distance_km", "avg_speed_kmph", "speed_violations", "gps_uptime",
]
GROUP_FIELDS = ["transporter", "destination", "vehicle_category", "own_market", "consignor", "device_type"]


def load_df() -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM trips", engine, parse_dates=["booking_dt", "dept_dt", "eta_dt", "ata_dt",
                                                                 "ata_out_dt", "closing_dt", "delivery_date"])
    return df


def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    if f.get("date_from"):
        df = df[df["dept_dt"] >= pd.Timestamp(f["date_from"])]
    if f.get("date_to"):
        df = df[df["dept_dt"] < pd.Timestamp(f["date_to"]) + pd.Timedelta(days=1)]
    for param, col in [("transporters", "transporter"), ("destinations", "destination"),
                       ("vehicle_categories", "vehicle_category"), ("own_market", "own_market"),
                       ("consignors", "consignor")]:
        vals = f.get(param)
        if vals:
            df = df[df[col].isin(vals)]
    return df


def clean_records(df: pd.DataFrame, digits: int = 2) -> list[dict]:
    df = df.copy()
    for c in df.select_dtypes(include=["float"]).columns:
        df[c] = df[c].round(digits)
    for c in df.select_dtypes(include=["datetime64[ns]"]).columns:
        df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M")
    df = df.replace([np.inf, -np.inf], np.nan)
    return df.astype(object).where(pd.notna(df), None).to_dict("records")


def _otd(s: pd.Series) -> float | None:
    s = s.dropna()
    return round(100 * s.mean(), 1) if len(s) else None


def _kpi_block(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    delayed = df.loc[df["is_on_time"] == 0, "delivery_delta_hours"].dropna()
    return {
        "trips": int(len(df)),
        "transporters": int(df["transporter"].nunique()),
        "vehicles": int(df["vehicle_no"].nunique()),
        "destinations": int(df["destination"].nunique()),
        "total_km": round(float(df["distance_km"].sum(skipna=True)), 0),
        "avg_km_per_trip": round(float(df["distance_km"].mean(skipna=True)), 1) if df["distance_km"].notna().any() else None,
        "otd_pct": _otd(df["is_on_time"]),
        "avg_transit_hours": round(float(df["transit_hours"].mean(skipna=True)), 1) if df["transit_hours"].notna().any() else None,
        "median_transit_hours": round(float(df["transit_hours"].median(skipna=True)), 1) if df["transit_hours"].notna().any() else None,
        "avg_delay_when_late_hours": round(float(delayed.mean()), 1) if len(delayed) else None,
        "avg_detention_hours": round(float(df["detention_hours"].mean(skipna=True)), 1) if df["detention_hours"].notna().any() else None,
        "avg_plant_vivo_hours": round(float(df["plant_vivo_hours"].mean(skipna=True)), 1) if df["plant_vivo_hours"].notna().any() else None,
        "avg_dispatch_lead_hours": round(float(df["dispatch_lead_hours"].mean(skipna=True)), 1) if df["dispatch_lead_hours"].notna().any() else None,
        "speed_violations": int(df["speed_violations"].sum()),
        "avg_violations_per_trip": round(float(df["speed_violations"].mean()), 1),
        "avg_gps_uptime": round(float(df["gps_uptime"].mean(skipna=True)), 1) if df["gps_uptime"].notna().any() else None,
        "avg_speed_kmph": round(float(df["avg_speed_kmph"].mean(skipna=True)), 1) if df["avg_speed_kmph"].notna().any() else None,
        "market_share_pct": round(100 * (df["own_market"] == "Market").mean(), 1),
    }


def kpis(df: pd.DataFrame, f: dict) -> dict:
    cur = _kpi_block(df)
    # previous window of equal length for deltas
    prev = {}
    if not df.empty and df["dept_dt"].notna().any():
        start, end = df["dept_dt"].min(), df["dept_dt"].max()
        span = max(end - start, pd.Timedelta(days=1))
        full = apply_filters(load_df(), {**f, "date_from": None, "date_to": None})
        prev_df = full[(full["dept_dt"] >= start - span) & (full["dept_dt"] < start)]
        prev = _kpi_block(prev_df)
    deltas = {}
    for k, v in cur.items():
        pv = prev.get(k)
        if isinstance(v, (int, float)) and isinstance(pv, (int, float)) and pv:
            deltas[k] = round(100 * (v - pv) / abs(pv), 1)
    return {"current": cur, "previous": prev, "delta_pct": deltas}


def timeseries(df: pd.DataFrame, granularity: str = "D") -> list[dict]:
    if df.empty:
        return []
    key = {"D": "dept_date", "W": "dept_week", "M": "dept_month"}.get(granularity, "dept_date")
    g = df.groupby(key).agg(
        trips=("id", "count"),
        otd_pct=("is_on_time", lambda s: _otd(s)),
        avg_transit_hours=("transit_hours", "mean"),
        avg_detention_hours=("detention_hours", "mean"),
        total_km=("distance_km", "sum"),
        speed_violations=("speed_violations", "sum"),
        avg_dispatch_lead_hours=("dispatch_lead_hours", "mean"),
    ).reset_index().rename(columns={key: "period"}).sort_values("period")
    return clean_records(g)


def group_summary(df: pd.DataFrame, by: str, min_trips: int = 1) -> list[dict]:
    if df.empty or by not in df.columns:
        return []
    g = df.groupby(by).agg(
        trips=("id", "count"),
        otd_pct=("is_on_time", lambda s: _otd(s)),
        avg_transit_hours=("transit_hours", "mean"),
        median_transit_hours=("transit_hours", "median"),
        avg_planned_transit_hours=("planned_transit_hours", "mean"),
        avg_detention_hours=("detention_hours", "mean"),
        avg_distance_km=("distance_km", "mean"),
        total_km=("distance_km", "sum"),
        avg_speed_kmph=("avg_speed_kmph", "mean"),
        speed_violations=("speed_violations", "sum"),
        avg_gps_uptime=("gps_uptime", "mean"),
        vehicles=("vehicle_no", "nunique"),
        destinations=("destination", "nunique"),
    ).reset_index()
    g = g[g["trips"] >= min_trips]
    g["violations_per_trip"] = (g["speed_violations"] / g["trips"]).round(1)
    g["share_pct"] = (100 * g["trips"] / len(df)).round(1)
    g["schedule_variance_hours"] = (g["avg_transit_hours"] - g["avg_planned_transit_hours"]).round(1)
    return clean_records(g.sort_values("trips", ascending=False))


def lanes(df: pd.DataFrame, min_trips: int = 3) -> list[dict]:
    return group_summary(df.assign(destination=df["destination"]), "destination", min_trips)


def geo_points(df: pd.DataFrame) -> dict:
    mapped = df.dropna(subset=["dest_lat", "dest_lon"])
    g = mapped.groupby(["destination", "dest_lat", "dest_lon"]).agg(
        trips=("id", "count"),
        otd_pct=("is_on_time", lambda s: _otd(s)),
        avg_transit_hours=("transit_hours", "mean"),
        avg_distance_km=("distance_km", "mean"),
        total_km=("distance_km", "sum"),
    ).reset_index()
    unmapped = (
        df[df["dest_lat"].isna()].groupby("destination").size().sort_values(ascending=False)
    )
    return {
        "origin": {"name": "JAMSHEDPUR", "lat": 22.8046, "lon": 86.2029},
        "points": clean_records(g),
        "unmapped": [{"destination": k, "trips": int(v)} for k, v in unmapped.items()],
        "mapped_pct": round(100 * len(mapped) / len(df), 1) if len(df) else 0,
    }


def heatmap_dow_hour(df: pd.DataFrame) -> dict:
    pivot = pd.crosstab(df["dept_dow"], df["dept_hour"]).reindex(index=range(7), columns=range(24), fill_value=0)
    return {"rows": DOW_NAMES, "cols": list(range(24)), "values": pivot.values.tolist()}


def heatmap_pivot(df: pd.DataFrame, rows: str, cols: str, metric: str, top: int = 12) -> dict:
    if df.empty or rows not in df.columns or cols not in df.columns:
        return {"rows": [], "cols": [], "values": []}
    top_rows = df[rows].value_counts().head(top).index.tolist()
    sub = df[df[rows].isin(top_rows)]
    if metric == "trips":
        pivot = pd.crosstab(sub[rows], sub[cols])
    elif metric == "otd_pct":
        pivot = sub.pivot_table(index=rows, columns=cols, values="is_on_time", aggfunc="mean") * 100
    else:
        pivot = sub.pivot_table(index=rows, columns=cols, values=metric, aggfunc="mean")
    pivot = pivot.reindex(top_rows)
    vals = pivot.round(1).where(pd.notna(pivot), None).values.tolist()
    return {"rows": pivot.index.astype(str).tolist(), "cols": pivot.columns.astype(str).tolist(), "values": vals}


def correlation(df: pd.DataFrame) -> dict:
    cols = [c for c in NUMERIC_METRICS if c in df.columns and df[c].notna().sum() > 10]
    corr = df[cols].corr().round(2)
    return {"labels": cols, "values": corr.where(pd.notna(corr), None).values.tolist()}


def distribution(df: pd.DataFrame, metric: str, max_points: int = 4000) -> dict:
    if metric not in NUMERIC_METRICS or metric not in df.columns:
        return {"values": [], "stats": {}}
    s = df[metric].dropna()
    sample = s.sample(min(len(s), max_points), random_state=7) if len(s) else s
    stats = {}
    if len(s):
        stats = {
            "count": int(len(s)), "mean": round(float(s.mean()), 2), "median": round(float(s.median()), 2),
            "std": round(float(s.std()), 2), "min": round(float(s.min()), 2), "max": round(float(s.max()), 2),
            "p10": round(float(s.quantile(0.10)), 2), "p90": round(float(s.quantile(0.90)), 2),
            "p95": round(float(s.quantile(0.95)), 2), "skew": round(float(s.skew()), 2),
        }
    return {"values": [round(float(v), 2) for v in sample], "stats": stats}


def boxdata(df: pd.DataFrame, group_by: str, metric: str, top: int = 10, max_points: int = 4000) -> list[dict]:
    if group_by not in GROUP_FIELDS or metric not in NUMERIC_METRICS:
        return []
    sub = df[[group_by, metric]].dropna()
    top_groups = sub[group_by].value_counts().head(top).index.tolist()
    sub = sub[sub[group_by].isin(top_groups)]
    if len(sub) > max_points:
        sub = sub.sample(max_points, random_state=7)
    return [{"group": r[group_by], "value": round(float(r[metric]), 2)} for _, r in sub.iterrows()]


def fleet(df: pd.DataFrame) -> dict:
    out = {
        "vehicle_category": group_summary(df, "vehicle_category"),
        "own_market": group_summary(df, "own_market"),
        "device_type": group_summary(df, "device_type"),
        "asset_make": group_summary(df.dropna(subset=["asset_make"]), "asset_make"),
    }
    veh = df.groupby("vehicle_no").agg(
        trips=("id", "count"), violations=("speed_violations", "sum"),
        avg_gps_uptime=("gps_uptime", "mean"), total_km=("distance_km", "sum"),
        transporter=("transporter", "first"),
    ).reset_index()
    out["top_violating_vehicles"] = clean_records(veh.sort_values("violations", ascending=False).head(15))
    low_gps = veh[veh["avg_gps_uptime"].notna() & (veh["avg_gps_uptime"] < 80) & (veh["trips"] >= 2)]
    out["low_gps_vehicles"] = clean_records(low_gps.sort_values("avg_gps_uptime").head(15))
    return out


def outliers(df: pd.DataFrame, z_threshold: float = 3.0, min_lane_trips: int = 8) -> list[dict]:
    sub = df.dropna(subset=["transit_hours", "destination"]).copy()
    grp = sub.groupby("destination")["transit_hours"]
    counts, mean, std = grp.transform("count"), grp.transform("mean"), grp.transform("std")
    sub["lane_mean_transit"] = mean.round(1)
    sub["z_score"] = ((sub["transit_hours"] - mean) / std.replace(0, np.nan)).round(2)
    flagged = sub[(counts >= min_lane_trips) & (sub["z_score"].abs() >= z_threshold)]
    cols = ["trip_id", "dept_dt", "transporter", "vehicle_no", "destination", "distance_km",
            "transit_hours", "lane_mean_transit", "z_score", "delivery_status", "driver_name"]
    flagged = flagged[cols].sort_values("z_score", key=lambda s: s.abs(), ascending=False).head(200)
    return clean_records(flagged)


def funnel(df: pd.DataFrame) -> list[dict]:
    stages = [
        ("Booked", int(df["booking_dt"].notna().sum())),
        ("Departed plant", int(df["dept_dt"].notna().sum())),
        ("Arrived at destination", int(df["ata_dt"].notna().sum())),
        ("Unloaded (gate-out)", int(df["ata_out_dt"].notna().sum())),
        ("Trip closed", int(df["closing_dt"].notna().sum())),
        ("Delivery status recorded", int(df["delivery_status"].notna().sum())),
    ]
    return [{"stage": s, "count": c} for s, c in stages]


def meta(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"rows": 0}
    return {
        "rows": int(len(df)),
        "date_min": str(df["dept_dt"].min().date()) if df["dept_dt"].notna().any() else None,
        "date_max": str(df["dept_dt"].max().date()) if df["dept_dt"].notna().any() else None,
        "transporters": sorted(df["transporter"].dropna().unique().tolist()),
        "destinations": df["destination"].value_counts().index.tolist(),
        "vehicle_categories": sorted(df["vehicle_category"].dropna().unique().tolist()),
        "consignors": sorted(df["consignor"].dropna().unique().tolist()),
        "own_market": sorted(df["own_market"].dropna().unique().tolist()),
    }
