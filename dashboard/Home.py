"""
ETL Platform Operations Dashboard — Entry Point

Run with:
    streamlit run dashboard/Home.py

The Home page shows the login form and, after authentication,
redirects to the Executive Overview.
"""
import streamlit as st

st.set_page_config(
    page_title="ETL Platform Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.utils.auth import init_session, is_authenticated, _render_login_form, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import fmt_number, fmt_pct, status_badge, fmt_duration, extract_data

init_session()
render_sidebar_user()

# ── Sidebar navigation hint ───────────────────────────────────────────────
st.sidebar.title("⚡ ETL Platform")
st.sidebar.caption("Operations Dashboard")
st.sidebar.markdown("---")
st.sidebar.info("Use the pages menu (▸ above) to navigate between modules.")

# ── Main content ──────────────────────────────────────────────────────────
if not is_authenticated():
    st.title("⚡ ETL Platform Operations Dashboard")
    st.markdown(
        "Enterprise monitoring and control center for the ETL pipeline platform. "
        "Log in to get started."
    )
    _render_login_form()
    st.stop()

# ── Authenticated: show executive summary ────────────────────────────────
st.title("⚡ ETL Platform — Executive Overview")

# ── System status banner ──────────────────────────────────────────────────
health = api.get_health()
health_data = extract_data(health) or {}
system_status = health_data.get("status", "unknown")

if system_status == "healthy":
    st.success(f"✅ System Status: **{system_status.upper()}** — All services operational")
elif system_status == "degraded":
    st.warning(f"⚠️ System Status: **{system_status.upper()}** — Some services degraded")
else:
    st.error(f"❌ System Status: **{system_status.upper()}** — Check API server")

col_status = st.columns(4)
with col_status[0]:
    st.metric("Environment", health_data.get("environment", "—").title())
with col_status[1]:
    st.metric("Version", health_data.get("version", "—"))
with col_status[2]:
    uptime = health_data.get("uptime_seconds")
    st.metric("Uptime", fmt_duration(uptime))
with col_status[3]:
    st.metric("Database", health_data.get("database", "—").title())

st.markdown("---")

# ── KPI cards from pipeline history ───────────────────────────────────────
history = api.get_pipeline_history(page=1, page_size=100)
runs: list[dict] = []
if not history.get("error"):
    runs = history.get("data", [])

total_runs = len(runs)
success_runs = sum(1 for r in runs if r.get("status") in ("completed", "succeeded"))
failed_runs = sum(1 for r in runs if r.get("status") == "failed")
running_runs = sum(1 for r in runs if r.get("status") == "running")
success_rate = (success_runs / total_runs * 100) if total_runs else 0
total_records = sum(r.get("total_records") or 0 for r in runs)
avg_duration = (
    sum(r.get("duration_seconds") or 0 for r in runs if r.get("duration_seconds")) /
    max(1, sum(1 for r in runs if r.get("duration_seconds")))
)

k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    st.metric("Total Runs", fmt_number(total_runs))
with k2:
    delta_color = "normal" if success_rate >= 90 else "inverse"
    st.metric("Success Rate", fmt_pct(success_rate), delta=None)
with k3:
    st.metric("Failed Runs", fmt_number(failed_runs))
with k4:
    st.metric("Running Now", fmt_number(running_runs))
with k5:
    st.metric("Records Processed", fmt_number(total_records))
with k6:
    st.metric("Avg Duration", fmt_duration(avg_duration))

st.markdown("---")

# ── Charts ────────────────────────────────────────────────────────────────
import plotly.graph_objects as go
from dashboard.utils.charts import pipeline_status_donut, records_funnel
import pandas as pd

col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Pipeline Status Distribution")
    if runs:
        from collections import Counter
        status_counts = dict(Counter(r.get("status", "unknown") for r in runs))
        fig = pipeline_status_donut(status_counts)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No pipeline run data available.")

with col_chart2:
    st.subheader("Records Funnel (all runs)")
    if runs:
        total_i = sum(r.get("total_records") or 0 for r in runs)
        total_v = sum(r.get("valid_records") or r.get("total_records") or 0 for r in runs)
        total_c = total_v
        total_l = sum(r.get("loaded_records") or 0 for r in runs) if any(r.get("loaded_records") for r in runs) else total_v
        if total_i > 0:
            fig2 = records_funnel(total_i, total_v, total_c, total_l)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No record counts available.")
    else:
        st.info("No data.")

st.markdown("---")

# ── Recent activity table ─────────────────────────────────────────────────
st.subheader("Recent Pipeline Runs")
if runs:
    recent = runs[:10]
    rows = []
    for r in recent:
        rows.append({
            "Run #": r.get("run_number", "—"),
            "Pipeline": r.get("pipeline_name", "—"),
            "Dataset": r.get("dataset_type", "—"),
            "Status": status_badge(r.get("status", "—")),
            "Records": fmt_number(r.get("total_records")),
            "Quality": fmt_pct(r.get("quality_score")),
            "Duration": fmt_duration(r.get("duration_seconds")),
            "Started": r.get("created_at", "—")[:19] if r.get("created_at") else "—",
            "Triggered By": r.get("triggered_by", "—"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No recent pipeline runs found.")

# ── Auto-refresh ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.subheader("⚙️ Refresh Settings")
    auto_refresh = st.checkbox("Auto Refresh", value=False)
    if auto_refresh:
        interval = st.selectbox("Interval", [10, 30, 60, 120], index=1)
        st.caption(f"Refreshing every {interval}s")
        import time
        time.sleep(interval)
        st.rerun()
    if st.button("🔄 Refresh Now", use_container_width=True):
        st.rerun()
