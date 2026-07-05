"""Settings — AI providers (enable/disable + keys from the UI), analytics
thresholds, and data management."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import streamlit as st

from lib import api, ui

ui.setup_page("Settings", "⚙️")

settings = api.guard(api.get_fresh, "/api/settings")

tab_ai, tab_analytics, tab_data, tab_api = st.tabs(
    ["🤖 AI providers", "📐 Analytics config", "💾 Data", "🔑 API access"])

# ------------------------------------------------------------------ AI tab --
with tab_ai:
    st.markdown("All AI features run through **LangChain**; pick the active provider and paste its key. "
                "Keys are stored in the local SQLite database only.")

    _providers = ["disabled", "glm", "huggingface", "azure_openai", "openai"]
    provider = st.radio(
        "Active provider",
        _providers,
        index=_providers.index(settings.get("ai_provider", "disabled"))
        if settings.get("ai_provider", "disabled") in _providers else 0,
        format_func={
            "disabled": "❌ Disabled",
            "glm": "🧠 GLM / Zhipu (free tier)",
            "huggingface": "🤗 Hugging Face (free tier)",
            "azure_openai": "☁️ Azure OpenAI",
            "openai": "🟢 OpenAI",
        }.get,
        horizontal=True,
    )

    st.markdown("##### 🧠 GLM / Zhipu AI")
    st.caption("Free key: z.ai → sign up → API Keys. Models **glm-4.5-flash** and "
               "**glm-4.7-flash** are free; glm-4.6 / glm-5.2 are paid but cheap. "
               "OpenAI-compatible — no extra dependency.")
    g1, g2, g3 = st.columns(3)
    glm_key = g1.text_input("GLM API key", type="password",
                            value="__keep__" if settings.get("glm_api_key_set") else "",
                            placeholder="paste your z.ai key")
    glm_model = g2.text_input("GLM model", value=settings.get("glm_model", "glm-4.5-flash"))
    glm_base_url = g3.text_input("Base URL", value=settings.get("glm_base_url", "https://api.z.ai/api/paas/v4/"),
                                 help="International: https://api.z.ai/api/paas/v4/ · "
                                      "Mainland China: https://open.bigmodel.cn/api/paas/v4/")

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### 🤗 Hugging Face")
        st.caption("Free token: huggingface.co → Settings → Access Tokens (read)")
        hf_key = st.text_input("HF API token", type="password",
                               value="__keep__" if settings.get("hf_api_key_set") else "",
                               placeholder="hf_…")
        hf_model = st.text_input("HF chat model", value=settings.get("hf_model", "Qwen/Qwen2.5-7B-Instruct"))
    with c2:
        st.markdown("##### ☁️ Azure OpenAI")
        az_key = st.text_input("Azure API key", type="password",
                               value="__keep__" if settings.get("azure_api_key_set") else "",
                               placeholder="paste when you receive it")
        az_endpoint = st.text_input("Endpoint", value=settings.get("azure_endpoint", ""))
        az_deploy = st.text_input("Chat deployment", value=settings.get("azure_chat_deployment", ""))
        az_version = st.text_input("API version", value=settings.get("azure_api_version", ""))
    with c3:
        st.markdown("##### 🟢 OpenAI")
        oa_key = st.text_input("OpenAI API key", type="password",
                               value="__keep__" if settings.get("openai_api_key_set") else "",
                               placeholder="sk-…")
        oa_model = st.text_input("Model", value=settings.get("openai_model", "gpt-4o-mini"))

    c4, c5 = st.columns(2)
    temperature = c4.slider("Creativity (temperature)", 0.0, 1.0,
                            float(settings.get("ai_temperature", 0.3)), 0.05)
    max_tokens = c5.slider("Max response tokens", 300, 2000,
                           int(float(settings.get("ai_max_tokens", 900))), 50)

    csave, ctest = st.columns(2)
    if csave.button("💾 Save AI settings", type="primary", use_container_width=True):
        api.guard(api.put, "/api/settings", {
            "ai_provider": provider,
            "glm_api_key": glm_key, "glm_model": glm_model, "glm_base_url": glm_base_url,
            "hf_api_key": hf_key, "hf_model": hf_model,
            "azure_api_key": az_key, "azure_endpoint": az_endpoint,
            "azure_chat_deployment": az_deploy, "azure_api_version": az_version,
            "openai_api_key": oa_key, "openai_model": oa_model,
            "ai_temperature": temperature, "ai_max_tokens": max_tokens,
        })
        st.success("Saved. The next AI request uses the new provider.")
        st.rerun()
    if ctest.button("🔌 Test AI connection", use_container_width=True):
        with st.spinner("Calling the model…"):
            try:
                res = api.post("/api/ai/test")
                st.success(f"✅ {res['provider']} responded in {res['elapsed_s']}s: “{res['response']}”")
            except api.ApiError as e:
                st.error(f"❌ {e}")

# ----------------------------------------------------------- analytics tab --
with tab_analytics:
    st.markdown("Thresholds used across the dashboards.")
    a1, a2 = st.columns(2)
    otd_target = a1.number_input("On-time delivery target (%)", 50.0, 100.0,
                                 float(settings.get("otd_target_pct", 95)), 0.5)
    outlier_z = a2.number_input("Default outlier z-score threshold", 1.5, 5.0,
                                float(settings.get("outlier_z", 3.0)), 0.25)
    a3, a4 = st.columns(2)
    top_n = a3.number_input("Default Top-N in rankings", 5, 30, int(float(settings.get("top_n", 10))))
    speed_cap = a4.number_input("Speed sanity cap for km/h calc", 60.0, 150.0,
                                float(settings.get("speed_cap_kmph", 110)), 5.0,
                                help="Speeds above this are treated as GPS noise (applied at import)")
    if st.button("💾 Save analytics settings", type="primary"):
        api.guard(api.put, "/api/settings", {
            "otd_target_pct": otd_target, "outlier_z": outlier_z,
            "top_n": top_n, "speed_cap_kmph": speed_cap,
        })
        st.success("Saved.")

# ----------------------------------------------------------------- data tab --
with tab_data:
    meta = api.guard(api.get_fresh, "/api/meta")
    li = meta.get("last_import", {})
    st.markdown(f"""
