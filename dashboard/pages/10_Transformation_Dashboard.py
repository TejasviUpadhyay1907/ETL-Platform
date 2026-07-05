import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Transformation", page_icon="⚗️", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_number, fmt_pct, fmt_duration, fmt_dt, extract_list, extract_data,
)

init_session()
require_auth()
render_sidebar_user()

st.title("⚗️ Transformation Dashboard")

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

# ── KPIs ──────────────────────────────────────────────────────────────────
total_input  = sum((r.get("total_records") or 0) for r in runs)
total_output = sum((r.get("valid_records") or r.get("total_records") or 0) for r in runs)
transform_rate = (total_output / max(1, total_input)) * 100

k1, k2, k3 = st.columns(3)
with k1:
    st.metric("Total Input Records",   fmt_number(total_input))
with k2:
    st.metric("Total Output Records",  fmt_number(total_output))
with k3:
    st.metric("Transformation Rate",   fmt_pct(transform_rate))

st.markdown("---")

# ── Throughput per run ─────────────────────────────────────────────────────
st.subheader("Transformation Throughput by Run")
throughput_rows = [
    {
        "Run":     r.get("run_number", "—"),
        "Input":   r.get("total_records") or 0,
        "Output":  r.get("valid_records") or 0,
        "Dataset": r.get("dataset_type", "—"),
    }
    for r in runs[:30] if (r.get("total_records") or 0) > 0
]
if throughput_rows:
    tp_df = pd.DataFrame(throughput_rows)
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Bar(x=tp_df["Run"], y=tp_df["Input"],  name="Input",  marker_color="#3B82F6"))
    fig.add_trace(go.Bar(x=tp_df["Run"], y=tp_df["Output"], name="Output", marker_color="#22C55E"))
    fig.update_layout(
        barmode="group", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F1F5F9"), height=300, title="Input vs Output Records",
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Stage detail drill-down ────────────────────────────────────────────────
st.markdown("---")
st.subheader("Transformation Stage Detail")
run_options = {f"{r.get('run_number','?')} ({r.get('dataset_type','')})" : r.get("id") for r in runs if r.get("id")}
if run_options:
    sel_label = st.selectbox("Select run", list(run_options.keys()))
    sel_id = run_options[sel_label]
    detail_resp = api.get_pipeline_run(sel_id)
    detail = extract_data(detail_resp) or {}
    stages = detail.get("stage_results", [])
    trans_stage = next((s for s in stages if s.get("stage_name") == "transformation"), None)

    if trans_stage:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Input Records",  fmt_number(trans_stage.get("input_records")))
        with c2:
            st.metric("Output Records", fmt_number(trans_stage.get("output_records")))
        with c3:
            st.metric("Status",         trans_stage.get("status", "—"))
        with c4:
            st.metric("Duration",       fmt_duration((trans_stage.get("duration_ms") or 0) / 1000))

        if trans_stage.get("error_message"):
            st.error(f"Error: {trans_stage['error_message']}")

        # Show all stage metrics
        all_stage_rows = [
            {
                "Stage":    s.get("stage_name", "—"),
                "Status":   s.get("status", "—"),
                "Input":    fmt_number(s.get("input_records")),
                "Output":   fmt_number(s.get("output_records")),
                "Duration": fmt_duration((s.get("duration_ms") or 0) / 1000),
            }
            for s in stages
        ]
        st.subheader("All Stages")
        st.dataframe(pd.DataFrame(all_stage_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No transformation stage data for this run.")

    # Metrics
    metrics_resp = api.get_pipeline_metrics(sel_id)
    metrics = extract_data(metrics_resp) or {}
    if metrics:
        st.markdown("---")
        st.subheader("Pipeline Metrics")
        stage_durs = metrics.get("stage_metrics") or {}
        if stage_durs:
            from dashboard.utils.charts import stage_duration_bar
            try:
                # stage_metrics may be in seconds or ms format
                dur_ms = {k: v * 1000 if v < 1000 else v for k, v in stage_durs.items()}
                st.plotly_chart(stage_duration_bar(dur_ms), use_container_width=True)
            except Exception:
                st.json(stage_durs)
