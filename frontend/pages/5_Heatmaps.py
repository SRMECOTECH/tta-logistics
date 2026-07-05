"""Heatmaps & correlations — operational rhythm and metric relationships."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import plotly.graph_objects as go
import streamlit as st

from lib import api, ui

ui.setup_page("Heatmaps & Correlations", "🔥")
ui.page_intro(
    "Patterns that averages hide: when trucks leave the plant, how each carrier trends month by "
    "month, and which operational factors move together."
)
params = ui.sidebar_filters()


def heat_fig(rows, cols, values, title, colorscale="Viridis", zmid=None):
    fig = go.Figure(go.Heatmap(
        z=values, x=[str(c) for c in cols], y=rows, colorscale=colorscale, zmid=zmid,
        hoverongaps=False, colorbar=dict(thickness=12),
    ))
    fig.update_layout(title=title)
    return ui.style_fig(fig, 430)


# ------------------------------------------------- departure rhythm dow×hour
dh = api.guard(api.get, "/api/heatmap/dow_hour", params)
st.plotly_chart(
    heat_fig(dh["rows"], [f"{h:02d}h" for h in dh["cols"]], dh["values"],
             "🕐 Departure rhythm — weekday × hour of day", "Blues"),
    use_container_width=True,
)
ui.explain(
    "Each cell is a day-of-week + hour-of-day combination; darker = more trucks left the plant "
    "gate in that window.",
    "Dark vertical bands are the gate's rush hours — queues, paperwork bottlenecks and loading "
    "delays concentrate there. Spreading departures into the pale cells reduces plant congestion "
    "without any new infrastructure.",
)

st.divider()

# ------------------------------------------------ transporter × month pivots
metric = st.selectbox(
    "Metric for transporter × month heatmap",
    ["otd_pct", "trips", "transit_hours", "detention_hours", "gps_uptime"],
    format_func=lambda m: {"otd_pct": "OTD %", "trips": "Trip volume", "transit_hours": "Avg transit (h)",
                           "detention_hours": "Avg detention (h)", "gps_uptime": "GPS uptime %"}[m],
)
pv = api.guard(api.get, "/api/heatmap/pivot",
               {**params, "rows": "transporter", "cols": "dept_month", "metric": metric, "top": 12})
scale = "RdYlGn" if metric in ("otd_pct", "gps_uptime") else ("RdYlGn_r" if "hours" in metric else "Viridis")
if pv["rows"]:
    st.plotly_chart(heat_fig(pv["rows"], pv["cols"], pv["values"],
                             "🚚 Top transporters × month", scale), use_container_width=True)
    ui.explain(
        "Each row is a major carrier, each column a month, colour = the metric chosen above.",
        "Read along a row: a carrier whose colour worsens month after month is deteriorating — "
        "catch the slide early, before it shows up as customer complaints.",
    )

# ---------------------------------------------- destination × month volume
pv2 = api.guard(api.get, "/api/heatmap/pivot",
                {**params, "rows": "destination", "cols": "dept_month", "metric": "trips", "top": 15})
if pv2["rows"]:
    st.plotly_chart(heat_fig(pv2["rows"], pv2["cols"], pv2["values"],
                             "📍 Top destinations × month (trip volume)", "Blues"), use_container_width=True)
    ui.explain(
        "Demand by customer location over time — darker means more truckloads that month.",
        "Shifting dark cells show demand moving between regions; useful for placing vehicles and "
        "negotiating carrier capacity before the shift bites.",
    )

st.divider()

# -------------------------------------------------------- correlation matrix
corr = api.guard(api.get, "/api/correlation", params)
nice = {
    "transit_hours": "Transit h", "planned_transit_hours": "Planned h", "detention_hours": "Detention h",
    "run_hours": "Run h", "stop_hours": "Stop h", "plant_vivo_hours": "Plant vivo h",
    "delivery_delta_hours": "Delay h", "dispatch_lead_hours": "Lead h", "distance_km": "Distance km",
    "avg_speed_kmph": "Speed", "speed_violations": "Violations", "gps_uptime": "GPS %",
}
labels = [nice.get(l, l) for l in corr["labels"]]
fig = go.Figure(go.Heatmap(z=corr["values"], x=labels, y=labels, colorscale="RdBu", zmid=0,
                           text=corr["values"], texttemplate="%{text}", colorbar=dict(thickness=12)))
fig.update_layout(title="🧮 Correlation matrix — every metric vs every metric")
st.plotly_chart(ui.style_fig(fig, 560), use_container_width=True)
ui.explain(
    "How strongly each pair of operational numbers moves together: blue = they rise and fall "
    "together, red = when one rises the other falls, near 0 = unrelated. (1.0 = perfectly linked.)",
    "This tells you which lever actually moves which outcome. Example: if 'Stop h' is strongly "
    "linked to 'Delay h' but 'Speed' is not, reducing en-route stops — not driving faster — is what "
    "fixes late deliveries. Correlation isn't proof of cause, but it tells you where to look first.",
)

ui.ai_insight_block(
    "Operational rhythm & metric correlations",
    {"departures_by_dow_hour": dh, "correlation_matrix": corr,
     "transporter_month_metric": {"metric": metric, **pv}},
    filters=params, key="ai_heat",
    question="Interpret the strongest correlations and the departure-time patterns; call out anything actionable.",
)
