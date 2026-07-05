import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
"""
Page 3 — Pipeline History

Searchable, filterable, sortable execution history with CSV/Excel export.
"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Pipeline History", page_icon="📋", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_number, fmt_duration, fmt_pct, status_badge, fmt_dt,
    extract_list, extract_pagination, safe_df,
    df_to_csv_bytes, df_to_excel_bytes,
)

init_session()
require_auth()
render_sidebar_user()

st.title("📋 Pipeline History")

# ── Sidebar filters ───────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Filters")
    filter_status = st.selectbox("Status", ["All", "completed", "succeeded", "failed", "cancelled", "running"])
    filter_dataset = st.selectbox("Dataset", ["All", "orders", "customers", "products", "inventory", "suppliers", "payments"])
    page_num = st.number_input("Page", min_value=1, value=1, step=1)
    page_size = st.selectbox("Page Size", [20, 50, 100], index=0)

# ── Fetch ─────────────────────────────────────────────────────────────────
status_param  = None if filter_status  == "All" else filter_status
dataset_param = None if filter_dataset == "All" else filter_dataset

result = api.get_pipeline_history(
    page=int(page_num), page_size=int(page_size),
    dataset_type=dataset_param, status=status_param,
)

if result.get("error"):
    st.error(f"API Error: {result['error']}")
    st.stop()

runs = extract_list(result)
pagination = extract_pagination(result)

# ── Search filter (client-side) ───────────────────────────────────────────
search_query = st.text_input("🔍 Search by pipeline name, run number, or triggered by")
if search_query:
    q = search_query.lower()
    runs = [
        r for r in runs
        if q in (r.get("pipeline_name") or "").lower()
        or q in (r.get("run_number") or "").lower()
        or q in (r.get("triggered_by") or "").lower()
        or q in (r.get("dataset_type") or "").lower()
    ]

st.caption(f"Showing {len(runs)} of {fmt_number(pagination.get('total_items', 0))} runs")

# ── Build display DataFrame ───────────────────────────────────────────────
if runs:
    rows = [
        {
            "Run #":       r.get("run_number", "—"),
            "Pipeline":    r.get("pipeline_name", "—"),
            "Dataset":     r.get("dataset_type", "—"),
            "Status":      status_badge(r.get("status", "—")),
            "Records":     fmt_number(r.get("total_records")),
            "Quality %":   fmt_pct(r.get("quality_score")),
            "Duration":    fmt_duration(r.get("duration_seconds")),
            "Started":     fmt_dt(r.get("started_at")),
            "Completed":   fmt_dt(r.get("completed_at")),
            "Triggered By": r.get("triggered_by", "—"),
            "ID":          (r.get("id") or "")[:8] + "…",
        }
        for r in runs
    ]
    df_display = pd.DataFrame(rows)

    # Sortable via column selection
    sort_col = st.selectbox("Sort by", df_display.columns.tolist(), index=df_display.columns.tolist().index("Started"))
    sort_asc = st.checkbox("Ascending", value=False)
    df_display = df_display.sort_values(sort_col, ascending=sort_asc)

    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── Pagination ──────────────────────────────────────────────────────────
    total_pages = pagination.get("total_pages", 1)
    pg_cols = st.columns(3)
    with pg_cols[0]:
        st.caption(f"Page {page_num} of {total_pages}")
    with pg_cols[1]:
        if pagination.get("has_previous") and st.button("← Previous"):
            st.query_params["page"] = str(int(page_num) - 1)
    with pg_cols[2]:
        if pagination.get("has_next") and st.button("Next →"):
            st.query_params["page"] = str(int(page_num) + 1)

    # ── Export ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Export")
    export_df = pd.DataFrame([
        {
            "run_number":   r.get("run_number"),
            "pipeline_name":r.get("pipeline_name"),
            "dataset_type": r.get("dataset_type"),
            "status":       r.get("status"),
            "total_records":r.get("total_records"),
            "quality_score":r.get("quality_score"),
            "duration_s":   r.get("duration_seconds"),
            "started_at":   r.get("started_at"),
            "completed_at": r.get("completed_at"),
            "triggered_by": r.get("triggered_by"),
        }
        for r in runs
    ])
    exp1, exp2 = st.columns(2)
    with exp1:
        st.download_button(
            "⬇️ Download CSV",
            data=df_to_csv_bytes(export_df),
            file_name="pipeline_history.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with exp2:
        st.download_button(
            "⬇️ Download Excel",
            data=df_to_excel_bytes(export_df),
            file_name="pipeline_history.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
else:
    st.info("No pipeline history matches the current filters.")
