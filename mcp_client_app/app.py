"""TTA MCP Client — a SEPARATE application that consumes the TTA analytics
purely over MCP (Model Context Protocol).

It never touches the database, the Excel or the REST API directly. Everything on
this page comes from the MCP server at http://127.0.0.1:8010/mcp — exactly how
an external app or AI agent would integrate. This is the live proof of the
"plug into anything" pitch.

Run it (its own port, alongside the main stack):
    .venv\\Scripts\\python.exe -m streamlit run mcp_client_app/app.py --server.port 8020
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from mcp_client_app import client

st.set_page_config(page_title="TTA MCP Client", page_icon="🧩", layout="wide")

st.title("🧩 TTA MCP Client")
st.caption(
    "A standalone app that reads the logistics analytics **only through MCP** — no database, "
    "no REST, no Excel. This is what an external application or AI agent sees."
)

# --------------------------------------------------------------- connection ---
with st.sidebar:
    st.subheader("🔌 MCP connection")
    url = st.text_input("MCP server URL", value=client.DEFAULT_URL)
    if st.button("🔄 Connect / refresh", use_container_width=True):
        st.session_state.pop("tools", None)
    reachable, msg = client.ping(url)
    (st.success if reachable else st.error)(msg)
    st.markdown(
        "---\n**Ports cheat-sheet**\n\n"
        "- `8000` REST API + Swagger `/docs`\n"
        "- `8010` MCP (this app talks here)\n"
        "- `8501` main dashboard\n"
        "- `8020` **this** client app"
    )

if not reachable:
    st.warning("Start the MCP server first:  `python -m mcp_server --http --port 8010`  "
               "(or run everything with `run.bat`).")
    st.stop()

if "tools" not in st.session_state:
    st.session_state["tools"] = client.list_tools(url)
tools = st.session_state["tools"]
tool_names = [t["name"] for t in tools]


def show_result(result, is_error: bool):
    """Render a tool result: markdown for text, tailored views for known JSON."""
    if is_error:
        st.error(result if isinstance(result, str) else "Tool returned an error.")
        return
    if isinstance(result, str):  # AI insight / plain text
        st.markdown(result)
        return

    # dataset overview -> KPI metrics
    if isinstance(result, dict) and "headline_kpis" in result:
        k = result["headline_kpis"]
        st.caption(f"{result.get('rows'):,} trips · {result.get('date_min')} → {result.get('date_max')} · "
                   f"{len(result.get('transporters', []))} transporters · {len(result.get('destinations', []))} destinations")
        cols = st.columns(4)
        cols[0].metric("On-time delivery", f"{k.get('otd_pct')} %")
        cols[1].metric("Avg transit", f"{k.get('avg_transit_hours')} h")
        cols[2].metric("Total distance", f"{k.get('total_km'):,.0f} km")
        cols[3].metric("Speed alerts / trip", k.get("avg_violations_per_trip"))

    # group summary -> table + bar chart
    rows = result.get("groups") if isinstance(result, dict) else None
    if rows:
        df = pd.DataFrame(rows)
        label = next((c for c in ("transporter", "destination", "vehicle_category",
                                  "own_market", "consignor", "device_type") if c in df.columns), df.columns[0])
        st.dataframe(df, use_container_width=True, hide_index=True, height=280)
        if "otd_pct" in df.columns:
            st.bar_chart(df.set_index(label)["otd_pct"].head(15), y_label="OTD %")

    # outliers / trips -> table
    for key in ("trips", "points"):
        if isinstance(result, dict) and isinstance(result.get(key), list) and result[key]:
            st.dataframe(pd.DataFrame(result[key]), use_container_width=True, hide_index=True, height=280)

    with st.expander("🔍 Raw MCP response (JSON)"):
        st.json(result)


# ------------------------------------------------------------- quick actions ---
st.subheader("⚡ Quick actions")
st.caption("One click = one MCP tool call, rendered as an app would.")
q = st.columns(5)
QUICK = [
    ("📊 Dataset overview", "tta_dataset_overview", {}),
    ("🚚 Top transporters", "tta_group_summary", {"by": "transporter", "min_trips": 20, "limit": 10}),
    ("🛣️ Worst lanes", "tta_group_summary", {"by": "destination", "min_trips": 10, "limit": 10}),
    ("🚩 Outliers", "tta_get_outliers", {"z_threshold": 3.0, "limit": 15}),
    ("🤖 AI insight", "tta_ai_insight", {"scope": "overview"}),
]
for col, (label, name, args) in zip(q, QUICK):
    if col.button(label, use_container_width=True):
        with st.spinner(f"Calling `{name}` over MCP…"):
            res, err = client.call_tool(name, args, url)
        st.markdown(f"**`{name}`** →")
        show_result(res, err)

st.divider()

# ------------------------------------------------------- tool catalog + caller ---
left, right = st.columns([1, 1.3])
with left:
    st.subheader(f"🛠️ Tool catalog ({len(tools)})")
    for t in tools:
        with st.expander(f"`{t['name']}` — {t['title']}"):
            st.write((t["description"] or "").split("\n\n")[0])

with right:
    st.subheader("🎯 Call any tool")
    picked = st.selectbox("Tool", tool_names,
                          index=tool_names.index("tta_get_kpis") if "tta_get_kpis" in tool_names else 0)
    st.caption(next((t["description"].split("\n\n")[0] for t in tools if t["name"] == picked), ""))
    import json as _json
    args_text = st.text_area(
        "Arguments (JSON)", value="{}", height=120,
        help='e.g. {"by": "transporter", "min_trips": 20}  or  {"filters": {"transporters": ["Hind Transport"]}}',
    )
    if st.button("▶️ Call tool", type="primary"):
        try:
            args = _json.loads(args_text or "{}")
        except _json.JSONDecodeError as e:
            st.error(f"Arguments must be valid JSON — {e}")
            st.stop()
        with st.spinner(f"Calling `{picked}` over MCP…"):
            res, err = client.call_tool(picked, args, url)
        show_result(res, err)
