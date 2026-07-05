"""Shared UI components: page setup, global filters, KPI cards, plotly theme,
and the reusable "AI Insights" block that appears on every page."""
import plotly.graph_objects as go
import streamlit as st

from . import api

COLORWAY = ["#00b4d8", "#f77f00", "#90be6d", "#f94144", "#c77dff",
            "#ffd166", "#4cc9f0", "#ff70a6", "#8ecae6", "#fb8500"]


def setup_page(title: str, icon: str = "📊"):
    st.set_page_config(page_title=f"{title} · TTA Analytics", page_icon=icon, layout="wide",
                       initial_sidebar_state="expanded")
    st.markdown(
        """
        <style>
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, #192132 0%, #1f2a40 100%);
            border: 1px solid #2b3a55; border-radius: 12px; padding: 14px 16px;
        }
        div[data-testid="stMetric"] label { color: #9fb3d1; }
        .block-container { padding-top: 2.2rem; }
        .biz-note {
            background: rgba(0, 180, 216, 0.06);
            border-left: 3px solid #00b4d8;
            border-radius: 0 8px 8px 0;
            padding: 9px 14px;
            margin: 6px 0 30px 0;
            font-size: 0.87rem;
            line-height: 1.5;
            color: #b8c4d8;
        }
        .biz-note b { color: #e8eaf0; }
        .biz-takeaway { color: #dfe6f2; }
        .page-intro {
            background: rgba(255, 209, 102, 0.06);
            border-left: 3px solid #ffd166;
            border-radius: 0 8px 8px 0;
            padding: 10px 16px;
            margin: 0 0 22px 0;
            font-size: 0.95rem;
            color: #cdd6e4;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title(f"{icon} {title}")


def page_intro(text: str):
    """Plain-English banner under the page title: why this page matters to the business."""
    st.markdown(f'<div class="page-intro">🎯 {text}</div>', unsafe_allow_html=True)


def explain(what: str, takeaway: str | None = None):
    """Non-technical reading guide rendered directly under a chart."""
    html = f'<div class="biz-note">{what}'
    if takeaway:
        html += f'<br><span class="biz-takeaway">{takeaway}</span>'
    st.markdown(html + "</div>", unsafe_allow_html=True)


def style_fig(fig: go.Figure, height: int | None = None) -> go.Figure:
    has_pie = any(trace.type == "pie" for trace in fig.data)
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=COLORWAY,
        # generous top margin: title sits at the very top, legend below it,
        # so the two never overlap
        margin=dict(l=10, r=10, t=90, b=16),
        font=dict(family="Segoe UI, sans-serif"),
        legend=(
            # pies/donuts: vertical legend on the right, clear of the chart
            dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02,
                 font=dict(size=11))
            if has_pie else
            # everything else: horizontal legend tucked between title and plot
            dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                 font=dict(size=11))
        ),
    )
    # pin the title to the very top only when the figure actually has one,
    # otherwise plotly renders a stray "undefined"
    if fig.layout.title and fig.layout.title.text:
        fig.update_layout(title=dict(y=0.97, yanchor="top", x=0, xanchor="left"))
    if height:
        fig.update_layout(height=height)
    return fig


def sidebar_filters() -> dict:
    """Global filters shared by all pages via session state. Returns query params."""
    meta = api.guard(api.get, "/api/meta")
    if not meta.get("rows"):
        st.warning("No data loaded yet. Go to ⚙️ Settings → Data to import the Excel.")
        st.stop()

    st.sidebar.header("🔍 Global filters")
    with st.sidebar:
        from datetime import date

        dmin = date.fromisoformat(meta["date_min"]) if meta.get("date_min") else None
        dmax = date.fromisoformat(meta["date_max"]) if meta.get("date_max") else None
        date_range = st.date_input("Departure date range", value=(), min_value=dmin, max_value=dmax,
                                   help="Leave empty for the full range", key="flt_dates")
        transporters = st.multiselect("Transporter", meta["transporters"], key="flt_tr")
        destinations = st.multiselect("Destination", meta["destinations"], key="flt_dest")
        vehicle_categories = st.multiselect("Vehicle category", meta["vehicle_categories"], key="flt_vc")
        own_market = st.multiselect("Own / Market", meta["own_market"], key="flt_om")
        consignors = st.multiselect("Consignor", meta["consignors"], key="flt_cons")
        if st.button("♻️ Refresh data cache", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        st.caption(f"📦 {meta['rows']:,} trips · {dmin} → {dmax}")

    params: dict = {}
    if isinstance(date_range, tuple) and len(date_range) == 2:
        params["date_from"] = str(date_range[0])
        params["date_to"] = str(date_range[1])
    if transporters:
        params["transporters"] = "||".join(transporters)
    if destinations:
        params["destinations"] = "||".join(destinations)
    if vehicle_categories:
        params["vehicle_categories"] = "||".join(vehicle_categories)
    if own_market:
        params["own_market"] = "||".join(own_market)
    if consignors:
        params["consignors"] = "||".join(consignors)
    return params


def kpi_card(col, label: str, value, suffix: str = "", delta=None, invert: bool = False):
    if value is None:
        col.metric(label, "—")
        return
    text = f"{value:,.0f}{suffix}" if isinstance(value, (int, float)) and abs(value) >= 1000 \
        else f"{value}{suffix}"
    delta_str = f"{delta:+.1f}% vs prev period" if isinstance(delta, (int, float)) else None
    col.metric(label, text, delta=delta_str, delta_color="inverse" if invert else "normal")


def ai_insight_block(context: str, data, filters: dict | None = None, key: str = "ai",
                     question: str | None = None):
    """'✨ Generate AI insights' button + result. Used on every page."""
    with st.container(border=True):
        left, right = st.columns([5, 2])
        left.markdown(f"#### ✨ AI insights — {context}")
        generate = right.button("Generate insights", key=f"{key}_btn", type="primary",
                                use_container_width=True)
        if generate:
            with st.spinner("LangChain is asking the model for insights…"):
                try:
                    result = api.post("/api/ai/insight", json={
                        "context": context, "data": data, "filters": filters, "question": question,
                    })
                    st.session_state[f"{key}_result"] = result
                except api.ApiError as e:
                    st.session_state[f"{key}_result"] = {"error": str(e)}
        result = st.session_state.get(f"{key}_result")
        if result:
            if "error" in result:
                st.warning(f"{result['error']}")
                try:
                    st.page_link("pages/10_Settings.py", label="→ Configure an AI provider in Settings",
                                 icon="⚙️")
                except Exception:
                    pass
            else:
                st.markdown(result["markdown"])
                st.caption(f"🤖 {result['provider']} · {result['elapsed_s']}s · generated via LangChain")
        with st.expander("🔍 Data sent to the LLM (transparency)"):
            st.json(data, expanded=False)
