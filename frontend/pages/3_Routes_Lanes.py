"""Route / Lane analysis — corridor performance from Jamshedpur."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import api, ui

ui.setup_page("Routes & Lanes", "🛣️")
ui.page_intro(
    "Every delivery corridor from the Jamshedpur plant, judged on speed, reliability and whether "
    "the promised delivery windows are realistic. This is where SLA renegotiations start."
)
params = ui.sidebar_filters()

data = api.guard(api.get, "/api/group", {**params, "by": "destination", "min_trips": 3})
df = pd.DataFrame(data)
if df.empty:
    st.info("No data for the current filters.")
    st.stop()

st.subheader("🛤️ Lane performance table (all lanes ≥ 3 trips)")
show = df[["destination", "trips", "otd_pct", "avg_transit_hours", "avg_planned_transit_hours",
           "schedule_variance_hours", "avg_distance_km", "avg_speed_kmph", "avg_detention_hours"]]
st.dataframe(
    show, use_container_width=True, hide_index=True, height=350,
    column_config={
        "destination": "Destination",
        "otd_pct": st.column_config.ProgressColumn("OTD %", format="%.1f%%", min_value=0, max_value=100),
        "avg_transit_hours": st.column_config.NumberColumn("Actual transit (h)", format="%.1f"),
        "avg_planned_transit_hours": st.column_config.NumberColumn("Planned transit (h)", format="%.1f"),
        "schedule_variance_hours": st.column_config.NumberColumn("Variance (h)", format="%.1f"),
        "avg_distance_km": st.column_config.NumberColumn("Avg km", format="%.0f"),
        "avg_speed_kmph": st.column_config.NumberColumn("Avg speed", format="%.1f"),
        "avg_detention_hours": st.column_config.NumberColumn("Detention (h)", format="%.1f"),
    },
)
ui.explain(
    "One row per destination: trips, on-time %, the journey time we promise (planned) versus what "
    "actually happens, and how long trucks wait to be unloaded there.",
    "'Variance' is the honesty check — a route that is always slower than planned needs either a "
    "better route plan or a more honest promise to the customer.",
)
st.download_button("⬇️ Download lanes CSV", show.to_csv(index=False), "lanes.csv", "text/csv")

st.divider()

# ------------------------------------------- distance vs transit + speed rank
c1, c2 = st.columns([1.4, 1])
with c1:
    sc = df.dropna(subset=["avg_distance_km", "avg_transit_hours"])
    fig = px.scatter(sc, x="avg_distance_km", y="avg_transit_hours", size="trips",
                     color="otd_pct", hover_name="destination",
                     color_continuous_scale=["#f94144", "#ffd166", "#90be6d"], range_color=[50, 100],
                     title="Distance vs transit time (bubble = trips, color = OTD %)",
                     labels={"avg_distance_km": "Avg distance (km)", "avg_transit_hours": "Avg transit (h)"})
    if len(sc) > 3:
        coeffs = np.polyfit(sc["avg_distance_km"], sc["avg_transit_hours"], 1)
        xs = np.linspace(sc["avg_distance_km"].min(), sc["avg_distance_km"].max(), 50)
        fig.add_trace(go.Scatter(x=xs, y=np.polyval(coeffs, xs), mode="lines", name="trend",
                                 line=dict(color="#9fb3d1", dash="dash")))
        st.caption(f"Fleet-wide effective pace: **{coeffs[0]:.2f} h per km** "
                   f"(≈ {1 / coeffs[0]:.0f} km/h door-to-door including stops)")
    st.plotly_chart(ui.style_fig(fig, 470), use_container_width=True)
    ui.explain(
        "Each bubble is a destination: further right = longer distance, higher up = longer journey "
        "time. The dashed line is the 'normal pace' for this network.",
        "Distance explains most journey time — that's expected. The interesting bubbles sit well "
        "ABOVE the line: those routes take longer than their distance justifies (congestion, bad "
        "roads, border delays, or slow carriers) and are the best candidates for savings.",
    )
with c2:
    qual = df[df["trips"] >= 10].dropna(subset=["avg_speed_kmph"])
    slow = qual.nsmallest(10, "avg_speed_kmph")
    fig = px.bar(slow, x="avg_speed_kmph", y="destination", orientation="h",
                 title="Slowest corridors (effective km/h)", color_discrete_sequence=["#f77f00"])
    fig.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(ui.style_fig(fig, 470), use_container_width=True)
    ui.explain(
        "Destinations where trucks make the least progress per hour, door to door (driving plus "
        "every stop along the way).",
        "Very low km/h usually means excessive stopping or queuing rather than slow driving — "
        "worth tracing where these trucks actually halt.",
    )

# ---------------------------------------------------- worst schedule variance
c3, c4 = st.columns(2)
with c3:
    late = df[df["trips"] >= 5].dropna(subset=["schedule_variance_hours"]).nlargest(10, "schedule_variance_hours")
    fig = px.bar(late, x="schedule_variance_hours", y="destination", orientation="h",
                 title="Lanes running most behind plan (h)", color_discrete_sequence=["#f94144"])
    fig.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(ui.style_fig(fig, 400), use_container_width=True)
    ui.explain(
        "Routes where actual journeys run the most hours LATE versus the promised schedule.",
        "These promises are being broken systematically — renegotiate the delivery window or fix "
        "the route before customers lose patience.",
    )
with c4:
    early = df[df["trips"] >= 5].dropna(subset=["schedule_variance_hours"]).nsmallest(10, "schedule_variance_hours")
    fig = px.bar(early, x="schedule_variance_hours", y="destination", orientation="h",
                 title="Lanes with most schedule buffer (h)", color_discrete_sequence=["#90be6d"])
    fig.update_layout(yaxis=dict(autorange="reversed"))
    st.plotly_chart(ui.style_fig(fig, 400), use_container_width=True)
    ui.explain(
        "Routes where trucks routinely arrive many hours EARLIER than promised.",
        "Hidden opportunity: these delivery promises have slack built in. Tightening them lets sales "
        "quote faster deliveries than competitors — at zero extra cost.",
    )

# ------------------------------------------------------------------ treemap
fig = px.treemap(df.head(40), path=["destination"], values="trips", color="otd_pct",
                 color_continuous_scale=["#f94144", "#ffd166", "#90be6d"], range_color=[50, 100],
                 title="Lane volume treemap (color = OTD %)")
st.plotly_chart(ui.style_fig(fig, 480), use_container_width=True)
ui.explain(
    "The whole delivery network in one picture: each tile is a destination, tile size = share of "
    "trips, colour = service quality (green good, red poor).",
    "Scan for LARGE RED tiles — that's the biggest volume getting the worst service, i.e. the most "
    "revenue at risk. Small red tiles matter less; large green tiles are the backbone to protect.",
)

ui.ai_insight_block(
    "Route / lane corridor analysis",
    {"lanes_top_by_volume": data[:15],
     "lanes_worst_schedule_variance": late.to_dict("records") if not late.empty else []},
    filters=params, key="ai_lanes",
    question="Which corridors are problematic, which SLAs look mis-calibrated, and where should transit SLAs be renegotiated?",
)
