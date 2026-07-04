"""
Page 5 — Cleaning Dashboard

Rows cleaned, cells modified, duplicate removal, missing value handling.
Data sourced from pipeline run metrics via the pipeline API.
"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Cleaning Dashboard", page_icon="🧹", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_number, fmt_pct, fmt_duration, fmt_dt, extract_list, extract_data,
)

init_session()
require_auth()
render_sidebar_user()

st.title("🧹 Cleaning Dashboard")

# ── Fetch pipeline history ────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Filters")
    filter_dataset = st.selectbox("Dataset", ["All", "orders", "customers", "products", "inventory", "suppliers", "payments"])
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

dataset_param = None if filter_dataset == "All" else filter_dataset
history_resp = api.get_pipeline_history(page=1, page_size=100, dataset_type=dataset_param)
runs = extract_list(history_resp)

if not runs:
    st.info("No pipeline runs available.")
    st.stop()

# ── Aggregate cleaning metrics from run data ───────────────────────────────
total_input   = sum((r.get("total_records") or 0) for r in runs)
total_cleaned = sum((r.get("cleaned_records") or r.get("valid_records") or 0) for r in runs)
total_dropped = sum(max(0, (r.get("total_records") or 0) - (r.get("cleaned_records") or r.get("valid_records") or r.get("total_records") or 0)) for r in runs)
clean_rate    = (total_cleaned / max(1, total_input)) * 100

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total Rows Input",   fmt_number(total_input))
with k2:
    st.metric("Rows Cleaned",       fmt_number(total_cleaned))
with k3:
    st.metric("Rows Dropped",       fmt_number(total_dropped))
with k4:
    st.metric("Clean Rate",         fmt_pct(clean_rate))

st.markdown("---")

# ── Cleaning rate trend ────────────────────────────────────────────────────
if runs:
    st.subheader("Cleaning Rate Trend")
    trend_rows = [
        {
            "Run":     r.get("run_number", "—"),
            "Input":   r.get("total_records") or 0,
            "Cleaned": r.get("cleaned_records") or r.get("valid_records") or 0,
            "Dataset": r.get("dataset_type", "—"),
            "Rate %":  round(((r.get("cleaned_records") or r.get("valid_records") or 0) / max(1, r.get("total_records") or 1)) * 100, 1),
        }
        for r in runs[:30]
    ]
    trend_df = pd.DataFrame(trend_rows)

    import plotly.express as px
    fig = px.line(trend_df, x="Run", y="Rate %", color="Dataset",
                  title="Cleaning Pass Rate by Run", markers=True)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#F1F5F9"), height=300)
    fig.add_hline(y=95, line_dash="dash", line_color="#22C55E", annotation_text="Target 95%")
    st.plotly_chart(fig, use_container_width=True)

# ── Per-run detail ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Per-Run Cleaning Summary")

rows = [
    {
        "Run #":      r.get("run_number", "—"),
        "Dataset":    r.get("dataset_type", "—"),
        "Input":      fmt_number(r.get("total_records")),
        "Cleaned":    fmt_number(r.get("cleaned_records") or r.get("valid_records")),
        "Dropped":    fmt_number(max(0, (r.get("total_records") or 0) - (r.get("cleaned_records") or r.get("valid_records") or r.get("total_records") or 0))),
        "Quality %":  fmt_pct(r.get("quality_score")),
        "Duration":   fmt_duration(r.get("duration_seconds")),
        "Date":       fmt_dt(r.get("started_at")),
    }
    for r in runs[:50]
]
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Run detail drill-down ─────────────────────────────────────────────────
st.markdown("---")
st.subheader("Stage Detail for a Run")
run_options = {f"{r.get('run_number','?')} ({r.get('dataset_type','')})" : r.get("id") for r in runs if r.get("id")}
if run_options:
    sel_label = st.selectbox("Select run", list(run_options.keys()))
    sel_id = run_options[sel_label]
    detail_resp = api.get_pipeline_run(sel_id)
    detail = extract_data(detail_resp) or {}
    stage_results = detail.get("stage_results", [])
    cleaning_stage = next((s for s in stage_results if s.get("stage_name") == "cleaning"), None)
    if cleaning_stage:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Input Records",  fmt_number(cleaning_stage.get("input_records")))
        with c2:
            st.metric("Output Records", fmt_number(cleaning_stage.get("output_records")))
        with c3:
            st.metric("Rejected",       fmt_number(cleaning_stage.get("rejected_records")))
        st.metric("Status",  cleaning_stage.get("status", "—"))
        if cleaning_stage.get("error_message"):
            st.error(f"Error: {cleaning_stage['error_message']}")
    else:
        st.info("No cleaning stage data for this run.")