| | |
|---|---|
| **Rows in database** | {meta.get('rows', 0):,} |
| **Date range** | {meta.get('date_min')} → {meta.get('date_max')} |
| **Last import** | {li.get('imported_at', '—')} |
| **Source file** | `{li.get('source', '—')}` |
| **Geo-mapped trips** | {li.get('geo_mapped_pct', '—')}% |
""")
    st.divider()
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("##### ♻️ Re-import from source Excel")
        st.caption("Wipes the trips table and re-runs the full ETL pipeline.")
        if st.button("Re-import now"):
            with st.spinner("Running ETL…"):
                res = api.guard(api.post, "/api/data/reload")
            st.cache_data.clear()
            st.success(f"Imported {res['rows_imported']:,} rows "
                       f"({res['geo_mapped_pct']}% geo-mapped).")
    with d2:
        st.markdown("##### ⬆️ Upload a new Excel")
        st.caption("Same column layout as the TTA export. Replaces current data.")
        up = st.file_uploader("Choose .xlsx", type=["xlsx"])
        if up is not None and st.button("Import uploaded file", type="primary"):
            with st.spinner("Uploading + running ETL…"):
                try:
                    res = api.post("/api/data/upload", files={"file": (up.name, up.getvalue())})
                    st.cache_data.clear()
                    st.success(f"Imported {res['rows_imported']:,} rows.")
                except api.ApiError as e:
                    st.error(f"❌ {e}")

# ------------------------------------------------------------ API access tab --
with tab_api:
    st.markdown(
        "Every `/api/v1/*` endpoint requires an **`X-API-Key`** header. Share this key "
        "with anyone who should call the API (it can also be pinned via the `TTA_API_KEY` "
        "environment variable — otherwise the backend generates one on first start)."
    )
    if api.API_KEY:
        st.code(api.API_KEY, language=None)
    else:
        st.warning("No API key found yet — start the backend once (run.bat) to generate it.")
    st.markdown(f"""
- **Interactive docs (Swagger):** [{api.BASE_URL}/docs]({api.BASE_URL}/docs) — click **Authorize**, paste the key
- **OpenAPI spec (for Postman / MCP gateways):** [{api.BASE_URL}/api/v1/openapi.json]({api.BASE_URL}/api/v1/openapi.json)
- Exempt from auth: `/health`, `/docs`, the OpenAPI spec
""")
    st.markdown("Quick test from any machine that can reach the backend:")
    st.code(
        f'import requests\n'
        f'kpis = requests.get("{api.BASE_URL}/api/v1/kpis",\n'
        f'                    headers={{"X-API-Key": "<your-key>"}}).json()\n'
        f'print(kpis["current"]["otd_pct"])',
        language="python",
    )
    ui.explain(
        "This key is the lock on the data service — requests without it get a polite 401.",
        "Hand the client the docs link, the key, and the OpenAPI URL; that is the complete integration handover.",
    )
