"""Executive Overview — the landing dashboard."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import api, ui

ui.setup_page("Executive Overview", "🏭")
ui.page_intro(
    "One-page health check of outbound steel logistics from the Jamshedpur plant: how much is "
    "shipping, whether customers get it on time, and where money and reputation are leaking. "
    "Green deltas = better than the previous period."
)
params = ui.sidebar_filters()

kpis = api.guard(api.get, "/api/kpis", params)
cur, deltas = kpis["current"], kpis["delta_pct"]
settings = api.guard(api.get, "/api/settings")
otd_target = float(settings.get("otd_target_pct", 95))

# ---------------------------------------------------------------- KPI cards --
r1 = st.columns(4)
ui.kpi_card(r1[0], "Total trips", cur.get("trips"), delta=deltas.get("trips"))
ui.kpi_card(r1[1], "On-time delivery", cur.get("otd_pct"), " %", deltas.get("otd_pct"))
ui.kpi_card(r1[2], "Avg transit time", cur.get("avg_transit_hours"), " h",
            deltas.get("avg_transit_hours"), invert=True)
ui.kpi_card(r1[3], "Total distance", cur.get("total_km"), " km", deltas.get("total_km"))
r2 = st.columns(4)
ui.kpi_card(r2[0], "Active transporters", cur.get("transporters"))
ui.kpi_card(r2[1], "Unique vehicles", cur.get("vehicles"))
ui.kpi_card(r2[2], "Avg detention", cur.get("avg_detention_hours"), " h",
            deltas.get("avg_detention_hours"), invert=True)
ui.kpi_card(r2[3], "Avg speed alerts / trip", cur.get("avg_violations_per_trip"),
            delta=deltas.get("avg_violations_per_trip"), invert=True)

with st.expander("📚 What do these terms mean? (plain-English glossary)"):
    st.markdown("""
