"""
Tests for dashboard/utils/auth.py

Patches st.session_state with a plain dict and verifies auth logic.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class _FakeState(dict):
    pass


@pytest.fixture
def session_state(monkeypatch):
    """Fresh session state for each test."""
    state = _FakeState()
    import streamlit as st
    monkeypatch.setattr(st, "session_state", state, raising=False)
    return state


class TestIsAuthenticated:

    def test_not_authenticated_by_default(self, session_state):
        from dashboard.utils.auth import is_authenticated
        assert is_authenticated() is False

    def test_authenticated_with_token(self, session_state):
        session_state["access_token"] = "sometoken"
        from dashboard.utils.auth import is_authenticated
        assert is_authenticated() is True

    def test_empty_token_not_authenticated(self, session_state):
        session_state["access_token"] = ""
        from dashboard.utils.auth import is_authenticated
        assert is_authenticated() is False


class TestGetRoles:

    def test_empty_roles_by_default(self, session_state):
        from dashboard.utils.auth import get_roles
        assert get_roles() == []

    def test_roles_returned_correctly(self, session_state):
        session_state["roles"] = ["administrator", "data_engineer"]
        from dashboard.utils.auth import get_roles
        assert "administrator" in get_roles()


class TestHasRole:

    def test_has_matching_role(self, session_state):
        session_state["roles"] = ["data_engineer"]
        from dashboard.utils.auth import has_role
        assert has_role("data_engineer") is True

    def test_does_not_have_role(self, session_state):
        session_state["roles"] = ["viewer"]
        from dashboard.utils.auth import has_role
        assert has_role("administrator") is False

    def test_has_one_of_multiple(self, session_state):
        session_state["roles"] = ["analyst"]
        from dashboard.utils.auth import has_role
        assert has_role("administrator", "analyst") is True

    def test_empty_roles(self, session_state):
        session_state["roles"] = []
        from dashboard.utils.auth import has_role
        assert has_role("viewer") is False


class TestIsAdmin:

    def test_admin_role(self, session_state):
        session_state["roles"] = ["administrator"]
        from dashboard.utils.auth import is_admin
        assert is_admin() is True

    def test_non_admin(self, session_state):
        session_state["roles"] = ["viewer"]
        from dashboard.utils.auth import is_admin
        assert is_admin() is False


class TestIsEngineer:

    def test_data_engineer(self, session_state):
        session_state["roles"] = ["data_engineer"]
        from dashboard.utils.auth import is_engineer
        assert is_engineer() is True

    def test_administrator(self, session_state):
        session_state["roles"] = ["administrator"]
        from dashboard.utils.auth import is_engineer
        assert is_engineer() is True

    def test_viewer(self, session_state):
        session_state["roles"] = ["viewer"]
        from dashboard.utils.auth import is_engineer
        assert is_engineer() is False


class TestInitSession:

    def test_initializes_keys(self, session_state):
        from dashboard.utils.auth import init_session
        init_session()
        assert "access_token" in session_state
        assert "roles" in session_state
        assert "logged_in" in session_state

    def test_does_not_overwrite_existing(self, session_state):
        session_state["access_token"] = "existing_token"
        from dashboard.utils.auth import init_session
        init_session()
        # Should not have been reset
        assert session_state["access_token"] == "existing_token"
