"""ORM models — tables are auto-created on startup."""
from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from .database import Base


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(Integer, index=True)
    store_entry_no = Column(Integer)
    invoice_no = Column(String)
    lr_no = Column(String)

    transporter = Column(String, index=True)
    transporter_code = Column(String)
    vehicle_no = Column(String, index=True)
    vehicle_type = Column(String)
    vehicle_category = Column(String)
    own_market = Column(String)
    device_type = Column(String)
    device_id = Column(String)
    asset_make = Column(String)
    asset_model = Column(String)
    driver_no = Column(String)
    driver_name = Column(String)

    consignor = Column(String, index=True)
    origin = Column(String)
    consignee = Column(String)
    destination = Column(String, index=True)
    ship_to_code = Column(String)
    pin_code = Column(String)

    booking_dt = Column(DateTime)
    dept_dt = Column(DateTime, index=True)
    eta_dt = Column(DateTime)
    ata_dt = Column(DateTime)
    ata_out_dt = Column(DateTime)
    closing_dt = Column(DateTime)
    delivery_date = Column(DateTime)

    transit_raw = Column(String)
    detention_raw = Column(String)
    run_raw = Column(String)
    stop_raw = Column(String)
    plant_vivo_raw = Column(String)
    delivery_duration_raw = Column(String)

    transit_hours = Column(Float)
    planned_transit_hours = Column(Float)
    detention_hours = Column(Float)
    run_hours = Column(Float)
    stop_hours = Column(Float)
    plant_vivo_hours = Column(Float)
    delivery_delta_hours = Column(Float)  # positive = delayed, negative = early
    dispatch_lead_hours = Column(Float)   # booking -> departure

    distance_km = Column(Float)
    avg_speed_kmph = Column(Float)
    speed_violations = Column(Integer)
    gps_uptime = Column(Float)

    trip_closed_reason = Column(String)
    delivery_status = Column(String)
    is_on_time = Column(Integer)  # 1 / 0 / NULL

    dest_lat = Column(Float)
    dest_lon = Column(Float)
    lane = Column(String, index=True)

    dept_date = Column(String)   # YYYY-MM-DD
    dept_hour = Column(Integer)
    dept_dow = Column(Integer)   # 0 = Monday
    dept_month = Column(String)  # YYYY-MM
    dept_week = Column(String)   # YYYY-Www


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, default="")
