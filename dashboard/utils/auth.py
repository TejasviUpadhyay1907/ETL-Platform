"""
Dashboard authentication helpers.

Manages JWT tokens in st.session_state.
Provides login gate, role checks, and session persistence.
"""
from __future__ import annotations

import streamlit as st
from dashboard.utils import api_client as api


# ---------------------------------------------------------------------------
# Session state keys
# ---------------------------------------------------------------------------

_KEYS = {
    "access_token": None,
    "refresh_token": None,
    "username": None,
    "roles": [],
    "user_id": None,
    "logged_in": False,
}


def init_session() -> None:
    """Initialise session state keys if they don't exist."""
    for key, default in _KEYS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def is_authenticated() -> bool:
    """Return True if the user has a valid access token in session."""
    return bool(st.session_state.get("access_token"))


def get_roles() -> list[str]:
    """Return the current user's role list."""
    return st.session_state.get("roles", [])


def has_role(*role_names: str) -> bool:
    """Return True if user holds at least one of the given roles."""
    user_roles = set(get_roles())
    return bool(user_roles.intersection(role_names))


def is_admin() -> bool:
    return has_role("administrator")


def is_engineer() -> bool:
    return has_role("administrator", "data_engineer")


def require_auth() -> None:
    """
    Call at the top of every protected page.
    Redirects to login if not authenticated.
    """
    init_session()
    if not is_authenticated():
        st.warning("🔒 Please log in to access this page.")
        _render_login_form()
        st.stop()


def _render_login_form() -> None:
    """Render the login form inline (used when page requires auth)."""
    st.markdown("---")
    st.subheader("Login to ETL Platform")

    with st.form("login_form"):
        username = st.text_input("Username or Email")
        password = st.text_input("Password", type="password")
        api_url = st.text_input(
            "API URL",
            value=st.session_state.get("api_url", "http://localhost:8000"),
        )
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
            return

        st.session_state["api_url"] = api_url
        with st.spinner("Authenticating…"):
            result = api.login(username, password)

        if result.get("error"):
            st.error(f"Login failed: {result['error']}")
            return

        data = result.get("data", {})
        if not data or not data.get("access_token"):
            # Check if success is False
            err = result.get("error") or result.get("detail", "Invalid credentials")
            st.error(f"Login failed: {err}")
            return

        st.session_state["access_token"] = data["access_token"]
        st.session_state["refresh_token"] = data.get("refresh_token")
        st.session_state["username"] = data.get("username", username)
        st.session_state["roles"] = data.get("roles", [])
        st.session_state["user_id"] = data.get("user_id")
        st.session_state["logged_in"] = True
        st.success(f"Welcome, {st.session_state['username']}!")
        st.rerun()


def render_sidebar_user() -> None:
    """Render user info and logout button in the sidebar."""
    if not is_authenticated():
        return

    username = st.session_state.get("username", "User")
    roles = get_roles()
    role_str = ", ".join(roles) if roles else "—"

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**👤 {username}**")
    st.sidebar.caption(f"Roles: {role_str}")

    if st.sidebar.button("Logout", use_container_width=True):
        refresh_token = st.session_state.get("refresh_token", "")
        if refresh_token:
            api.logout(refresh_token)
        for key in _KEYS:
            st.session_state[key] = _KEYS[key]
        st.rerun()
