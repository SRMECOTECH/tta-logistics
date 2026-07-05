"""Excel -> clean -> SQLite loader.

Runs automatically on first startup (when the trips table is empty) and on
demand via POST /api/data/reload or /api/data/upload. The app is fully
standalone after import — the Excel is only a seed.
"""
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import geo
from .database import engine

COLMAP = {
    "Transporter": "transporter", "Trip ID": "trip_id", "Store Entry No": "store_entry_no",
    "Vehicle No": "vehicle_no", "Vehicle Type": "vehicle_type", "Dept Date": "dept_dt",
    "Consignor": "consignor", "Origin": "origin", "Consignee": "consignee",
    "Destination": "destination", "Ship To Party Code": "ship_to_code",
    "ETA": "eta_dt", "ATA": "ata_dt", "ATA Out": "ata_out_dt",
    "Transit Time(Hr:Mi)": "transit_raw", "Detention(Hr:Mi)": "detention_raw",
    "Distance Travelled(Km)": "distance_km", "Total Run Time(Hr:Mi)": "run_raw",
    "Total Stop Time(Hr:Mi)": "stop_raw", "Speed Voilation(No)": "speed_violations",
    "Trip Closing Date": "closing_dt", "Trip Closed Reason": "trip_closed_reason",
    "Invoice No.": "invoice_no", "Asset Make": "asset_make", "Asset Model": "asset_model",
    "Driver No": "driver_no", "Driver Name": "driver_name", "Booking Date": "booking_dt",
    "Delivery Date": "delivery_date", "Device Id": "device_id", "Device Type": "device_type",
    "Own/Market": "own_market", "Receipt No./LR No.": "lr_no", "Pin Code": "pin_code",
    "Plant Vivo(Days Hr:Mi)": "plant_vivo_raw", "Delivery Status": "delivery_status",
    "Delivery Duration": "delivery_duration_raw", "Transporter Code": "transporter_code",
    "GPS Uptime": "gps_uptime",
}

DUR_RE = re.compile(r"(?:(\d+)\s*Days?\s*)?(\d{1,4}):(\d{2})", re.IGNORECASE)


def parse_duration_hours(val):
    """'5 Days 23:51' | '123:35' | '00:12' -> hours (float)."""
    if not isinstance(val, str):
        return None
    m = DUR_RE.search(val)
    if not m:
        return None
    days = int(m.group(1) or 0)
    return round(days * 24 + int(m.group(2)) + int(m.group(3)) / 60.0, 3)


def parse_delivery_delta(val):
    """'Before By 3 Days 00:09' -> -72.15 ; 'Delay By 10:18' -> +10.3"""
    hours = parse_duration_hours(val)
    if hours is None:
        return None
    if isinstance(val, str) and "before" in val.lower():
        return -hours
    return hours


def _to_dt(series, fmt):
    parsed = pd.to_datetime(series, format=fmt, errors="coerce")
    fallback = pd.to_datetime(series, dayfirst=True, errors="coerce")
    return parsed.fillna(fallback)


def _vehicle_category(vt):
    if not isinstance(vt, str):
        return "UNSPECIFIED"
    up = vt.upper()
    if "TRAILER" in up:
        return "TRAILER"
    if "HEAVY" in up:
        return "HEAVY VEHICLE"
    if "LCV" in up or "LIGHT" in up:
        return "LIGHT VEHICLE"
    return "SPEC/OTHER"


