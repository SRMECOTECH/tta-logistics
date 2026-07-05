"""Transporter Scorecard — league table, rankings, radar comparison."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import api, ui

ui.setup_page("Transporter Scorecard", "🚚")
ui.page_intro(
    "A report card for every transport partner. Use it to decide who earns more business, "
    "who needs a performance conversation, and who is a safety or reliability risk."
)
params = ui.sidebar_filters()

data = api.guard(api.get, "/api/group", {**params, "by": "transporter", "min_trips": 1})
df = pd.DataFrame(data)
if df.empty:
    st.info("No data for the current filters.")
    st.stop()

# ------------------------------------------------------------- league table
st.subheader("🏆 League table")
show = df[["transporter", "trips", "share_pct", "otd_pct", "avg_transit_hours",
           "schedule_variance_hours", "avg_detention_hours", "avg_distance_km",
           "violations_per_trip", "avg_gps_uptime", "vehicles", "destinations"]]
st.dataframe(
    show, use_container_width=True, hide_index=True, height=380,
    column_config={
        "transporter": "Transporter",
        "trips": st.column_config.NumberColumn("Trips"),
        "share_pct": st.column_config.ProgressColumn("Volume share", format="%.1f%%",
                                                     min_value=0, max_value=float(show["share_pct"].max() or 1)),
        "otd_pct": st.column_config.ProgressColumn("OTD %", format="%.1f%%", min_value=0, max_value=100),
        "avg_transit_hours": st.column_config.NumberColumn("Avg transit (h)", format="%.1f"),
        "schedule_variance_hours": st.column_config.NumberColumn("Vs plan (h)", format="%.1f",
                                                                 help="Actual minus planned transit"),
        "avg_detention_hours": st.column_config.NumberColumn("Avg detention (h)", format="%.1f"),
        "avg_distance_km": st.column_config.NumberColumn("Avg km", format="%.0f"),
        "violations_per_trip": st.column_config.NumberColumn("Speed alerts /trip", format="%.1f"),
        "avg_gps_uptime": st.column_config.NumberColumn("GPS uptime %", format="%.1f"),
    },
)
ui.explain(
    "One row per carrier: how much they haul, how often they deliver on time, how fast they run, "
    "how long they get held up, and how safely they drive. Click any column header to sort.",
    "'Vs plan' is telling: a positive number means the carrier consistently runs behind the promised "
    "schedule; a large negative number means the schedule itself has slack built in.",
)
st.download_button("⬇️ Download scorecard CSV", show.to_csv(index=False), "transporters.csv", "text/csv")

st.divider()

# ------------------------------------------------- best / worst + bubble map
min_trips = st.slider("Minimum trips to qualify for ranking", 5, 100, 20, 5)
qual = df[df["trips"] >= min_trips].copy()

c1, c2 = st.columns(2)
with c1:
    best = qual.dropna(subset=["otd_pct"]).nlargest(10, "otd_pct")
    fig = px.bar(best, x="otd_pct", y="transporter", orientation="h", title="Best OTD %",
                 color_discrete_sequence=["#90be6d"], text="otd_pct")
    fig.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 105]))
    st.plotly_chart(ui.style_fig(fig, 380), use_container_width=True)
with c2:
    worst = qual.dropna(subset=["otd_pct"]).nsmallest(10, "otd_pct")
    fig = px.bar(worst, x="otd_pct", y="transporter", orientation="h", title="Worst OTD %",
                 color_discrete_sequence=["#f94144"], text="otd_pct")
    fig.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 105]))
    st.plotly_chart(ui.style_fig(fig, 380), use_container_width=True)

ui.explain(
    "The most and least reliable carriers among those with enough trips to judge fairly "
    "(adjust the minimum-trips slider above).",
    "Reward the green list with volume. For the red list, first check *where* they run — a carrier "
    "stuck with the hardest routes may deserve context, not punishment. The radar below helps with that.",
)

if not qual.empty:
    fig = px.scatter(
        qual, x="avg_transit_hours", y="otd_pct", size="trips", color="avg_detention_hours",
        hover_name="transporter", color_continuous_scale=["#90be6d", "#ffd166", "#f94144"],
        title="Risk map: transit time vs OTD (bubble = volume, color = detention)",
        labels={"avg_transit_hours": "Avg transit (h)", "otd_pct": "OTD %"},
    )
    st.plotly_chart(ui.style_fig(fig, 460), use_container_width=True)
    ui.explain(
        "Every bubble is one carrier. Left = faster journeys, higher = more reliable, bigger bubble = "
        "more of your volume, redder = more time wasted waiting at customer gates.",
        "The danger zone is bottom-right: big bubbles there mean a lot of freight riding on slow, "
        "unreliable partners. Top-left bubbles are candidates for more volume.",
    )

# ------------------------------------------------------------ radar compare
st.subheader("🎯 Head-to-head radar")
pick = st.multiselect("Compare transporters (2-4)", qual["transporter"].tolist(),
                      default=qual["transporter"].head(3).tolist())
if 2 <= len(pick) <= 4:
    metrics = ["otd_pct", "avg_transit_hours", "avg_detention_hours", "violations_per_trip", "avg_gps_uptime"]
    labels = ["OTD %", "Transit (inv)", "Detention (inv)", "Violations (inv)", "GPS uptime"]
    sub = qual.set_index("transporter").loc[pick, metrics].astype(float)
    norm = sub.copy()
    for m in metrics:
        lo, hi = df[m].min(), df[m].max()
        span = (hi - lo) or 1
        norm[m] = (sub[m] - lo) / span * 100
        if m in ("avg_transit_hours", "avg_detention_hours", "violations_per_trip"):
            norm[m] = 100 - norm[m]  # lower is better
    fig = go.Figure()
    for name in pick:
        fig.add_trace(go.Scatterpolar(r=norm.loc[name].tolist() + [norm.loc[name].iloc[0]],
                                      theta=labels + [labels[0]], fill="toself", name=name))
    fig.update_layout(title="Normalized performance (100 = best in fleet)",
                      polar=dict(radialaxis=dict(range=[0, 100])))
    st.plotly_chart(ui.style_fig(fig, 480), use_container_width=True)
    ui.explain(
        "A head-to-head comparison of the carriers you selected, scored 0–100 on five dimensions "
        "(100 = best in the fleet; for time, detention and speeding the scale is flipped so bigger "
        "is always better).",
        "The carrier with the larger overall shape is the better all-round partner. A lopsided shape "
        "reveals a specific weakness to raise in the next contract review.",
    )

# --------------------------------------------------------- transit box plots
box = api.guard(api.get, "/api/boxdata", {**params, "group_by": "transporter",
                                          "metric": "transit_hours", "top": 10})
bdf = pd.DataFrame(box)
if not bdf.empty:
    fig = px.box(bdf, x="group", y="value", color="group",
                 title="Transit time spread — top 10 transporters by volume",
                 labels={"group": "", "value": "Transit hours"})
    fig.update_layout(showlegend=False)
    st.plotly_chart(ui.style_fig(fig, 420), use_container_width=True)
    ui.explain(
        "Each box shows the *spread* of journey times for a carrier, not just the average. The box is "
        "where half of their trips fall; dots are unusual trips.",
        "A short box = predictable partner you can plan around. A tall box or many dots = erratic "
        "delivery times, which forces everyone downstream to keep extra buffer stock.",
    )

ui.ai_insight_block(
    "Transporter performance benchmarking",
    {"transporter_scorecard": data[:20], "min_trips_filter": min_trips},
    filters=params, key="ai_transporters",
    question="Benchmark the transporters: who should get more volume, who needs a performance review, and why?",
)
