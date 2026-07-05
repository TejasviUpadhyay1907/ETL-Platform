import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Warehouse", page_icon="🏭", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_number, fmt_duration, fmt_pct, fmt_dt, extract_data, extract_list,
    df_to_csv_bytes, df_to_excel_bytes,
)
from dashboard.utils.charts import load_metrics_bar

init_session()
require_auth()
render_sidebar_user()

st.title("🏭 Warehouse Dashboard")

# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Filters")
    filter_dataset = st.selectbox("Dataset", ["All", "orders", "customers", "products", "inventory", "suppliers", "payments"])
    page_num = st.number_input("Page", min_value=1, value=1, step=1)
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

dataset_param = None if filter_dataset == "All" else filter_dataset

# ── Load history ───────────────────────────────────────────────────────────
hist_resp = api.get_load_history(page=int(page_num), page_size=50, dataset_type=dataset_param)
load_events = extract_list(hist_resp)

if hist_resp.get("error"):
    st.warning(f"Load history unavailable: {hist_resp['error']}")
    load_events = []

# ── Aggregate KPIs from pipeline history ─────────────────────────────────
pipeline_resp = api.get_pipeline_history(page=1, page_size=100, dataset_type=dataset_param)
runs = extract_list(pipeline_resp)

total_loaded  = sum((r.get("loaded_records") or 0) for r in runs)
total_failed  = sum((r.get("failed_records") or 0) for r in runs)
successful_loads = sum(1 for r in runs if (r.get("loaded_records") or 0) > 0)
load_success_rate = (successful_loads / max(1, len(runs))) * 100 if runs else 0

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.metric("Total Rows Loaded", fmt_number(total_loaded))
with k2:
    st.metric("Total Failed Records", fmt_number(total_failed))
with k3:
    st.metric("Load Success Rate", fmt_pct(load_success_rate))
with k4:
    st.metric("Load Events", fmt_number(len(load_events)))

st.markdown("---")

# ── Strategy breakdown ─────────────────────────────────────────────────────
st.subheader("Load Strategy Distribution")
strategy_counts: dict[str, int] = {}
for ev in load_events:
    metrics = ev.get("metrics") or {}
    strategy = metrics.get("strategy_used", "unknown")
    strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

if strategy_counts:
    import plotly.graph_objects as go
    strat_fig = go.Figure(go.Bar(
        x=list(strategy_counts.keys()),
        y=list(strategy_counts.values()),
        marker_color="#2563EB",
        text=list(strategy_counts.values()),
        textposition="outside",
    ))
    strat_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F1F5F9"), height=280, title="Load Strategy Usage",
    )
    st.plotly_chart(strat_fig, use_container_width=True)
else:
    st.info("No load strategy data available.")

# ── Rows loaded over time ─────────────────────────────────────────────────
if runs:
    st.subheader("Rows Loaded Over Time")
    trend_rows = [
        {"Run": r.get("run_number", "—"), "Loaded": r.get("loaded_records") or 0,
         "Dataset": r.get("dataset_type", "—")}
        for r in runs if (r.get("loaded_records") or 0) > 0
    ]
    if trend_rows:
        trend_df = pd.DataFrame(trend_rows)
        import plotly.express as px
        fig = px.bar(trend_df, x="Run", y="Loaded", color="Dataset",
                     title="Records Loaded per Pipeline Run")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#F1F5F9"), height=300)
        st.plotly_chart(fig, use_container_width=True)

# ── Load history table ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Load Event Log")
if load_events:
    load_rows = []
    for ev in load_events:
        metrics = ev.get("metrics") or {}
        load_rows.append({
            "Run ID":    (ev.get("run_id") or "—")[:8] + "…",
            "Success":   "✅" if ev.get("success") else "❌",
            "Loaded":    fmt_number(metrics.get("rows_loaded") or metrics.get("rows_inserted", 0)),
            "Inserted":  fmt_number(metrics.get("rows_inserted", 0)),
            "Updated":   fmt_number(metrics.get("rows_updated", 0)),
            "Failed":    fmt_number(metrics.get("rows_failed", 0)),
            "Strategy":  metrics.get("strategy_used", "—"),
            "Table":     metrics.get("target_table", "—"),
            "Time":      fmt_dt(ev.get("created_at")),
        })
    df_load = pd.DataFrame(load_rows)
    st.dataframe(df_load, use_container_width=True, hide_index=True)

    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        st.download_button("⬇️ CSV", df_to_csv_bytes(df_load), "load_history.csv", "text/csv", use_container_width=True)
    with col_exp2:
        st.download_button("⬇️ Excel", df_to_excel_bytes(df_load), "load_history.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    # ── Per-run detail ──────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Per-Run Load Detail")
    run_ids_with_data = [ev.get("run_id") for ev in load_events if ev.get("run_id")]
    if run_ids_with_data:
        selected_run = st.selectbox("Select Run", run_ids_with_data[:20],
                                    format_func=lambda x: x[:8] + "…" if x else "—")
        if selected_run:
            detail_resp = api.get_load_report(selected_run)
            if not detail_resp.get("error"):
                detail = extract_data(detail_resp) or {}
                metrics = detail.get("metrics", detail)
                if metrics:
                    st.plotly_chart(load_metrics_bar(metrics), use_container_width=True)
                    with st.expander("Full Load Report JSON"):
                        st.json(detail)
else:
    st.info("No load events found. Run a pipeline to see load data.")
