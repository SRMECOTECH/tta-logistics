"""Raw trip explorer with export."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from lib import api, ui

ui.setup_page("Data Explorer", "🔎")
ui.page_intro(
    "The raw trip records behind every chart in this app — searchable, filterable, exportable. "
    "When a chart raises a question, this is where you find the individual trips that answer it."
)
params = ui.sidebar_filters()

limit = st.select_slider("Rows to load", [250, 500, 1000, 2500, 5000], value=500)
rows = api.guard(api.get, "/api/records", {**params, "limit": limit})
df = pd.DataFrame(rows)

if df.empty:
    st.info("No records for the current filters.")
    st.stop()

search = st.text_input("🔍 Quick search (vehicle, driver, destination, transporter…)")
if search:
    mask = df.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
    df = df[mask]

st.caption(f"{len(df):,} rows shown (latest departures first)")
st.dataframe(
    df, use_container_width=True, hide_index=True, height=560,
    column_config={
        "delivery_status": st.column_config.TextColumn("Delivery"),
        "transit_hours": st.column_config.NumberColumn("Transit h", format="%.1f"),
        "planned_transit_hours": st.column_config.NumberColumn("Planned h", format="%.1f"),
    },
)
st.download_button("⬇️ Download CSV", df.to_csv(index=False), "trips_export.csv", "text/csv")
