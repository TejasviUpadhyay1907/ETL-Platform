import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Audit Log", page_icon="🔍", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_dt, fmt_dt_relative, extract_list,
    df_to_csv_bytes, df_to_excel_bytes,
)

init_session()
require_auth()
render_sidebar_user()

st.title("🔍 Audit Log")

# ── Load pipeline runs to find audit events ────────────────────────────────
history_resp = api.get_pipeline_history(page=1, page_size=50)
runs = extract_list(history_resp)

with st.sidebar:
    st.subheader("Filters")
    filter_run = st.selectbox(
        "Pipeline Run",
        ["All runs"] + [f"{r.get('run_number','?')} — {(r.get('id','')[:8]+'…')}" for r in runs[:30]],
    )
    filter_event = st.selectbox(
        "Event Type",
        ["All", "PIPELINE_STARTED", "PIPELINE_COMPLETED", "PIPELINE_FAILED",
         "STAGE_STARTED", "STAGE_COMPLETED", "STAGE_FAILED",
         "RECORD_LOADED", "API_REQUEST", "API_ERROR",
         "FILE_INGESTED", "FILE_REJECTED"],
    )
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ── Determine which run to show ────────────────────────────────────────────
selected_run_id = None
if filter_run != "All runs" and runs:
    idx = ([f"{r.get('run_number','?')} — {(r.get('id','')[:8]+'…')}" for r in runs[:30]]).index(filter_run)
    selected_run_id = runs[idx].get("id") if idx < len(runs) else None

# ── Fetch events ───────────────────────────────────────────────────────────
all_events: list[dict] = []

if selected_run_id:
    event_type_param = None if filter_event == "All" else filter_event
    events_resp = api.get_pipeline_events(selected_run_id, page=1, page_size=100)
    if not events_resp.get("error"):
        all_events = extract_list(events_resp)
    else:
        st.warning(f"Could not load events: {events_resp['error']}")
else:
    # Show events from multiple recent runs
    for run in runs[:10]:
        run_id = run.get("id")
        if not run_id:
            continue
        resp = api.get_pipeline_events(run_id, page=1, page_size=20)
        if not resp.get("error"):
            for ev in extract_list(resp):
                ev["_run_number"] = run.get("run_number", "?")
                ev["_run_id"] = run_id
                all_events.append(ev)

# ── Filter by event type (client-side) ────────────────────────────────────
if filter_event != "All" and all_events:
    all_events = [ev for ev in all_events if ev.get("event_type") == filter_event]

# ── Search ─────────────────────────────────────────────────────────────────
search_q = st.text_input("🔍 Search audit log", placeholder="event type, message, stage…")
if search_q:
    sq = search_q.lower()
    all_events = [ev for ev in all_events if sq in str(ev).lower()]

# ── KPI summary ───────────────────────────────────────────────────────────
if all_events:
    from collections import Counter
    type_counts = Counter(ev.get("event_type", "?") for ev in all_events)
    severity_counts = Counter(ev.get("severity", "INFO") for ev in all_events)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Total Events", len(all_events))
    with k2:
        st.metric("Error Events", severity_counts.get("ERROR", 0))
    with k3:
        st.metric("Warning Events", severity_counts.get("WARNING", 0))
    with k4:
        st.metric("Pipeline Failures", type_counts.get("PIPELINE_FAILED", 0))

    st.markdown("---")

    # ── Event type distribution chart ─────────────────────────────────────
    col_chart, col_table = st.columns([1, 2])

    with col_chart:
        st.subheader("Event Distribution")
        import plotly.graph_objects as go
        top_types = dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        fig = go.Figure(go.Bar(
            x=list(top_types.values()), y=list(top_types.keys()),
            orientation="h",
            marker_color="#2563EB",
            text=list(top_types.values()), textposition="outside",
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#F1F5F9"), height=350, margin=dict(l=150, r=20, t=30, b=30),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.subheader(f"Audit Events ({len(all_events)})")
        _SICONS = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚨", "DEBUG": "🔵"}
        rows = [
            {
                "Sev":         _SICONS.get(ev.get("severity", "INFO"), "ℹ️"),
                "Event Type":  ev.get("event_type", "—"),
                "Stage":       ev.get("stage") or "—",
                "Message":     (ev.get("message") or "")[:80],
                "Time":        fmt_dt(ev.get("created_at")),
                "Run":         ev.get("_run_number", "—"),
            }
            for ev in all_events[:200]
        ]
        df_events = pd.DataFrame(rows)
        st.dataframe(df_events, use_container_width=True, hide_index=True)

    # ── Export ─────────────────────────────────────────────────────────────
    st.markdown("---")
    exp_df = pd.DataFrame([
        {"event_type": e.get("event_type"), "severity": e.get("severity"),
         "stage": e.get("stage"), "message": e.get("message"),
         "created_at": e.get("created_at")}
        for e in all_events
    ])
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Export CSV", df_to_csv_bytes(exp_df), "audit_log.csv", "text/csv", use_container_width=True)
    with c2:
        st.download_button("⬇️ Export Excel", df_to_excel_bytes(exp_df), "audit_log.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    # ── Event timeline ─────────────────────────────────────────────────────
    if len(all_events) >= 3:
        st.markdown("---")
        st.subheader("Event Timeline")
        timeline_df = pd.DataFrame([
            {"Time": fmt_dt(e.get("created_at")), "Event": e.get("event_type"), "Severity": e.get("severity", "INFO")}
            for e in all_events[-50:]
        ])
        import plotly.express as px
        sev_colors = {"INFO": "#3B82F6", "WARNING": "#F59E0B", "ERROR": "#EF4444", "CRITICAL": "#DC2626"}
        fig2 = px.scatter(
            timeline_df, x="Time", y="Event", color="Severity",
            color_discrete_map=sev_colors, title="Recent Audit Events",
            height=350,
        )
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(color="#F1F5F9"))
        st.plotly_chart(fig2, use_container_width=True)

else:
    st.info("No audit events found. Select a specific run or run a pipeline to generate events.")
