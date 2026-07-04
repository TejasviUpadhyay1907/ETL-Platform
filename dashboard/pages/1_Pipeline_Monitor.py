"""
Page 2 — Pipeline Monitor

Shows running, queued, completed, failed pipelines with live-refresh.
"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Pipeline Monitor", page_icon="🔄", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_number, fmt_duration, fmt_pct, status_badge,
    fmt_dt, extract_list, safe_df,
)
from dashboard.utils.charts import stage_duration_bar, stage_timeline, pipeline_status_donut

init_session()
require_auth()
render_sidebar_user()

st.title("🔄 Pipeline Monitor")

# ── Sidebar filters ───────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Filters")
    filter_status = st.selectbox(
        "Status", ["All", "running", "completed", "succeeded", "failed", "cancelled", "retrying"]
    )
    filter_dataset = st.selectbox(
        "Dataset", ["All", "orders", "customers", "products", "inventory", "suppliers", "payments"]
    )
    page_size = st.slider("Rows per page", 10, 100, 20)
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ── Fetch ─────────────────────────────────────────────────────────────────
status_param = None if filter_status == "All" else filter_status
dataset_param = None if filter_dataset == "All" else filter_dataset

result = api.list_pipelines(page=1, page_size=100, status=status_param, dataset_type=dataset_param)
runs = extract_list(result)

if result.get("error"):
    st.error(f"API Error: {result['error']}")
    st.stop()

# ── Summary cards ─────────────────────────────────────────────────────────
running   = [r for r in runs if r.get("status") == "running"]
queued    = [r for r in runs if r.get("status") in ("queued", "pending")]
completed = [r for r in runs if r.get("status") in ("completed", "succeeded")]
failed    = [r for r in runs if r.get("status") == "failed"]
retrying  = [r for r in runs if r.get("status") == "retrying"]

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("🔄 Running",   len(running))
with c2:
    st.metric("⏳ Queued",    len(queued))
with c3:
    st.metric("✅ Completed", len(completed))
with c4:
    st.metric("❌ Failed",    len(failed))
with c5:
    st.metric("🔁 Retrying",  len(retrying))

# ── Status donut ──────────────────────────────────────────────────────────
if runs:
    from collections import Counter
    counts = dict(Counter(r.get("status", "unknown") for r in runs))
    col_d, col_tbl = st.columns([1, 2])
    with col_d:
        st.plotly_chart(pipeline_status_donut(counts), use_container_width=True)
    with col_tbl:
        st.subheader("All Runs")
        rows = [
            {
                "Run #":     r.get("run_number", "—"),
                "Pipeline":  r.get("pipeline_name", "—"),
                "Dataset":   r.get("dataset_type", "—"),
                "Status":    status_badge(r.get("status", "—")),
                "Records":   fmt_number(r.get("total_records")),
                "Quality":   fmt_pct(r.get("quality_score")),
                "Duration":  fmt_duration(r.get("duration_seconds")),
                "Started":   fmt_dt(r.get("started_at")),
                "By":        r.get("triggered_by", "—"),
            }
            for r in runs[:page_size]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No pipeline runs match the current filters.")

st.markdown("---")

# ── Run detail drill-down ─────────────────────────────────────────────────
st.subheader("Run Detail")
run_ids = [r.get("id", "") for r in runs if r.get("id")]
if run_ids:
    selected_id = st.selectbox("Select a run to inspect", run_ids, format_func=lambda x: x[:8] + "…")
    if selected_id:
        detail = api.get_pipeline_run(selected_id)
        if detail.get("error"):
            st.error(detail["error"])
        else:
            run_data = detail.get("data", {})
            d1, d2, d3 = st.columns(3)
            with d1:
                st.metric("Status", status_badge(run_data.get("status", "—")))
                st.metric("Total Records", fmt_number(run_data.get("total_records")))
            with d2:
                st.metric("Quality Score", fmt_pct(run_data.get("quality_score")))
                st.metric("Duration", fmt_duration(run_data.get("duration_seconds")))
            with d3:
                st.metric("Error", run_data.get("error_message", "None") or "None")

            stages = run_data.get("stage_results", [])
            if stages:
                st.subheader("Stage Timeline")
                st.plotly_chart(stage_timeline(stages), use_container_width=True)

                stage_dur = {
                    s.get("stage_name", ""): s.get("duration_ms", 0)
                    for s in stages if s.get("duration_ms")
                }
                if stage_dur:
                    st.plotly_chart(stage_duration_bar(stage_dur), use_container_width=True)

                st.subheader("Stage Results")
                stage_rows = [
                    {
                        "Stage":    s.get("stage_name"),
                        "Status":   status_badge(s.get("status", "—")),
                        "Input":    fmt_number(s.get("input_records")),
                        "Output":   fmt_number(s.get("output_records")),
                        "Duration": fmt_duration((s.get("duration_ms") or 0) / 1000),
                        "Error":    s.get("error_message") or "—",
                    }
                    for s in stages
                ]
                st.dataframe(pd.DataFrame(stage_rows), use_container_width=True, hide_index=True)

            # Checkpoint info
            if st.checkbox("Show Checkpoints"):
                chk = api.get_pipeline_checkpoints(selected_id)
                chk_data = chk.get("data", [])
                if chk_data:
                    st.json(chk_data)
                else:
                    st.info("No checkpoints found.")

            # Action buttons
            st.markdown("---")
            act1, act2 = st.columns(2)
            with act1:
                if run_data.get("status") == "running":
                    if st.button("⛔ Cancel Run", type="secondary"):
                        res = api.cancel_pipeline(selected_id)
                        if res.get("error"):
                            st.error(res["error"])
                        else:
                            st.success("Cancellation requested.")
                            st.rerun()
            with act2:
                if run_data.get("status") == "failed":
                    if st.button("🔁 Retry Run", type="primary"):
                        res = api.retry_pipeline(selected_id)
                        if res.get("error"):
                            st.error(res["error"])
                        else:
                            st.success("Retry triggered.")
                            st.rerun()
else:
    st.info("No runs available to inspect.")