def load_excel_to_db(excel_path: str | Path, speed_cap: float = 110.0) -> dict:
    """Full replace-import. Returns summary dict."""
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    raw = pd.read_excel(excel_path)
    missing = [c for c in COLMAP if c not in raw.columns]
    df = raw.rename(columns=COLMAP)[[v for k, v in COLMAP.items() if k in raw.columns]].copy()

    # --- datetimes ---
    for col, fmt in [
        ("dept_dt", "%d-%m-%Y %H:%M:%S"), ("eta_dt", "%d-%m-%Y %H:%M:%S"),
        ("ata_dt", "%d-%m-%Y %H:%M:%S"), ("ata_out_dt", "%d-%m-%Y %H:%M:%S"),
        ("booking_dt", "%d-%m-%Y %H:%M:%S"), ("delivery_date", "%d-%m-%Y %H:%M:%S"),
        ("closing_dt", "%d-%b-%Y %H:%M:%S"),
    ]:
        if col in df:
            df[col] = _to_dt(df[col], fmt)

    # --- durations ---
    df["transit_hours"] = df.get("transit_raw", pd.Series(dtype=object)).map(parse_duration_hours)
    df["detention_hours"] = df.get("detention_raw", pd.Series(dtype=object)).map(parse_duration_hours)
    df["run_hours"] = df.get("run_raw", pd.Series(dtype=object)).map(parse_duration_hours)
    df["stop_hours"] = df.get("stop_raw", pd.Series(dtype=object)).map(parse_duration_hours)
    df["plant_vivo_hours"] = df.get("plant_vivo_raw", pd.Series(dtype=object)).map(parse_duration_hours)
    df["delivery_delta_hours"] = df.get("delivery_duration_raw", pd.Series(dtype=object)).map(parse_delivery_delta)

    # zero transit usually means trip was force-closed before tracking - keep NULL
    df.loc[df["transit_hours"] == 0, "transit_hours"] = np.nan

    df["planned_transit_hours"] = (df["eta_dt"] - df["dept_dt"]).dt.total_seconds() / 3600
    df.loc[df["planned_transit_hours"] <= 0, "planned_transit_hours"] = np.nan
    df["dispatch_lead_hours"] = (df["dept_dt"] - df["booking_dt"]).dt.total_seconds() / 3600
    df.loc[df["dispatch_lead_hours"] < 0, "dispatch_lead_hours"] = np.nan

    # --- speed (guard against GPS noise) ---
    df["distance_km"] = pd.to_numeric(df.get("distance_km"), errors="coerce")
    speed = df["distance_km"] / df["run_hours"].replace(0, np.nan)
    df["avg_speed_kmph"] = speed.where((speed > 1) & (speed <= speed_cap)).round(1)

    df["speed_violations"] = pd.to_numeric(df.get("speed_violations"), errors="coerce").fillna(0).astype(int)
    df["gps_uptime"] = pd.to_numeric(df.get("gps_uptime"), errors="coerce")

    # --- delivery flags ---
    status = df.get("delivery_status", pd.Series(dtype=object))
    df["is_on_time"] = np.where(
        status == "On Time Delivery", 1, np.where(status == "Delay Delivery", 0, np.nan)
    )

    df["vehicle_category"] = df.get("vehicle_type", pd.Series(dtype=object)).map(_vehicle_category)

    # --- geo ---
    coords = df.apply(lambda r: geo.resolve(r.get("destination"), r.get("pin_code")), axis=1)
    df["dest_lat"] = [c[0] for c in coords]
    df["dest_lon"] = [c[1] for c in coords]
    df["lane"] = df.get("origin", "").fillna("JAMSHEDPUR").astype(str).str.strip() + " → " + df[
        "destination"
    ].astype(str).str.strip()

    # --- calendar helpers ---
    df["dept_date"] = df["dept_dt"].dt.strftime("%Y-%m-%d")
    df["dept_hour"] = df["dept_dt"].dt.hour
    df["dept_dow"] = df["dept_dt"].dt.dayofweek
    df["dept_month"] = df["dept_dt"].dt.strftime("%Y-%m")
    iso = df["dept_dt"].dt.isocalendar()
    df["dept_week"] = iso["year"].astype("string") + "-W" + iso["week"].astype("string").str.zfill(2)

    # --- stringify ids ---
    for col in ["invoice_no", "lr_no", "driver_no", "device_id", "transporter_code", "ship_to_code", "pin_code"]:
        if col in df:
            df[col] = df[col].astype("string").str.replace(r"\.0$", "", regex=True)

    from .models import Trip

    keep = [c.name for c in Trip.__table__.columns if c.name != "id" and c.name in df.columns]
    out = df[keep].replace({np.nan: None, pd.NaT: None})

    with engine.begin() as conn:
        conn.exec_driver_sql("DELETE FROM trips")
    out.to_sql("trips", engine, if_exists="append", index=False, chunksize=1000)

    return {
        "rows_imported": int(len(out)),
        "source": str(excel_path),
        "missing_columns": missing,
        "geo_mapped_pct": round(100 * df["dest_lat"].notna().mean(), 1),
        "imported_at": datetime.now().isoformat(timespec="seconds"),
    }
