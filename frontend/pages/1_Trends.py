"""Time & Trends — volumes, OTD, transit and lead-time over time."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import api, ui

ui.setup_page("Time & Trends", "📈")
ui.page_intro(
    "Is the operation getting better or worse over time? This page tracks volumes, reliability, "
    "journey times and safety week by week — direction matters more than any single number."
)
params = ui.sidebar_filters()

gran_label = st.radio("Granularity", ["Daily", "Weekly", "Monthly"], horizontal=True)
gran = {"Daily": "D", "Weekly": "W", "Monthly": "M"}[gran_label]

ts = api.guard(api.get, "/api/timeseries", {**params, "granularity": gran})
df = pd.DataFrame(ts)
if df.empty:
    st.info("No data for the current filters.")
    st.stop()

# --------------------------------------------------------- multi-metric line
c1, c2 = st.columns(2)
with c1:
    fig = px.bar(df, x="period", y="trips", title=f"{gran_label} trip volume")
    if len(df) > 2:
        df["growth_pct"] = (df["trips"].pct_change() * 100).round(1)
        fig.add_trace(go.Scatter(x=df["period"], y=df["trips"].rolling(3, min_periods=1).mean(),
                                 name="3-period avg", line=dict(color="#ffd166", dash="dash")))
    st.plotly_chart(ui.style_fig(fig, 380), use_container_width=True)
    ui.explain(
        "Number of truckloads dispatched per period — the pulse of the outbound business.",
        "Compare against plant production plans: if output is steady but dispatches drop, product is "
        "piling up in the yard.",
    )
with c2:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["period"], y=df["otd_pct"], name="OTD %",
                             line=dict(color="#90be6d", width=3)))
    fig.add_hline(y=95, line_dash="dot", line_color="#f94144", annotation_text="target 95%")
    fig.update_layout(title="On-time delivery % trend", yaxis=dict(range=[0, 105]))
    st.plotly_chart(ui.style_fig(fig, 380), use_container_width=True)
    ui.explain(
        "The reliability of the delivery promise over time, against the target line.",
        "A slow downward drift is more dangerous than a one-off bad week — it means the problem is "
        "structural (routes, carriers or unrealistic promises), not bad luck.",
    )

c3, c4 = st.columns(2)
with c3:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["period"], y=df["avg_transit_hours"], name="Avg transit (h)",
                             fill="tozeroy", line=dict(color="#f77f00")))
    fig.add_trace(go.Scatter(x=df["period"], y=df["avg_detention_hours"], name="Avg detention (h)",
                             line=dict(color="#f94144")))
    fig.update_layout(title="Transit & detention hours")
    st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
    ui.explain(
        "Orange = average road journey time. Red = average hours trucks sat waiting at the customer "
        "gate before unloading (detention).",
        "Detention is pure waste: the truck is paid for but doing nothing. If the red line rises, "
        "specific customers are holding trucks — the Routes page shows who.",
    )
with c4:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["period"], y=df["avg_dispatch_lead_hours"],
                             name="Booking → departure (h)", line=dict(color="#c77dff", width=2)))
    fig.update_layout(title="Dispatch lead time (booking to gate-out)")
    st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
    ui.explain(
        "How many hours pass between booking a truck and that truck actually leaving the plant.",
        "This is internal friction — before the transporter is even on the road. Shrinking it moves "
        "every delivery earlier for free.",
    )

c5, c6 = st.columns(2)
with c5:
    fig = px.area(df, x="period", y="total_km", title="Distance covered (km)")
    st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
    ui.explain(
        "Total kilometres the fleet drove per period — a good proxy for freight spend and fuel.",
        "If kilometres grow faster than trip count, loads are travelling further on average; check "
        "whether pricing and delivery promises reflect that.",
    )
with c6:
    fig = px.bar(df, x="period", y="speed_violations", title="Speed violations",
                 color_discrete_sequence=["#f94144"])
    st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
    ui.explain(
        "GPS-detected over-speeding events per period across the whole fleet.",
        "Spikes are a safety red flag — one serious accident costs more than any delivery saving. "
        "The Fleet page names the specific vehicles responsible.",
    )

with st.expander("📄 Underlying data"):
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download CSV", df.to_csv(index=False), "trends.csv", "text/csv")

ui.ai_insight_block(
    f"{gran_label} performance trends",
    {"timeseries": ts[-40:]}, filters=params, key="ai_trends",
    question="Identify trends, inflection points, seasonality and anomalies over time.",
)
