import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Configuration", page_icon="⚙️", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user, is_engineer
from dashboard.utils import api_client as api
from dashboard.utils.formatting import extract_list, extract_data

init_session()
require_auth()
render_sidebar_user()

st.title("⚙️ Configuration Viewer")
st.info("🔒 Read-only view. Configuration changes must be made through the API or configuration files.")

tabs = st.tabs(["🚀 Pipeline Definitions", "🏥 System Health", "📦 API Version"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — Pipeline Definitions
# ═══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Registered Pipeline Definitions")
    defs_resp = api.get_pipeline_definitions()
    defs = extract_list(defs_resp)

    if defs_resp.get("error"):
        st.error(f"Cannot load definitions: {defs_resp['error']}")
    elif defs:
        rows = [
            {
                "Name":         d.get("name", "—"),
                "Dataset":      d.get("dataset_type", "—"),
                "Enabled":      "✅" if d.get("enabled") else "❌",
                "Stages":       " → ".join(d.get("stage_order", [])),
                "Max Runtime":  f"{d.get('max_runtime_seconds', 0) // 60} min",
                "Version":      d.get("version", "—"),
                "Description":  d.get("description", "—"),
            }
            for d in defs
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Detailed view
        selected_def = st.selectbox("Select definition for detail", [d.get("name") for d in defs])
        if selected_def:
            defn = next((d for d in defs if d.get("name") == selected_def), None)
            if defn:
                st.subheader(f"Definition: {selected_def}")
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Dataset Type",   defn.get("dataset_type", "—"))
                    st.metric("Version",        defn.get("version", "—"))
                    st.metric("Enabled",        "Yes" if defn.get("enabled") else "No")
                with c2:
                    stages = defn.get("stage_order", [])
                    for i, s in enumerate(stages, 1):
                        st.write(f"Stage {i}: **{s}**")
                with st.expander("Full Definition JSON"):
                    st.json(defn)
    else:
        st.info("No pipeline definitions returned.")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — System Health
# ═══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("System Health")
    health_resp = api.get_health()
    health_data = extract_data(health_resp) or {}

    if health_resp.get("error"):
        st.error(f"Cannot reach API: {health_resp['error']}")
    else:
        from dashboard.utils.formatting import fmt_duration
        status = health_data.get("status", "unknown")
        if status == "healthy":
            st.success(f"✅ **System Status: {status.upper()}**")
        elif status == "degraded":
            st.warning(f"⚠️ **System Status: {status.upper()}**")
        else:
            st.error(f"❌ **System Status: {status.upper()}**")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("App Name",    health_data.get("app_name", "—"))
        with c2:
            st.metric("Version",     health_data.get("version", "—"))
        with c3:
            st.metric("Environment", health_data.get("environment", "—"))
        with c4:
            st.metric("Database",    health_data.get("database", "—"))

        st.metric("Uptime", fmt_duration(health_data.get("uptime_seconds")))
        with st.expander("Full Health Response JSON"):
            st.json(health_data)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — API Version
# ═══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("API Version Info")
    ver_resp = api.get_version()
    ver_data = extract_data(ver_resp) or {}

    if ver_resp.get("error"):
        st.error(f"Cannot reach API: {ver_resp['error']}")
    else:
        st.metric("App Name",    ver_data.get("app_name", "—"))
        st.metric("Version",     ver_data.get("version", "—"))
        st.metric("Environment", ver_data.get("environment", "—"))
        st.markdown("---")
        st.markdown("**API Base URL**")
        st.code(st.session_state.get("api_url", "http://localhost:8000"))
        st.markdown("**OpenAPI Docs**")
        base = st.session_state.get("api_url", "http://localhost:8000")
        st.markdown(f"- [Swagger UI]({base}/docs)")
        st.markdown(f"- [ReDoc]({base}/redoc)")
        st.markdown(f"- [OpenAPI JSON]({base}/openapi.json)")
