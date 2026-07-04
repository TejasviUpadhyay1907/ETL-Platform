"""
Page — Ingestion Monitor

Ingestion events, file upload stats, dataset distribution.
"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Ingestion", page_icon="📥", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_number, fmt_bytes, fmt_dt, extract_list, extract_pagination,
    df_to_csv_bytes,
)

init_session()
require_auth()
render_sidebar_user()

st.title("📥 Ingestion Monitor")

with st.sidebar:
    st.subheader("Filters")
    filter_dataset = st.selectbox("Dataset", ["All", "orders", "customers", "products", "inventory", "suppliers", "payments"])
    filter_status  = st.selectbox("Status", ["All", "processed", "rejected", "duplicate", "processing"])
    page_num = st.number_input("Page", min_value=1, value=1, step=1)
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

dataset_param = None if filter_dataset == "All" else filter_dataset
status_param  = None if filter_status  == "All" else filter_status

events_resp = api.list_ingestion_events(page=int(page_num), page_size=50, dataset_type=dataset_param, status=status_param)
events = extract_list(events_resp)
pagination = extract_pagination(events_resp)

if events_resp.get("error"):
    st.error(f"API Error: {events_resp['error']}")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────
total_events  = pagination.get("total_items", len(events))
processed     = sum(1 for e in events if (e.get("status") or "").lower() == "processed")
rejected      = sum(1 for e in events if (e.get("status") or "").lower() == "rejected")
duplicates    = sum(1 for e in events if (e.get("status") or "").lower() == "duplicate")
total_rows    = sum((e.get("row_count") or 0) for e in events)
total_size    = sum((e.get("file_size_bytes") or 0) for e in events)

k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    st.metric("Total Events", fmt_number(total_events))
with k2:
    st.metric("Processed", fmt_number(processed))
with k3:
    st.metric("Rejected", fmt_number(rejected))
with k4:
    st.metric("Duplicates", fmt_number(duplicates))
with k5:
    st.metric("Total Rows", fmt_number(total_rows))

st.markdown("---")

# ── Dataset distribution ───────────────────────────────────────────────────
if events:
    from collections import Counter
    import plotly.graph_objects as go

    ds_counts = Counter(e.get("dataset_type", "unknown") for e in events)
    status_counts = Counter(e.get("status", "unknown") for e in events)

    col_ds, col_st = st.columns(2)
    with col_ds:
        st.subheader("By Dataset Type")
        fig1 = go.Figure(go.Bar(
            x=list(ds_counts.keys()), y=list(ds_counts.values()),
            marker_color="#2563EB", text=list(ds_counts.values()), textposition="outside",
        ))
        fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(color="#F1F5F9"), height=280)
        st.plotly_chart(fig1, use_container_width=True)

    with col_st:
        st.subheader("By Status")
        _SCOL = {"processed": "#22C55E", "rejected": "#EF4444", "duplicate": "#F59E0B", "processing": "#3B82F6"}
        fig2 = go.Figure(go.Pie(
            labels=list(status_counts.keys()),
            values=list(status_counts.values()),
            marker=dict(colors=[_SCOL.get(s, "#6B7280") for s in status_counts.keys()]),
            hole=0.4,
        ))
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#F1F5F9"), height=280)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.subheader("Ingestion Events")

    search_e = st.text_input("🔍 Search events")
    rows = [
        {
            "File":        e.get("original_filename", "—"),
            "Dataset":     e.get("dataset_type", "—"),
            "Status":      e.get("status", "—"),
            "Rows":        fmt_number(e.get("row_count")),
            "Size":        fmt_bytes(e.get("file_size_bytes")),
            "Format":      e.get("file_extension", "—"),
            "Ingested":    fmt_dt(e.get("created_at")),
            "ID":          (e.get("id") or "")[:8] + "…",
        }
        for e in events
    ]
    df_events = pd.DataFrame(rows)
    if search_e:
        sq = search_e.lower()
        df_events = df_events[df_events.apply(lambda row: sq in row.to_string().lower(), axis=1)]

    st.dataframe(df_events, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Export CSV", df_to_csv_bytes(df_events), "ingestion_events.csv", "text/csv")
else:
    st.info("No ingestion events found.")
