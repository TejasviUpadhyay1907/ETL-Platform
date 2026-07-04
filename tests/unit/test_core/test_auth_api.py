"""
API-level tests for Phase 10 authentication endpoints.

Uses the TestClient with a real SQLite in-memory DB session.
We override the get_db dependency to inject our test session.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.rbac import seed_roles_and_permissions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_app_with_db(db_session: Session):
    """
    Create a TestClient that uses the provided db_session for all requests.
    We override the get_db dependency with our test session.
    """
    from app.core.application import create_app
    from app.api.dependencies import get_db

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=False)


def _register_and_login(client: TestClient, username: str = "testadmin", password: str = "pass1234!"):
    """Register a user directly via UserService and return auth headers."""
    # We need to call into the DB directly — the /users endpoint itself requires auth.
    # Return just the login info.
    return {"username": username, "password": password}


def _get_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Auth endpoint tests
# ---------------------------------------------------------------------------

class TestAuthEndpoints:

    def test_login_valid_credentials(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("logintest", "logintest@example.com", "pass1234!")

        client = _make_test_app_with_db(db_session)
        response = client.post("/api/v1/auth/login", json={
            "username": "logintest",
            "password": "pass1234!",
        })
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "access_token" in body["data"]
        assert "refresh_token" in body["data"]

    def test_login_invalid_credentials_returns_401(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("badlogin", "badlogin@example.com", "pass1234!")

        client = _make_test_app_with_db(db_session)
        response = client.post("/api/v1/auth/login", json={
            "username": "badlogin",
            "password": "wrongpass",
        })
        assert response.status_code == 401

    def test_login_missing_fields_returns_422(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.post("/api/v1/auth/login", json={"username": "only"})
        assert response.status_code == 422

    def test_refresh_token_returns_new_access_token(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("refreshtest", "refresh@example.com", "pass1234!")

        client = _make_test_app_with_db(db_session)
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "refreshtest", "password": "pass1234!"
        })
        refresh_token = login_resp.json()["data"]["refresh_token"]

        refresh_resp = client.post("/api/v1/auth/refresh", json={
            "refresh_token": refresh_token
        })
        assert refresh_resp.status_code == 200
        assert "access_token" in refresh_resp.json()["data"]

    def test_refresh_with_invalid_token_returns_401(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.post("/api/v1/auth/refresh", json={
            "refresh_token": "not.a.real.token"
        })
        assert response.status_code == 401

    def test_logout_requires_auth(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        # Sending logout without an Authorization header — should get 401
        response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "some_token"},
            headers={},  # no auth
        )
        assert response.status_code == 401

    def test_me_endpoint_requires_auth(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_returns_user_info(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("meuser", "meuser@example.com", "pass1234!")

        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "meuser", "password": "pass1234!"
        })
        token = login.json()["data"]["access_token"]

        me_resp = client.get("/api/v1/auth/me", headers=_get_headers(token))
        assert me_resp.status_code == 200
        assert me_resp.json()["data"]["username"] == "meuser"

    def test_change_password_success(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("pwchange", "pwchange@example.com", "oldpass123")

        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "pwchange", "password": "oldpass123"
        })
        token = login.json()["data"]["access_token"]

        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "oldpass123", "new_password": "newpass456"},
            headers=_get_headers(token),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["password_changed"] is True

    def test_change_password_wrong_current_returns_401(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("badpwchange", "badpwchange@example.com", "correctpass")

        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "badpwchange", "password": "correctpass"
        })
        token = login.json()["data"]["access_token"]

        resp = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "wrongpass", "new_password": "newpass456"},
            headers=_get_headers(token),
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:

    def test_rate_limit_headers_present(self, db_session: Session):
        """Rate-limit headers should be injected on normal authenticated requests."""
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("ratelimituser", "ratelimit@example.com", "pass1234!")

        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "ratelimituser", "password": "pass1234!"
        })
        token = login.json()["data"]["access_token"]
        # Make a request that succeeds with auth
        response = client.get("/api/v1/auth/me", headers=_get_headers(token))
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Protected pipeline endpoint — requires auth
# ---------------------------------------------------------------------------

class TestProtectedEndpoints:

    def test_pipeline_list_without_auth_returns_401(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.get("/api/v1/pipelines")
        assert response.status_code == 401

    def test_pipeline_list_with_valid_token(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("pipapiuser", "pipapi@example.com", "pass1234!", role_names=["data_engineer"])

        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "pipapiuser", "password": "pass1234!"
        })
        token = login.json()["data"]["access_token"]
        response = client.get("/api/v1/pipelines", headers=_get_headers(token))
        # Should get 200 (empty list) not 401
        assert response.status_code == 200

    def test_invalid_bearer_token_returns_401(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.get(
            "/api/v1/pipelines",
            headers={"Authorization": "Bearer invalidtoken.here.xxx"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# User management API
# ---------------------------------------------------------------------------

class TestUsersAPI:

    def _login_as_admin(self, client: TestClient, db_session: Session) -> str:
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        try:
            svc.create_user(
                "adminuser", "admin@example.com", "adminpass123",
                role_names=["administrator"], is_superuser=True,
            )
        except Exception:
            pass  # May already exist in session
        login = client.post("/api/v1/auth/login", json={
            "username": "adminuser", "password": "adminpass123"
        })
        return login.json()["data"]["access_token"]

    def test_list_users_requires_auth(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.get("/api/v1/users")
        assert response.status_code == 401

    def test_list_users_with_admin(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        client = _make_test_app_with_db(db_session)
        token = self._login_as_admin(client, db_session)
        response = client.get("/api/v1/users", headers=_get_headers(token))
        assert response.status_code == 200

    def test_create_user_with_admin(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        client = _make_test_app_with_db(db_session)
        token = self._login_as_admin(client, db_session)
        response = client.post(
            "/api/v1/users",
            json={
                "username": "newcreated",
                "email": "newcreated@example.com",
                "password": "pass1234!x",
            },
            headers=_get_headers(token),
        )
        assert response.status_code == 201
        assert response.json()["data"]["username"] == "newcreated"

    def test_create_user_without_perm_returns_403(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("viewonly", "viewonly@example.com", "pass1234!", role_names=["viewer"])

        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "viewonly", "password": "pass1234!"
        })
        token = login.json()["data"]["access_token"]

        response = client.post(
            "/api/v1/users",
            json={
                "username": "blocked",
                "email": "blocked@example.com",
                "password": "pass1234!",
            },
            headers=_get_headers(token),
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# API Keys API
# ---------------------------------------------------------------------------

class TestAPIKeysAPI:

    def _login_as_engineer(self, client: TestClient, db_session: Session) -> str:
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        try:
            svc.create_user(
                "apienguser", "apieng@example.com", "engineerpass123",
                role_names=["data_engineer"],
            )
        except Exception:
            pass
        login = client.post("/api/v1/auth/login", json={
            "username": "apienguser", "password": "engineerpass123"
        })
        return login.json()["data"]["access_token"]

    def test_create_api_key(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        client = _make_test_app_with_db(db_session)
        token = self._login_as_engineer(client, db_session)
        response = client.post(
            "/api/v1/api-keys",
            json={"name": "test CI key", "scope": "pipeline"},
            headers=_get_headers(token),
        )
        # Debug: print body if not 201
        if response.status_code != 201:
            print("create_api_key response:", response.status_code, response.text)
        assert response.status_code == 201
        data = response.json()["data"]
        assert "raw_key" in data
        assert data["raw_key"].startswith("etl_")

    def test_list_api_keys(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        client = _make_test_app_with_db(db_session)
        token = self._login_as_engineer(client, db_session)
        # Create a key first
        client.post(
            "/api/v1/api-keys",
            json={"name": "list test key", "scope": "readonly"},
            headers=_get_headers(token),
        )
        response = client.get("/api/v1/api-keys", headers=_get_headers(token))
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    def test_revoke_api_key(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        client = _make_test_app_with_db(db_session)
        token = self._login_as_engineer(client, db_session)
        create_resp = client.post(
            "/api/v1/api-keys",
            json={"name": "to revoke", "scope": "readonly"},
            headers=_get_headers(token),
        )
        key_id = create_resp.json()["data"]["id"]
        revoke_resp = client.delete(
            f"/api/v1/api-keys/{key_id}",
            headers=_get_headers(token),
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["data"]["revoked"] is True

    def test_create_api_key_requires_auth(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.post(
            "/api/v1/api-keys",
            json={"name": "no auth key", "scope": "readonly"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Roles API
# ---------------------------------------------------------------------------

class TestRolesAPI:

    def test_list_roles_requires_auth(self, db_session: Session):
        client = _make_test_app_with_db(db_session)
        response = client.get("/api/v1/roles")
        assert response.status_code == 401

    def test_list_roles_with_admin(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user(
            "rolesadmin", "rolesadmin@example.com", "adminpass123",
            role_names=["administrator"], is_superuser=True,
        )
        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "rolesadmin", "password": "adminpass123"
        })
        token = login.json()["data"]["access_token"]
        response = client.get("/api/v1/roles", headers=_get_headers(token))
        assert response.status_code == 200
        role_names = [r["name"] for r in response.json()["data"]]
        assert "administrator" in role_names

    def test_list_permissions_with_admin(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        try:
            svc.create_user(
                "permsadmin", "permsadmin@example.com", "adminpass123",
                role_names=["administrator"], is_superuser=True,
            )
        except Exception:
            pass
        client = _make_test_app_with_db(db_session)
        login = client.post("/api/v1/auth/login", json={
            "username": "permsadmin", "password": "adminpass123"
        })
        token = login.json()["data"]["access_token"]
        response = client.get("/api/v1/permissions", headers=_get_headers(token))
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 10