| Term | Plain-English meaning | Why it matters |
|---|---|---|
| **On-time delivery (OTD)** | % of trips that reached the customer by the promised date | The single best measure of the service promise being kept |
| **Transit time** | Hours from leaving the plant gate to arriving at the customer | Longer transit = slower cash cycle and unhappier customers |
| **Detention** | Hours a truck waits at the customer before it is unloaded | Idle trucks cost money and delay their next load |
| **Plant vivo** | Time a truck spends inside our own plant before departure | Our own loading delays, before the transporter is even responsible |
| **Dispatch lead time** | Hours from booking a truck to it actually leaving | Long lead time = planning friction |
| **Speed alerts** | GPS-detected over-speed events during a trip | Safety risk, accident and insurance exposure |
| **GPS uptime** | % of the trip the truck was actually visible on tracking | Low uptime = blind spots; you can't manage what you can't see |
| **Own vs Market** | Company-controlled fleet vs hired market trucks | Cost vs control trade-off |
""")

st.divider()

# --------------------------------------------------- volume trend + OTD gauge
ts = api.guard(api.get, "/api/timeseries", {**params, "granularity": "D"})
tsdf = pd.DataFrame(ts)
c1, c2 = st.columns([2.2, 1])
with c1:
    if not tsdf.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=tsdf["period"], y=tsdf["trips"], fill="tozeroy",
                                 name="Trips/day", line=dict(color="#00b4d8", width=2)))
        tsdf["ma7"] = tsdf["trips"].rolling(7, min_periods=1).mean()
        fig.add_trace(go.Scatter(x=tsdf["period"], y=tsdf["ma7"], name="7-day avg",
                                 line=dict(color="#ffd166", width=2, dash="dash")))
        fig.update_layout(title="Daily dispatch volume")
        st.plotly_chart(ui.style_fig(fig, 360), use_container_width=True)
        ui.explain(
            "How many loaded trucks left the plant each day; the dotted line smooths out daily noise.",
            "A steady or rising line is healthy. Sudden dips mean production, ordering or truck-availability "
            "problems on those dates — worth asking 'what happened that day?'.",
        )
with c2:
    gauge = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=cur.get("otd_pct") or 0,
        number={"suffix": " %"},
        delta={"reference": otd_target, "suffix": " vs target"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#00b4d8"},
            "threshold": {"line": {"color": "#f94144", "width": 3}, "value": otd_target},
            "steps": [{"range": [0, otd_target * 0.85], "color": "#3d1f28"},
                      {"range": [otd_target * 0.85, otd_target], "color": "#3d3520"},
                      {"range": [otd_target, 100], "color": "#1d3428"}],
        },
        title={"text": f"OTD vs target ({otd_target:.0f}%)"},
    ))
    st.plotly_chart(ui.style_fig(gauge, 360), use_container_width=True)
    ui.explain(
        "The share of deliveries that arrived by the promised date, against the company target (red line).",
        "Every point below target is a broken promise to a customer. Use the filters on the left to find "
        "which transporter or route is dragging this down.",
    )

# ------------------------------------------------ transit trend + status donut
c3, c4 = st.columns([2.2, 1])
with c3:
    if not tsdf.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=tsdf["period"], y=tsdf["avg_transit_hours"],
                                 name="Avg transit (h)", line=dict(color="#f77f00", width=2)))
        fig.add_trace(go.Scatter(x=tsdf["period"], y=tsdf["otd_pct"], name="OTD %",
                                 yaxis="y2", line=dict(color="#90be6d", width=2)))
        fig.update_layout(title="Transit time vs on-time performance",
                          yaxis=dict(title="hours"),
                          yaxis2=dict(title="OTD %", overlaying="y", side="right", range=[0, 100]))
        st.plotly_chart(ui.style_fig(fig, 340), use_container_width=True)
        ui.explain(
            "Average journey time (orange) plotted against on-time performance (green) day by day.",
            "When the orange line climbs and the green line falls at the same time, journeys are genuinely "
            "getting slower. If OTD falls while transit stays flat, the delivery promises themselves are "
            "probably too tight.",
        )
with c4:
    on = cur.get("otd_pct") or 0
    donut = px.pie(values=[on, 100 - on], names=["On time", "Delayed"], hole=0.6,
                   color_discrete_sequence=["#90be6d", "#f94144"], title="Delivery status split")
    st.plotly_chart(ui.style_fig(donut, 340), use_container_width=True)
    ui.explain(
        "Out of every 100 completed deliveries, how many were on time (green) vs late (red).",
        "The red slice is the volume of customer conversations you don't want to be having.",
    )

# -------------------------------------------- top destinations + market share
lanes = api.guard(api.get, "/api/group", {**params, "by": "destination", "min_trips": 1})
tr = api.guard(api.get, "/api/group", {**params, "by": "transporter"})
c5, c6 = st.columns(2)
with c5:
    top = pd.DataFrame(lanes).head(10)
    if not top.empty:
        fig = px.bar(top, x="trips", y="destination", orientation="h", color="otd_pct",
                     color_continuous_scale=["#f94144", "#ffd166", "#90be6d"],
                     range_color=[50, 100], title="Top 10 destinations (color = OTD %)")
        fig.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(ui.style_fig(fig, 400), use_container_width=True)
        ui.explain(
            "Where the most trucks go. Bar length = number of trips; bar colour = service quality "
            "(green = mostly on time, red = often late).",
            "A long red bar is the worst combination: a major customer location getting poor service. "
            "Fix those lanes first — that's where the most business is at risk.",
        )
with c6:
    trdf = pd.DataFrame(tr).head(10)
    if not trdf.empty:
        fig = px.pie(trdf, values="trips", names="transporter", hole=0.45,
                     title="Volume share — top 10 transporters")
        st.plotly_chart(ui.style_fig(fig, 400), use_container_width=True)
        ui.explain(
            "How the shipping work is divided among transport partners.",
            "If two or three slices dominate, the business depends heavily on those carriers — good for "
            "rates, risky if one of them fails. Balance volume with the performance shown on the "
            "Transporters page.",
        )

# ---------------------------------------------------------------- funnel ----
fun = api.guard(api.get, "/api/funnel", params)
fdf = pd.DataFrame(fun)
if not fdf.empty:
    fig = go.Figure(go.Funnel(y=fdf["stage"], x=fdf["count"], textinfo="value+percent initial",
                              marker={"color": ui.COLORWAY}))
    fig.update_layout(title="Trip lifecycle funnel")
    st.plotly_chart(ui.style_fig(fig, 380), use_container_width=True)
    ui.explain(
        "Every trip should pass through these stages: booked → departed → arrived → unloaded → closed. "
        "The funnel shows how many trips have data at each stage.",
        "A big step down between two stages means trips are 'disappearing' from the tracking system there "
        "— usually a GPS or process-discipline gap, not trucks actually vanishing. Those blind spots make "
        "every other number less trustworthy.",
    )

# ------------------------------------------------------------- AI summary ---
ui.ai_insight_block(
    "Executive summary",
    {"kpis": cur, "kpi_change_pct_vs_previous_period": deltas,
     "top_destinations": lanes[:8], "top_transporters": tr[:8]},
    filters=params, key="ai_home",
    question="Write an executive summary of overall logistics performance for a client presentation.",
)
