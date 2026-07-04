"""
Page 8 — User Administration

Users, roles, permissions, API keys, sessions.
Admin-only page (requires administrator or data_engineer role).
"""
import streamlit as st
import pandas as pd

st.set_page_config(page_title="User Admin", page_icon="👥", layout="wide")

from dashboard.utils.auth import init_session, require_auth, render_sidebar_user, is_admin, is_engineer
from dashboard.utils import api_client as api
from dashboard.utils.formatting import (
    fmt_dt, fmt_dt_relative, status_badge, extract_list, extract_data,
    df_to_csv_bytes,
)

init_session()
require_auth()
render_sidebar_user()

st.title("👥 User Administration")

if not is_engineer():
    st.error("🔒 Administrator or Data Engineer role required to access this page.")
    st.stop()

tabs = st.tabs(["👤 Users", "🎭 Roles & Permissions", "🔑 API Keys"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — Users
# ═══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("User Accounts")

    users_resp = api.list_users(page=1, page_size=100)
    users = extract_list(users_resp)

    if users_resp.get("error"):
        st.error(f"Cannot load users: {users_resp['error']}")
    elif users:
        user_rows = [
            {
                "Username":   u.get("username", "—"),
                "Email":      u.get("email", "—"),
                "Roles":      ", ".join(u.get("roles", [])) or "—",
                "Status":     "🟢 Active" if u.get("is_active") else "🔴 Inactive",
                "Locked":     "🔒 Yes" if u.get("is_locked") else "—",
                "Last Login": fmt_dt_relative(u.get("last_login_at")),
                "ID":         (u.get("id") or "")[:8] + "…",
            }
            for u in users
        ]
        df_users = pd.DataFrame(user_rows)

        search_user = st.text_input("🔍 Search users")
        if search_user:
            sq = search_user.lower()
            df_users = df_users[df_users.apply(lambda row: sq in row.to_string().lower(), axis=1)]

        st.dataframe(df_users, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export CSV", df_to_csv_bytes(df_users), "users.csv", "text/csv")

        # ── User actions ────────────────────────────────────────────────────
        if is_admin():
            st.markdown("---")
            st.subheader("User Actions")
            user_map = {u.get("username", "—"): u.get("id") for u in users}

            act_tabs = st.tabs(["Create User", "Assign Role", "Unlock User", "Delete User"])

            with act_tabs[0]:
                with st.form("create_user"):
                    new_username = st.text_input("Username")
                    new_email    = st.text_input("Email")
                    new_password = st.text_input("Password", type="password")
                    new_roles    = st.multiselect("Roles", ["administrator", "data_engineer", "operator", "analyst", "viewer"])
                    if st.form_submit_button("Create User", use_container_width=True):
                        if new_username and new_email and new_password:
                            r = api.create_user(new_username, new_email, new_password, new_roles)
                            if r.get("error"):
                                st.error(r["error"])
                            elif r.get("success"):
                                st.success(f"User '{new_username}' created.")
                                st.rerun()
                            else:
                                err = (r.get("error") or {})
                                st.error(str(err))
                        else:
                            st.warning("All fields required.")

            with act_tabs[1]:
                with st.form("assign_role"):
                    target_user   = st.selectbox("User", list(user_map.keys()))
                    role_to_assign = st.selectbox("Role", ["administrator", "data_engineer", "operator", "analyst", "viewer"])
                    if st.form_submit_button("Assign Role", use_container_width=True):
                        uid = user_map.get(target_user)
                        if uid:
                            r = api.assign_role(uid, role_to_assign)
                            if r.get("error"):
                                st.error(r["error"])
                            else:
                                st.success(f"Role '{role_to_assign}' assigned to {target_user}.")
                                st.rerun()

            with act_tabs[2]:
                with st.form("unlock_user"):
                    locked_users = [u.get("username") for u in users if u.get("is_locked")]
                    if locked_users:
                        target_locked = st.selectbox("Locked User", locked_users)
                        if st.form_submit_button("Unlock Account", use_container_width=True):
                            uid = user_map.get(target_locked)
                            if uid:
                                r = api.unlock_user(uid)
                                if r.get("error"):
                                    st.error(r["error"])
                                else:
                                    st.success(f"Account '{target_locked}' unlocked.")
                                    st.rerun()
                    else:
                        st.info("No locked accounts.")
                        st.form_submit_button("Unlock", disabled=True)

            with act_tabs[3]:
                with st.form("delete_user"):
                    target_del = st.selectbox("User to Delete", list(user_map.keys()))
                    confirm = st.checkbox("I confirm I want to delete this user.")
                    if st.form_submit_button("Delete User", type="secondary", use_container_width=True):
                        if confirm:
                            uid = user_map.get(target_del)
                            if uid:
                                r = api.delete_user(uid)
                                if r.get("error"):
                                    st.error(r["error"])
                                else:
                                    st.success(f"User '{target_del}' deleted.")
                                    st.rerun()
                        else:
                            st.warning("Please check the confirmation box.")
    else:
        st.info("No users found.")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — Roles & Permissions
# ═══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    col_roles, col_perms = st.columns(2)

    with col_roles:
        st.subheader("Roles")
        roles_resp = api.list_roles()
        roles = extract_list(roles_resp)
        if roles_resp.get("error"):
            st.error(roles_resp["error"])
        elif roles:
            for role in roles:
                with st.expander(f"**{role.get('display_name', role.get('name', '—'))}** — {role.get('name')}"):
                    st.caption(role.get("description", ""))
                    perms = role.get("permissions", [])
                    st.write(f"Permissions ({len(perms)}): {', '.join(perms[:10])}" + ("…" if len(perms) > 10 else ""))
        else:
            st.info("No roles found.")

    with col_perms:
        st.subheader("All Permissions")
        perms_resp = api.list_permissions()
        perms = extract_list(perms_resp)
        if perms_resp.get("error"):
            st.error(perms_resp["error"])
        elif perms:
            perm_rows = [
                {"Permission": p.get("name"), "Resource": p.get("resource"), "Action": p.get("action"), "Description": p.get("description", "")}
                for p in perms
            ]
            st.dataframe(pd.DataFrame(perm_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No permissions found.")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — API Keys
# ═══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("My API Keys")

    keys_resp = api.list_api_keys()
    keys = extract_list(keys_resp)

    if keys_resp.get("error"):
        st.warning(f"Cannot load API keys: {keys_resp['error']}")
    elif keys:
        key_rows = [
            {
                "Name":       k.get("name", "—"),
                "Prefix":     k.get("key_prefix", "—"),
                "Scope":      k.get("scope", "—"),
                "Active":     "✅" if k.get("is_active") else "❌",
                "Requests":   k.get("request_count", 0),
                "Expires":    fmt_dt(k.get("expires_at")) if k.get("expires_at") else "Never",
                "Last Used":  fmt_dt_relative(k.get("last_used_at")),
                "Created":    fmt_dt(k.get("created_at")),
                "ID":         (k.get("id") or "")[:8] + "…",
            }
            for k in keys
        ]
        st.dataframe(pd.DataFrame(key_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No API keys found.")

    st.markdown("---")
    st.subheader("Create API Key")
    with st.form("create_key"):
        key_name  = st.text_input("Key Name", placeholder="e.g. CI/CD Pipeline Key")
        key_scope = st.selectbox("Scope", ["readonly", "pipeline", "admin"])
        key_desc  = st.text_input("Description (optional)")
        if st.form_submit_button("Create Key", use_container_width=True):
            if key_name:
                r = api.create_api_key(key_name, key_scope, key_desc)
                if r.get("error"):
                    st.error(r["error"])
                else:
                    data = extract_data(r) or {}
                    raw_key = data.get("raw_key")
                    if raw_key:
                        st.success("API Key created! Copy it now — it will not be shown again.")
                        st.code(raw_key, language=None)
                    else:
                        st.warning("Key created but raw key not returned.")
                    st.rerun()
            else:
                st.warning("Key name is required.")

    # Revoke / rotate
    if keys:
        st.markdown("---")
        key_map = {k.get("name", "—"): k.get("id") for k in keys if k.get("is_active")}
        if key_map:
            rev_col, rot_col = st.columns(2)
            with rev_col:
                st.subheader("Revoke Key")
                with st.form("revoke_key"):
                    key_to_revoke = st.selectbox("Key", list(key_map.keys()), key="revoke_sel")
                    if st.form_submit_button("Revoke", type="secondary", use_container_width=True):
                        kid = key_map.get(key_to_revoke)
                        if kid:
                            r = api.revoke_api_key(kid)
                            st.success("Key revoked.") if not r.get("error") else st.error(r["error"])
                            st.rerun()
            with rot_col:
                st.subheader("Rotate Key")
                with st.form("rotate_key"):
                    key_to_rotate = st.selectbox("Key", list(key_map.keys()), key="rotate_sel")
                    if st.form_submit_button("Rotate", use_container_width=True):
                        kid = key_map.get(key_to_rotate)
                        if kid:
                            r = api.rotate_api_key(kid)
                            if r.get("error"):
                                st.error(r["error"])
                            else:
                                new_data = (extract_data(r) or {}).get("new_key", {})
                                new_raw = new_data.get("raw_key")
                                st.success("Key rotated! Copy the new key now.")
                                if new_raw:
                                    st.code(new_raw, language=None)
                                st.rerun()
