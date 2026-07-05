"""Fleet & Vehicles — own vs market, vehicle mix, telematics compliance."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import streamlit as st

from lib import api, ui

ui.setup_page("Fleet & Vehicles", "🚛")
ui.page_intro(
    "The trucks themselves: company fleet vs hired market vehicles, tracking quality, and the "
    "specific vehicles creating safety risk. This is where accidents and blind spots are prevented."
)
params = ui.sidebar_filters()

fleet = api.guard(api.get, "/api/fleet", params)

# ------------------------------------------------------------ own vs market
om = pd.DataFrame(fleet["own_market"])
st.subheader("🏠 Own fleet vs market vehicles")
if not om.empty:
    cols = st.columns(len(om))
    for i, (_, row) in enumerate(om.iterrows()):
        with cols[i]:
            st.metric(f"{row['own_market']} fleet", f"{row['trips']:,} trips",
                      f"OTD {row['otd_pct']}%" if row["otd_pct"] is not None else None)
    melt = om.melt(id_vars="own_market",
                   value_vars=["otd_pct", "avg_transit_hours", "avg_detention_hours",
                               "violations_per_trip", "avg_gps_uptime"],
                   var_name="metric", value_name="value")
    nice = {"otd_pct": "OTD %", "avg_transit_hours": "Transit h", "avg_detention_hours": "Detention h",
            "violations_per_trip": "Speed alerts/trip", "avg_gps_uptime": "GPS %"}
    melt["metric"] = melt["metric"].map(nice)
    fig = px.bar(melt, x="metric", y="value", color="own_market", barmode="group",
                 title="Own vs Market — side-by-side KPIs")
    st.plotly_chart(ui.style_fig(fig, 380), use_container_width=True)
    ui.explain(
        "Company-controlled trucks ('Own') compared with hired market trucks on the same five "
        "yardsticks, side by side.",
        "If the Own fleet is clearly more reliable, every critical customer should ride on it — and "
        "the gap is the service price of the market fleet's flexibility. Use this to decide which "
        "loads deserve which fleet.",
    )

c1, c2 = st.columns(2)
with c1:
    vc = pd.DataFrame(fleet["vehicle_category"])
    if not vc.empty:
        fig = px.pie(vc, values="trips", names="vehicle_category", hole=0.5,
                     title="Trips by vehicle category")
        st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
        ui.explain(
            "What kind of vehicles carry the freight — trailers, heavy vehicles, and specialised types.",
            "The mix should match the cargo: too few trailers forces steel onto less suitable "
            "vehicles; too many parked trailers is idle capital.",
        )
with c2:
    dt = pd.DataFrame(fleet["device_type"])
    if not dt.empty:
        fig = px.bar(dt, x="device_type", y="trips", color="device_type",
                     title="GPS device type (permanent vs rental)",
                     text="avg_gps_uptime")
        fig.update_traces(texttemplate="GPS %{text:.1f}%")
        st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
        ui.explain(
            "Trips tracked with permanently installed GPS devices vs temporary rented trackers, and "
            "the average tracking quality of each.",
            "Rented trackers usually mean market trucks. If their uptime is lower, a chunk of the "
            "fleet is effectively invisible for part of every journey.",
        )

am = pd.DataFrame(fleet["asset_make"])
if not am.empty:
    fig = px.bar(am.sort_values("trips", ascending=False), x="asset_make", y="trips",
                 title="Asset make (where telematics metadata exists)", color="otd_pct",
                 color_continuous_scale=["#f94144", "#ffd166", "#90be6d"], range_color=[50, 100])
    st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
    ui.explain(
        "Truck manufacturers in the fleet (where recorded), coloured by on-time performance.",
        "Only a small share of trips carry maker data, so treat this as indicative — but persistent "
        "differences can inform the next fleet purchase.",
    )

st.divider()

# --------------------------------------------------------- compliance tables
c3, c4 = st.columns(2)
with c3:
    st.subheader("🚨 Top speed-violating vehicles")
    tv = pd.DataFrame(fleet["top_violating_vehicles"])
    st.dataframe(tv, use_container_width=True, hide_index=True, height=360)
    ui.explain(
        "The specific trucks with the most over-speeding alerts, and which carrier runs them.",
        "This is an actionable safety list: a handful of vehicles usually accounts for a huge share "
        "of alerts. Share it with the named transporters and re-check next month.",
    )
with c4:
    st.subheader("📡 Low GPS-uptime vehicles (< 80%)")
    lg = pd.DataFrame(fleet["low_gps_vehicles"])
    if lg.empty:
        st.success("No vehicles below the 80% GPS uptime threshold.")
    else:
        st.dataframe(lg, use_container_width=True, hide_index=True, height=360)
        ui.explain(
            "Trucks whose GPS was silent for more than 20% of their journeys.",
            "You cannot manage what you cannot see: these vehicles' delivery data is unreliable and "
            "their loads are effectively untracked. Ask the carrier to fix or replace the devices.",
        )

# ------------------------------------------------- GPS uptime distribution
dist = api.guard(api.get, "/api/distribution", {**params, "metric": "gps_uptime"})
if dist["values"]:
    fig = px.histogram(x=dist["values"], nbins=40, title="GPS uptime distribution (%)",
                       color_discrete_sequence=["#4cc9f0"])
    fig.update_layout(xaxis_title="GPS uptime %", yaxis_title="trips")
    st.plotly_chart(ui.style_fig(fig, 340), use_container_width=True)
    ui.explain(
        "How tracking quality is distributed across all trips: the further right, the more of the "
        "journey was visible on GPS.",
        "A healthy fleet piles up near 100%. A second bump at lower values reveals a subset of "
        "vehicles (often rentals) with chronic tracking problems.",
    )

ui.ai_insight_block(
    "Fleet composition & telematics compliance",
    {"own_vs_market": fleet["own_market"], "vehicle_categories": fleet["vehicle_category"],
     "device_types": fleet["device_type"], "top_violating_vehicles": fleet["top_violating_vehicles"][:8],
     "low_gps_vehicles": fleet["low_gps_vehicles"][:8], "gps_uptime_stats": dist["stats"]},
    filters=params, key="ai_fleet",
    question="Assess fleet strategy (own vs market), telematics compliance gaps, and safety risks from speed violations.",
)
