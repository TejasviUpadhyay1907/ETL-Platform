"""
ETL Platform API client for the Streamlit dashboard.

All dashboard pages consume data exclusively through this client.
Never import app.* modules — the dashboard is a pure API consumer.

Design:
- Single APIClient class wrapping httpx (synchronous)
- All methods return plain dicts/lists — no domain models
- JWT token stored in st.session_state, injected per request
- Graceful error handling: returns {"error": "..."} on failure
- Configurable base URL via environment variable DASHBOARD_API_URL
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_API_URL = os.getenv("DASHBOARD_API_URL", "http://localhost:8001")
REQUEST_TIMEOUT = int(os.getenv("DASHBOARD_API_TIMEOUT", "15"))


def _get_base_url() -> str:
    return st.session_state.get("api_url", DEFAULT_API_URL).rstrip("/")


def _get_headers() -> dict[str, str]:
    """Build auth headers from session state."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = st.session_state.get("access_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _safe_get(url: str, params: dict | None = None) -> dict[str, Any]:
    """Perform a GET request and return the parsed JSON body."""
    try:
        resp = httpx.get(
            url,
            headers=_get_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 401:
            st.session_state["access_token"] = None
            return {"error": "Session expired. Please log in again.", "status_code": 401}
        return resp.json()
    except httpx.ConnectError:
        return {"error": f"Cannot connect to API at {_get_base_url()}. Is the server running?"}
    except httpx.TimeoutException:
        return {"error": "Request timed out. The API server may be busy."}
    except Exception as exc:
        return {"error": str(exc)}


def _safe_post(url: str, json: dict | None = None) -> dict[str, Any]:
    """Perform a POST request and return the parsed JSON body."""
    try:
        resp = httpx.post(
            url,
            headers=_get_headers(),
            json=json or {},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 401:
            st.session_state["access_token"] = None
            return {"error": "Session expired. Please log in again.", "status_code": 401}
        return resp.json()
    except httpx.ConnectError:
        return {"error": f"Cannot connect to API at {_get_base_url()}. Is the server running?"}
    except httpx.TimeoutException:
        return {"error": "Request timed out."}
    except Exception as exc:
        return {"error": str(exc)}


def _safe_delete(url: str) -> dict[str, Any]:
    """Perform a DELETE request and return the parsed JSON body."""
    try:
        resp = httpx.delete(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(username: str, password: str) -> dict[str, Any]:
    """POST /api/v1/auth/login"""
    url = f"{_get_base_url()}/api/v1/auth/login"
    try:
        resp = httpx.post(url, json={"username": username, "password": password}, timeout=REQUEST_TIMEOUT)
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


def get_current_user() -> dict[str, Any]:
    """GET /api/v1/auth/me"""
    return _safe_get(f"{_get_base_url()}/api/v1/auth/me")


def logout(refresh_token: str) -> dict[str, Any]:
    """POST /api/v1/auth/logout"""
    return _safe_post(f"{_get_base_url()}/api/v1/auth/logout", {"refresh_token": refresh_token})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def get_health() -> dict[str, Any]:
    """GET /api/v1/health"""
    return _safe_get(f"{_get_base_url()}/api/v1/health")


def get_version() -> dict[str, Any]:
    """GET /api/v1/health/version"""
    return _safe_get(f"{_get_base_url()}/api/v1/health/version")


# ---------------------------------------------------------------------------
# Pipelines
# ---------------------------------------------------------------------------

def list_pipelines(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    dataset_type: str | None = None,
    pipeline_name: str | None = None,
) -> dict[str, Any]:
    """GET /api/v1/pipelines"""
    params: dict = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    if dataset_type:
        params["dataset_type"] = dataset_type
    if pipeline_name:
        params["pipeline_name"] = pipeline_name
    return _safe_get(f"{_get_base_url()}/api/v1/pipelines", params=params)


def get_pipeline_run(run_id: str) -> dict[str, Any]:
    """GET /api/v1/pipelines/{run_id}"""
    return _safe_get(f"{_get_base_url()}/api/v1/pipelines/{run_id}")


def get_pipeline_metrics(run_id: str) -> dict[str, Any]:
    """GET /api/v1/pipelines/{run_id}/metrics"""
    return _safe_get(f"{_get_base_url()}/api/v1/pipelines/{run_id}/metrics")


def get_pipeline_events(run_id: str, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """GET /api/v1/pipelines/{run_id}/events"""
    return _safe_get(
        f"{_get_base_url()}/api/v1/pipelines/{run_id}/events",
        params={"page": page, "page_size": page_size},
    )


def get_pipeline_checkpoints(run_id: str) -> dict[str, Any]:
    """GET /api/v1/pipelines/{run_id}/checkpoints"""
    return _safe_get(f"{_get_base_url()}/api/v1/pipelines/{run_id}/checkpoints")


def get_pipeline_history(
    page: int = 1,
    page_size: int = 20,
    dataset_type: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """GET /api/v1/pipelines/history"""
    params: dict = {"page": page, "page_size": page_size}
    if dataset_type:
        params["dataset_type"] = dataset_type
    if status:
        params["status"] = status
    return _safe_get(f"{_get_base_url()}/api/v1/pipelines/history", params=params)


def get_pipeline_definitions() -> dict[str, Any]:
    """GET /api/v1/pipelines/definitions"""
    return _safe_get(f"{_get_base_url()}/api/v1/pipelines/definitions")


def cancel_pipeline(run_id: str) -> dict[str, Any]:
    """POST /api/v1/pipelines/{run_id}/cancel"""
    return _safe_post(f"{_get_base_url()}/api/v1/pipelines/{run_id}/cancel")


def retry_pipeline(run_id: str) -> dict[str, Any]:
    """POST /api/v1/pipelines/{run_id}/retry"""
    return _safe_post(f"{_get_base_url()}/api/v1/pipelines/{run_id}/retry")


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

def get_quality_score(run_id: str) -> dict[str, Any]:
    """GET /api/v1/quality/score/{run_id}"""
    return _safe_get(f"{_get_base_url()}/api/v1/quality/score/{run_id}")


def get_quality_report(run_id: str, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    """GET /api/v1/quality/report/{run_id}"""
    return _safe_get(
        f"{_get_base_url()}/api/v1/quality/report/{run_id}",
        params={"page": page, "page_size": page_size},
    )


def get_quality_summary(run_id: str) -> dict[str, Any]:
    """GET /api/v1/quality/summary/{run_id}"""
    return _safe_get(f"{_get_base_url()}/api/v1/quality/summary/{run_id}")


# ---------------------------------------------------------------------------
# Load / Warehouse
# ---------------------------------------------------------------------------

def get_load_history(page: int = 1, page_size: int = 20, dataset_type: str | None = None) -> dict[str, Any]:
    """GET /api/v1/load/history"""
    params: dict = {"page": page, "page_size": page_size}
    if dataset_type:
        params["dataset_type"] = dataset_type
    return _safe_get(f"{_get_base_url()}/api/v1/load/history", params=params)


def get_load_report(run_id: str) -> dict[str, Any]:
    """GET /api/v1/load/report/{run_id}"""
    return _safe_get(f"{_get_base_url()}/api/v1/load/report/{run_id}")


def get_load_summary(run_id: str) -> dict[str, Any]:
    """GET /api/v1/load/summary/{run_id}"""
    return _safe_get(f"{_get_base_url()}/api/v1/load/summary/{run_id}")


def get_load_metrics(run_id: str) -> dict[str, Any]:
    """GET /api/v1/load/metrics/{run_id}"""
    return _safe_get(f"{_get_base_url()}/api/v1/load/metrics/{run_id}")


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def list_ingestion_events(
    page: int = 1,
    page_size: int = 20,
    dataset_type: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """GET /api/v1/ingest/events"""
    params: dict = {"page": page, "page_size": page_size}
    if dataset_type:
        params["dataset_type"] = dataset_type
    if status:
        params["status"] = status
    return _safe_get(f"{_get_base_url()}/api/v1/ingest/events", params=params)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def list_users(page: int = 1, page_size: int = 20) -> dict[str, Any]:
    """GET /api/v1/users"""
    return _safe_get(f"{_get_base_url()}/api/v1/users", params={"page": page, "page_size": page_size})


def get_user(user_id: str) -> dict[str, Any]:
    """GET /api/v1/users/{user_id}"""
    return _safe_get(f"{_get_base_url()}/api/v1/users/{user_id}")


def create_user(username: str, email: str, password: str, roles: list[str]) -> dict[str, Any]:
    """POST /api/v1/users"""
    return _safe_post(
        f"{_get_base_url()}/api/v1/users",
        {"username": username, "email": email, "password": password, "role_names": roles},
    )


def delete_user(user_id: str) -> dict[str, Any]:
    """DELETE /api/v1/users/{user_id}"""
    return _safe_delete(f"{_get_base_url()}/api/v1/users/{user_id}")


def assign_role(user_id: str, role_name: str) -> dict[str, Any]:
    """POST /api/v1/users/{user_id}/roles"""
    return _safe_post(f"{_get_base_url()}/api/v1/users/{user_id}/roles", {"role_name": role_name})


def unlock_user(user_id: str) -> dict[str, Any]:
    """POST /api/v1/users/{user_id}/unlock"""
    return _safe_post(f"{_get_base_url()}/api/v1/users/{user_id}/unlock")


def list_roles() -> dict[str, Any]:
    """GET /api/v1/roles"""
    return _safe_get(f"{_get_base_url()}/api/v1/roles")


def list_permissions() -> dict[str, Any]:
    """GET /api/v1/permissions"""
    return _safe_get(f"{_get_base_url()}/api/v1/permissions")


def list_api_keys() -> dict[str, Any]:
    """GET /api/v1/api-keys"""
    return _safe_get(f"{_get_base_url()}/api/v1/api-keys")


def create_api_key(name: str, scope: str, description: str = "") -> dict[str, Any]:
    """POST /api/v1/api-keys"""
    return _safe_post(
        f"{_get_base_url()}/api/v1/api-keys",
        {"name": name, "scope": scope, "description": description},
    )


def revoke_api_key(key_id: str) -> dict[str, Any]:
    """DELETE /api/v1/api-keys/{key_id}"""
    return _safe_delete(f"{_get_base_url()}/api/v1/api-keys/{key_id}")


def rotate_api_key(key_id: str) -> dict[str, Any]:
    """POST /api/v1/api-keys/{key_id}/rotate"""
    return _safe_post(f"{_get_base_url()}/api/v1/api-keys/{key_id}/rotate")
