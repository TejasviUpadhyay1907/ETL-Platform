import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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

st.title("📥 Data Ingestion")

# ═══════════════════════════════════════════════════════════════════════════
# UPLOAD SECTION — top of page
# ═══════════════════════════════════════════════════════════════════════════
st.subheader("Upload & Process a File")
st.info("Upload a CSV or Excel file. The system will ingest it, validate data quality, clean it, transform it, and load it to the warehouse automatically.")

col_up, col_info = st.columns([2, 1])

with col_up:
    uploaded_file = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        help="Supported: CSV, Excel (.xlsx, .xls). Max 100 MB.",
    )

    dataset_type = st.selectbox(
        "Dataset Type",
        ["orders", "customers", "products", "inventory", "suppliers", "payments"],
        help="Tell the system what kind of data this file contains.",
    )

    col_b1, col_b2 = st.columns(2)

    with col_b1:
        upload_btn = st.button("📤 Upload File", type="primary",
                               disabled=(uploaded_file is None),
                               use_container_width=True)

    with col_b2:
        run_pipeline = st.checkbox("Also run full ETL pipeline after upload",
                                   value=True,
                                   help="Validation → Cleaning → Transformation → Loading")

with col_info:
    st.markdown("**Sample files to try:**")
    # Load sample files for download
    sample_files = {
        "orders_valid.csv":    "data/sample/orders_valid.csv",
        "customers_valid.csv": "data/sample/customers_valid.csv",
        "products_valid.csv":  "data/sample/products_valid.csv",
        "orders_with_errors.csv": "data/sample/orders_with_errors.csv",
    }
    for name, path in sample_files.items():
        try:
            content = open(path, "rb").read()
            st.download_button(
                f"⬇️ {name}",
                data=content,
                file_name=name,
                mime="text/csv",
                use_container_width=True,
                key=f"dl_{name}",
            )
        except FileNotFoundError:
            pass

# ── Handle upload ──────────────────────────────────────────────────────────
if upload_btn and uploaded_file is not None:
    with st.spinner(f"Uploading {uploaded_file.name}…"):
        import httpx

        token = st.session_state.get("access_token", "")
        base  = st.session_state.get("api_url", "https://etl-platform-api.onrender.com")

        try:
            r = httpx.post(
                f"{base}/api/v1/ingest/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (uploaded_file.name, uploaded_file.getvalue(),
                                uploaded_file.type or "text/csv")},
                data={"dataset_type": dataset_type},
                timeout=120,
            )

            if r.status_code in (200, 201):
                data = r.json().get("data", {})
                ing_id = data.get("ingestion_event_id", "")

                st.success(f"✅ File uploaded successfully!")

                m1, m2, m3, m4 = st.columns(4)
                with m1: st.metric("Rows Ingested", fmt_number(data.get("row_count")))
                with m2: st.metric("Dataset Type",  data.get("dataset_type", dataset_type))
                with m3: st.metric("File Size",     fmt_bytes(data.get("file_size_bytes")))
                with m4: st.metric("Event ID",      ing_id[:8] + "…" if ing_id else "—")

                # Run full pipeline if requested
                if run_pipeline:
                    st.markdown("---")
                    st.subheader("🚀 Running ETL Pipeline…")
                    st.info("Ingestion → Validation → Cleaning → Transformation → Loading")

                    with st.spinner("Pipeline running (this takes 10-30 seconds)…"):
                        pr = httpx.post(
                            f"{base}/api/v1/pipelines/run",
                            headers={"Authorization": f"Bearer {token}",
                                     "Content-Type": "application/json"},
                            json={
                                "dataset_type":     dataset_type,
                                "pipeline_name":    f"{dataset_type}_pipeline",
                                "triggered_by":     "dashboard_upload",
                                "source_file_path": data.get("file_path", ""),
                                "original_filename": uploaded_file.name,
                            },
                            timeout=120,
                        )

                    if pr.status_code == 200:
                        pdata   = pr.json().get("data", {})
                        success = pdata.get("success", False)
                        status  = pdata.get("status", "?")
                        metrics = pdata.get("metrics", {})

                        if success:
                            st.success(f"✅ Pipeline completed successfully!")
                        else:
                            st.warning(f"⚠️ Pipeline finished with status: {status}")

                        p1, p2, p3, p4, p5 = st.columns(5)
                        with p1: st.metric("Status",   status)
                        with p2: st.metric("Records In",  fmt_number(metrics.get("total_records_ingested", 0)))
                        with p3: st.metric("Records Out", fmt_number(metrics.get("total_records_loaded", 0)))
                        with p4: st.metric("Quality",  f"{metrics.get('quality_score') or 0:.1f}%")
                        with p5: st.metric("Duration", f"{pdata.get('duration_seconds',0):.1f}s")

                        stages = pdata.get("stage_results", [])
                        if stages:
                            st.subheader("Stage Results")
                            srows = []
                            for s in stages:
                                icon = "✅" if s.get("status") in ("success","warning") else "❌"
                                srows.append({
                                    "Stage":  f"{icon} {s.get('stage_name','')}",
                                    "Status": s.get("status",""),
                                    "In":     fmt_number(s.get("input_records")),
                                    "Out":    fmt_number(s.get("output_records")),
                                    "Time":   f"{(s.get('duration_ms') or 0)/1000:.2f}s",
                                    "Error":  s.get("error_message") or "—",
                                })
                            st.dataframe(pd.DataFrame(srows),
                                         use_container_width=True, hide_index=True)

                        run_id = pdata.get("pipeline_run_id","")
                        if run_id:
                            st.info(f"View full results in **Pipeline Monitor** → Run ID: {run_id[:8]}…")
                    else:
                        st.error(f"Pipeline error: {pr.text[:200]}")

            elif r.status_code == 409:
                st.warning("⚠️ This file was already ingested (duplicate detected). "
                           "The system prevents loading the same data twice.")
            else:
                err = r.json().get("error", {})
                st.error(f"Upload failed: {err.get('message', r.text[:200])}")

        except Exception as e:
            st.error(f"Connection error: {e}")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# INGESTION HISTORY
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.subheader("Filter History")
    filter_dataset = st.selectbox("Dataset", ["All","orders","customers","products","inventory","suppliers","payments"])
    filter_status  = st.selectbox("Status",  ["All","processed","rejected","duplicate","processing"])
    page_num = st.number_input("Page", min_value=1, value=1, step=1)
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

