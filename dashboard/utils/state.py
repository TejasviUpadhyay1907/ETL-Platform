"""
Shared session state helpers for auto-refresh and filter persistence.
"""
from __future__ import annotations

import time
import streamlit as st


def auto_refresh_sidebar(default_interval: int = 30) -> bool:
    """
    Render an auto-refresh control in the sidebar.

    Returns True if a refresh was triggered this cycle.
    """
    with st.sidebar:
        st.markdown("---")
        st.subheader("⚙️ Refresh")
        enabled  = st.checkbox("Auto Refresh", value=False, key="_auto_refresh")
        interval = st.selectbox("Interval (s)", [10, 30, 60, 120], index=1, key="_refresh_interval") if enabled else default_interval

        if st.button("🔄 Refresh Now", use_container_width=True, key="_manual_refresh"):
            st.rerun()

        if enabled:
            last = st.session_state.get("_last_refresh", 0)
            if time.time() - last >= interval:
                st.session_state["_last_refresh"] = time.time()
                st.rerun()
    return False


def get_filter(key: str, default=None):
    """Retrieve a persisted filter value from session state."""
    return st.session_state.get(f"_filter_{key}", default)


def set_filter(key: str, value) -> None:
    """Persist a filter value into session state."""
    st.session_state[f"_filter_{key}"] = value
