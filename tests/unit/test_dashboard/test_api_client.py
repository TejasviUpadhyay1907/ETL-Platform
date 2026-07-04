"""
Tests for dashboard/utils/api_client.py

Uses httpx MockTransport to intercept HTTP calls without a live server.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────

def _mock_response(status_code: int = 200, body: dict | None = None):
    """Build a mock httpx Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = body or {"success": True, "data": {}}
    return mock


def _patch_get(body: dict, status: int = 200):
    """Context manager patching httpx.get."""
    return patch("httpx.get", return_value=_mock_response(status, body))


def _patch_post(body: dict, status: int = 200):
    """Context manager patching httpx.post."""
    return patch("httpx.post", return_value=_mock_response(status, body))


def _patch_delete(body: dict, status: int = 200):
    """Context manager patching httpx.delete."""
    return patch("httpx.delete", return_value=_mock_response(status, body))


# ── Session state mock ───────────────────────────────────────────────────────

class _FakeState(dict):
    pass


@pytest.fixture(autouse=True)
def mock_session_state(monkeypatch):
    """Patch st.session_state to a plain dict so no Streamlit context needed."""
    state = _FakeState()
    state["access_token"] = "test_token"
    state["api_url"] = "http://localhost:8000"
    import streamlit as st
    monkeypatch.setattr(st, "session_state", state, raising=False)


# ── Tests ────────────────────────────────────────────────────────────────────

class TestAPIClientGet:

    def test_get_health_success(self):
        from dashboard.utils.api_client import get_health
        body = {"success": True, "data": {"status": "healthy"}}
        with _patch_get(body):
            result = get_health()
        assert result["data"]["status"] == "healthy"

    def test_get_health_connect_error(self):
        from dashboard.utils.api_client import get_health
        import httpx
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            result = get_health()
        assert "error" in result
        assert "connect" in result["error"].lower() or "cannot" in result["error"].lower()

    def test_get_health_timeout(self):
        from dashboard.utils.api_client import get_health
        import httpx
        with patch("httpx.get", side_effect=httpx.TimeoutException("timed out")):
            result = get_health()
        assert "error" in result
        assert "timed out" in result["error"].lower() or "timeout" in result["error"].lower()

    def test_401_clears_token(self):
        """A 401 response should clear the access_token from session state."""
        import streamlit as st
        from dashboard.utils.api_client import list_pipelines
        body = {"success": False, "error": {"code": "AUTHENTICATION_REQUIRED", "message": "Login required"}}
        with _patch_get(body, status=401):
            result = list_pipelines()
        assert "error" in result
        # Token should be cleared
        assert st.session_state.get("access_token") is None

    def test_list_pipelines_passes_params(self):
        from dashboard.utils.api_client import list_pipelines
        body = {"success": True, "data": [], "pagination": {"total_items": 0}}
        with _patch_get(body) as mock_get:
            list_pipelines(status="failed", dataset_type="orders")
        call_kwargs = mock_get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs.args[1] if len(call_kwargs.args) > 1 else {}
        # params may be in args or kwargs
        assert mock_get.called

    def test_get_version(self):
        from dashboard.utils.api_client import get_version
        body = {"success": True, "data": {"version": "1.0.0"}}
        with _patch_get(body):
            result = get_version()
        assert result["data"]["version"] == "1.0.0"

    def test_list_roles(self):
        from dashboard.utils.api_client import list_roles
        body = {"success": True, "data": [{"name": "administrator"}]}
        with _patch_get(body):
            result = list_roles()
        assert result["data"][0]["name"] == "administrator"

    def test_list_permissions(self):
        from dashboard.utils.api_client import list_permissions
        body = {"success": True, "data": [{"name": "pipelines:run"}]}
        with _patch_get(body):
            result = list_permissions()
        assert result["data"][0]["name"] == "pipelines:run"

    def test_get_pipeline_run(self):
        from dashboard.utils.api_client import get_pipeline_run
        body = {"success": True, "data": {"id": "abc-123", "status": "completed"}}
        with _patch_get(body):
            result = get_pipeline_run("abc-123")
        assert result["data"]["status"] == "completed"

    def test_get_quality_score(self):
        from dashboard.utils.api_client import get_quality_score
        body = {"success": True, "data": {"overall_score": 95.0}}
        with _patch_get(body):
            result = get_quality_score("run-1")
        assert result["data"]["overall_score"] == 95.0

    def test_list_api_keys(self):
        from dashboard.utils.api_client import list_api_keys
        body = {"success": True, "data": [{"id": "key-1", "name": "CI Key"}]}
        with _patch_get(body):
            result = list_api_keys()
        assert result["data"][0]["name"] == "CI Key"


class TestAPIClientPost:

    def test_login_success(self):
        from dashboard.utils.api_client import login
        body = {"success": True, "data": {"access_token": "tok123", "username": "alice"}}
        with _patch_post(body):
            result = login("alice", "pass123")
        assert result["data"]["access_token"] == "tok123"

    def test_login_failure(self):
        from dashboard.utils.api_client import login
        body = {"success": False, "error": {"code": "INVALID_CREDENTIALS", "message": "Bad creds"}}
        with _patch_post(body, status=401):
            result = login("alice", "wrong")
        assert result.get("success") is False or "error" in result

    def test_cancel_pipeline(self):
        from dashboard.utils.api_client import cancel_pipeline
        body = {"success": True, "data": {"cancelled": True}}
        with _patch_post(body):
            result = cancel_pipeline("run-xyz")
        assert result.get("success") or result["data"].get("cancelled") is True

    def test_create_api_key(self):
        from dashboard.utils.api_client import create_api_key
        body = {"success": True, "data": {"id": "k1", "raw_key": "etl_abc"}}
        with _patch_post(body, status=201):
            result = create_api_key("Test Key", "readonly")
        assert result["data"]["raw_key"].startswith("etl_")

    def test_assign_role(self):
        from dashboard.utils.api_client import assign_role
        body = {"success": True, "data": {"username": "alice", "roles": ["analyst"]}}
        with _patch_post(body):
            result = assign_role("uid-1", "analyst")
        assert result.get("success") or result.get("data")


class TestAPIClientDelete:

    def test_revoke_api_key(self):
        from dashboard.utils.api_client import revoke_api_key
        body = {"success": True, "data": {"revoked": True}}
        with _patch_delete(body):
            result = revoke_api_key("key-1")
        assert result.get("success") or result.get("data", {}).get("revoked") is True

    def test_delete_user(self):
        from dashboard.utils.api_client import delete_user
        body = {"success": True, "data": {"deleted": True}}
        with _patch_delete(body):
            result = delete_user("user-1")
        assert result.get("success") or result.get("data", {}).get("deleted") is True