dataset_param = None if filter_dataset == "All" else filter_dataset
status_param  = None if filter_status  == "All" else filter_status

events_resp = api.list_ingestion_events(
    page=int(page_num), page_size=20,
    dataset_type=dataset_param, status=status_param,
)
events     = extract_list(events_resp)
pagination = extract_pagination(events_resp)

st.subheader(f"Ingestion History ({pagination.get('total_items', 0)} events)")

if events_resp.get("error"):
    st.error(f"API Error: {events_resp['error']}")
elif events:
    from collections import Counter
    import plotly.graph_objects as go

    col_ds, col_st = st.columns(2)
    with col_ds:
        ds_counts = dict(Counter(e.get("dataset_type","unknown") for e in events))
        fig1 = go.Figure(go.Bar(x=list(ds_counts.keys()), y=list(ds_counts.values()),
                                 marker_color="#2563EB", text=list(ds_counts.values()),
                                 textposition="outside"))
        fig1.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                           font=dict(color="#F1F5F9"), height=220, title="By Dataset",
                           margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig1, use_container_width=True)

    with col_st:
        st_counts = dict(Counter(e.get("status","?") for e in events))
        _SC = {"processed":"#22C55E","rejected":"#EF4444","duplicate":"#F59E0B","processing":"#3B82F6"}
        fig2 = go.Figure(go.Pie(labels=list(st_counts.keys()), values=list(st_counts.values()),
                                 marker=dict(colors=[_SC.get(s,"#6B7280") for s in st_counts.keys()]),
                                 hole=0.4))
        fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#F1F5F9"),
                           height=220, title="By Status",
                           margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig2, use_container_width=True)

    rows = [
        {
            "File":        e.get("original_filename", "—"),
            "Dataset":     e.get("dataset_type", "—"),
            "Status":      e.get("status","—"),
            "Rows":        fmt_number(e.get("row_count")),
            "Size":        fmt_bytes(e.get("file_size_bytes")),
            "Format":      e.get("file_extension","—"),
            "Ingested":    fmt_dt(e.get("created_at")),
        }
        for e in events
    ]
    search = st.text_input("🔍 Search")
    df_ev = pd.DataFrame(rows)
    if search:
        sq = search.lower()
        df_ev = df_ev[df_ev.apply(lambda r: sq in r.to_string().lower(), axis=1)]
    st.dataframe(df_ev, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Export CSV", df_to_csv_bytes(df_ev), "ingestion_events.csv", "text/csv")
else:
    st.info("No ingestion events yet. Upload a file above to get started!")
    st.markdown("**Quick start:** Download a sample file from the right panel, then upload it above.")
