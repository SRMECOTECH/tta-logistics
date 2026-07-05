"""Statistical distributions + automated anomaly detection."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import api, ui

ui.setup_page("Distributions & Outliers", "📊")
ui.page_intro(
    "Averages lie. This page shows the full spread behind each number — what a typical trip looks "
    "like, how bad the worst ones get — and automatically flags individual trips that behaved "
    "abnormally and deserve investigation."
)
params = ui.sidebar_filters()

METRICS = {
    "transit_hours": "Transit time (h)", "distance_km": "Distance (km)",
    "detention_hours": "Detention (h)", "delivery_delta_hours": "Delivery delta (h, − = early)",
    "avg_speed_kmph": "Effective speed (km/h)", "plant_vivo_hours": "Plant vivo (h)",
    "dispatch_lead_hours": "Dispatch lead time (h)", "gps_uptime": "GPS uptime (%)",
}
metric = st.selectbox("Metric", list(METRICS), format_func=METRICS.get)

dist = api.guard(api.get, "/api/distribution", {**params, "metric": metric})
values, stats = dist["values"], dist["stats"]
if not values:
    st.info("No data for this metric with the current filters.")
    st.stop()

# ------------------------------------------------------------------- stats
s = st.columns(8)
for col, (label, key) in zip(s, [("Count", "count"), ("Mean", "mean"), ("Median", "median"),
                                 ("Std dev", "std"), ("P10", "p10"), ("P90", "p90"),
                                 ("P95", "p95"), ("Skew", "skew")]):
    col.metric(label, stats.get(key))
ui.explain(
    "Quick decoder — <b>Mean</b>: the average. <b>Median</b>: the middle trip (half are quicker, half "
    "slower) — more honest than the mean when a few extreme trips distort things. <b>P90/P95</b>: 9 in "
    "10 (or 19 in 20) trips finish below this value — this is the number to base promises on. "
    "<b>Skew</b> above ~1 means a long tail of unusually bad trips is dragging the average up."
)

c1, c2 = st.columns(2)
with c1:
    fig = px.histogram(x=values, nbins=60, title=f"Histogram — {METRICS[metric]}",
                       color_discrete_sequence=["#00b4d8"])
    fig.add_vline(x=stats["mean"], line_dash="dash", line_color="#ffd166", annotation_text="mean")
    fig.add_vline(x=stats["median"], line_dash="dot", line_color="#90be6d", annotation_text="median")
    st.plotly_chart(ui.style_fig(fig, 400), use_container_width=True)
    ui.explain(
        "How all trips are spread across this metric — tall bars are the most common values.",
        "A long thin tail stretching right is a minority of very bad trips. They inflate the "
        "average and hide in summary reports — the outlier table below names them individually.",
    )
with c2:
    fig = go.Figure()
    fig.add_trace(go.Violin(y=values, box_visible=True, meanline_visible=True,
                            fillcolor="rgba(0,180,216,0.3)", line_color="#00b4d8", name=""))
    fig.update_layout(title=f"Violin + box — {METRICS[metric]}")
    st.plotly_chart(ui.style_fig(fig, 400), use_container_width=True)
    ui.explain(
        "The same spread drawn as a shape: the widest part is where most trips sit; the box marks "
        "the middle half of all trips.",
        "A short, fat shape = a consistent, predictable process. A long, stretched shape = high "
        "variability, which forces customers and planners to keep safety buffers.",
    )

# ECDF
sv = sorted(values)
ecdf_y = [i / len(sv) * 100 for i in range(1, len(sv) + 1)]
fig = go.Figure(go.Scatter(x=sv, y=ecdf_y, mode="lines", line=dict(color="#c77dff", width=2)))
fig.update_layout(title=f"Cumulative distribution — {METRICS[metric]}",
                  yaxis_title="% of trips ≤ x", xaxis_title=METRICS[metric])
st.plotly_chart(ui.style_fig(fig, 340), use_container_width=True)
ui.explain(
    "Read this like a promise-setting chart: pick a value on the bottom axis and the curve tells "
    "you what percentage of trips finish within it.",
    "Example: find where the curve crosses 95% — that's the delivery time you can promise and keep "
    "19 times out of 20. Quoting the average instead means disappointing nearly half of customers.",
)

# ----------------------------------------------------- grouped box compare
group_by = st.selectbox("Compare distribution across", ["transporter", "destination", "vehicle_category",
                                                        "own_market", "consignor"])
box = api.guard(api.get, "/api/boxdata", {**params, "group_by": group_by, "metric": metric, "top": 10})
bdf = pd.DataFrame(box)
if not bdf.empty:
    fig = px.box(bdf, x="group", y="value", color="group", points="outliers",
                 title=f"{METRICS[metric]} by {group_by} (top 10 by volume)",
                 labels={"group": "", "value": METRICS[metric]})
    fig.update_layout(showlegend=False)
    st.plotly_chart(ui.style_fig(fig, 440), use_container_width=True)
    ui.explain(
        "The same metric, split by the group you chose — each box shows one group's typical range.",
        "Compare box heights, not just centres: two carriers can have the same average while one is "
        "far more erratic. Predictability is worth almost as much as speed.",
    )

st.divider()

# --------------------------------------------------------- anomaly detection
st.subheader("🚩 Automated anomaly detection (per-lane z-score on transit time)")
z = st.slider("Z-score threshold (lower = more sensitive)", 1.5, 4.0, 3.0, 0.25)
out = api.guard(api.get, "/api/outliers", {**params, "z": z})
odf = pd.DataFrame(out)
if odf.empty:
    st.success("No outlier trips at this sensitivity.")
else:
    st.caption(f"**{len(odf)} anomalous trips** — transit time far from their lane's average.")
    st.dataframe(odf, use_container_width=True, hide_index=True, height=380)
    ui.explain(
        "Specific trips that took far longer (or shorter) than is normal FOR THAT ROUTE — each row "
        "shows the trip, its actual hours, the route's usual hours, and how extreme the gap is "
        "(z-score: 3 ≈ a once-in-hundreds event).",
        "Each row is a question for the transporter: breakdown? diversion? driver issue? or simply "
        "wrong data? Investigating even the top five usually surfaces a fixable process gap.",
    )
    st.download_button("⬇️ Download outliers CSV", odf.to_csv(index=False), "outliers.csv", "text/csv")

ui.ai_insight_block(
    f"Statistical distribution of {METRICS[metric]} + anomalies",
    {"metric": METRICS[metric], "stats": stats, "outlier_threshold_z": z,
     "sample_outlier_trips": out[:12]},
    filters=params, key="ai_dist",
    question="Interpret the distribution shape (skew, spread, tails) and the flagged anomalies; suggest process actions.",
)
