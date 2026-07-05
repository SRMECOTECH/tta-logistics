"""Geo intelligence — India-wide flow map from the Jamshedpur plant."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import math

import pandas as pd
import pydeck as pdk
import streamlit as st

from lib import api, ui

ui.setup_page("Geo Intelligence Map", "🗺️")
ui.page_intro(
    "The delivery network on a map of India. Every arc is freight flowing out of the Jamshedpur "
    "plant; every bubble is a customer location — sized by how much goes there, coloured by how "
    "well it's served."
)
params = ui.sidebar_filters()

geo = api.guard(api.get, "/api/geo", params)
points = pd.DataFrame(geo["points"])
origin = geo["origin"]

if points.empty:
    st.info("No mapped destinations for the current filters.")
    st.stop()

st.caption(f"🌍 {geo['mapped_pct']}% of trips geolocated · offline city/pincode geocoder (no external API)")

c0, c1, c2, c3 = st.columns(4)
show_arcs = c0.toggle("Flow arcs", value=True)
show_bubbles = c1.toggle("Volume bubbles", value=True)
show_heat = c2.toggle("Density heatmap", value=False)
metric = c3.selectbox("Bubble color", ["otd_pct", "avg_transit_hours", "avg_distance_km"],
                      format_func=lambda m: {"otd_pct": "OTD %", "avg_transit_hours": "Transit h",
                                             "avg_distance_km": "Distance km"}[m])


def color_for(row):
    """green -> red scale; for OTD high=green, for time/distance high=red."""
    v = row.get(metric)
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return [120, 130, 150, 160]
    lo, hi = points[metric].min(), points[metric].max()
    t = 0.5 if hi == lo else (v - lo) / (hi - lo)
    if metric != "otd_pct":
        t = 1 - t
    r = int(249 - t * (249 - 144))
    g = int(65 + t * (190 - 65))
    b = int(68 + t * (109 - 68))
    return [r, g, b, 200]


points = points.copy()
points["color"] = points.apply(color_for, axis=1)
points["radius"] = points["trips"].apply(lambda t: 9000 + math.sqrt(t) * 2600)
points["from_lon"], points["from_lat"] = origin["lon"], origin["lat"]

layers = []
if show_arcs:
    layers.append(pdk.Layer(
        "ArcLayer", data=points,
        get_source_position=["from_lon", "from_lat"], get_target_position=["dest_lon", "dest_lat"],
        get_source_color=[0, 180, 216, 120], get_target_color="color",
        get_width="1 + trips / 60", pickable=True,
    ))
if show_bubbles:
    layers.append(pdk.Layer(
        "ScatterplotLayer", data=points,
        get_position=["dest_lon", "dest_lat"], get_radius="radius", get_fill_color="color",
        pickable=True, opacity=0.75, stroked=True, get_line_color=[255, 255, 255, 60],
    ))
if show_heat:
    layers.append(pdk.Layer(
        "HeatmapLayer", data=points,
        get_position=["dest_lon", "dest_lat"], get_weight="trips", radius_pixels=60,
    ))
# origin marker
layers.append(pdk.Layer(
    "ScatterplotLayer",
    data=pd.DataFrame([{**origin, "label": "ORIGIN"}]),
    get_position=["lon", "lat"], get_radius=16000, get_fill_color=[0, 180, 216, 255],
    stroked=True, get_line_color=[255, 255, 255, 200], line_width_min_pixels=2,
))

st.pydeck_chart(pdk.Deck(
    layers=layers,
    initial_view_state=pdk.ViewState(latitude=22.5, longitude=80.5, zoom=4.1, pitch=32),
    tooltip={"html": "<b>{destination}</b><br/>Trips: {trips}<br/>OTD: {otd_pct}%"
                     "<br/>Avg transit: {avg_transit_hours} h<br/>Avg distance: {avg_distance_km} km"},
), height=620)
ui.explain(
    "Bubble size = trip volume to that location; colour runs green (good) to red (poor) on the metric "
    "selected above. Hover any bubble for its numbers; drag to rotate, scroll to zoom.",
    "Look for regional patterns: a cluster of red bubbles in one region points to a shared cause — "
    "a weak carrier covering that zone, a congested corridor, or over-optimistic promises for that "
    "distance. One red bubble alone is a local issue; a red region is a network issue.",
)

st.divider()

c4, c5 = st.columns([1.4, 1])
with c4:
    st.subheader("📍 Destination detail")
    st.dataframe(
        points[["destination", "trips", "otd_pct", "avg_transit_hours", "avg_distance_km", "total_km"]]
        .sort_values("trips", ascending=False),
        use_container_width=True, hide_index=True, height=380,
        column_config={"otd_pct": st.column_config.ProgressColumn("OTD %", format="%.1f%%",
                                                                  min_value=0, max_value=100)},
    )
with c5:
    st.subheader("❓ Not geolocated")
    unmapped = pd.DataFrame(geo["unmapped"])
    if unmapped.empty:
        st.success("All destinations mapped.")
    else:
        st.dataframe(unmapped, use_container_width=True, hide_index=True, height=380)

ui.ai_insight_block(
    "Geographic distribution of outbound logistics",
    {"origin": origin, "destinations": geo["points"][:25]},
    filters=params, key="ai_geo",
    question="Analyse the geographic spread: regional concentration, long-haul vs short-haul mix, and regional service risks.",
)
