"""AI Insights Studio — LangChain-powered analysis on demand."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import api, ui

ui.setup_page("AI Insights Studio", "🤖")
ui.page_intro(
    "Ask the data questions in plain English. The system computes the relevant numbers from the "
    "database, hands them to an AI analyst, and returns a written brief — findings, risks and "
    "recommended actions — that can go straight into a management review."
)
params = ui.sidebar_filters()

settings = api.guard(api.get, "/api/settings")
provider = settings.get("ai_provider", "disabled")
if provider == "disabled":
    st.warning("No AI provider is enabled. Configure Azure OpenAI, OpenAI or Hugging Face (free) "
               "in the ⚙️ Settings page (sidebar).")
    try:
        st.page_link("pages/10_Settings.py", label="→ Open Settings", icon="⚙️")
    except Exception:
        pass
else:
    st.success(f"AI provider active: **{provider}** — every request is orchestrated through LangChain "
               "(prompt template → chat model → output parser).")

st.markdown("Pick an analysis pack; the backend computes the relevant aggregates from the database, "
            "sends them to the LLM with a role-specific prompt, and returns a client-ready narrative.")

PACKS = {
    "📋 Executive summary (full overview)": {
        "endpoints": {"kpis": ("/api/kpis", {}), "timeseries": ("/api/timeseries", {"granularity": "W"}),
                      "transporters": ("/api/group", {"by": "transporter"}),
                      "lanes": ("/api/group", {"by": "destination", "min_trips": 5})},
        "question": "Write a board-level executive summary: overall health, biggest wins, biggest problems, "
                    "and a 90-day improvement agenda.",
    },
    "🚚 Transporter deep-dive": {
        "endpoints": {"transporters": ("/api/group", {"by": "transporter"})},
        "question": "Rank transporters, identify who should gain/lose volume, quantify performance gaps, and "
                    "propose a carrier scorecard policy.",
    },
    "🛣️ Lane / corridor deep-dive": {
        "endpoints": {"lanes": ("/api/group", {"by": "destination", "min_trips": 3})},
        "question": "Find the most problematic corridors, mis-calibrated SLAs, and quantify the on-time risk "
                    "per corridor.",
    },
    "🚛 Fleet & safety review": {
        "endpoints": {"fleet": ("/api/fleet", {})},
        "question": "Review own-vs-market strategy, GPS compliance and speeding risk; propose safety actions.",
    },
    "⚠️ Risk & anomaly report": {
        "endpoints": {"outliers": ("/api/outliers", {}), "kpis": ("/api/kpis", {})},
        "question": "Summarize anomalous trips and systemic risks; recommend a monitoring & escalation process.",
    },
}

pack_name = st.selectbox("Analysis pack", list(PACKS))
custom_q = st.text_area("Optional: ask your own question about this data",
                        placeholder="e.g. Which 3 changes would improve OTD the fastest? "
                                    "Which transporters are overloaded on the Chennai corridor?")

if st.button("🚀 Run AI analysis", type="primary"):
    pack = PACKS[pack_name]
    data = {}
    with st.spinner("Computing aggregates from the database…"):
        for name, (path, extra) in pack["endpoints"].items():
            try:
                result = api.get(path, {**params, **extra})
                data[name] = result[:25] if isinstance(result, list) else result
            except api.ApiError as e:
                st.error(f"{name}: {e}")
    if data:
        with st.spinner("LangChain → LLM analysing…"):
            try:
                out = api.post("/api/ai/insight", json={
                    "context": pack_name, "data": data, "filters": params,
                    "question": custom_q.strip() or pack["question"],
                })
                st.session_state["studio_result"] = out
                st.session_state["studio_data"] = data
            except api.ApiError as e:
                st.error(f"⚠️ {e}")

if "studio_result" in st.session_state:
    out = st.session_state["studio_result"]
    st.divider()
    st.markdown(out["markdown"])
    st.caption(f"🤖 {out['provider']} · {out['elapsed_s']}s · LangChain pipeline")
    st.download_button("⬇️ Download report (markdown)", out["markdown"], "ai_report.md")
    with st.expander("🔍 Aggregates sent to the LLM"):
        st.json(st.session_state.get("studio_data", {}), expanded=False)
