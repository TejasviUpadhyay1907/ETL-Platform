"""
Tests for Phase 10 auth DB models: User, Role, Permission, APIKey, UserSession.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.auth.rbac import seed_roles_and_permissions
from app.database.models.auth.user import User
from app.database.models.auth.role import Role
from app.database.models.auth.permission import Permission
from app.database.models.auth.api_key import APIKey
from app.database.models.auth.user_session import UserSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db: Session, username: str = "testuser", email: str = "test@example.com") -> User:
    user = User(
        username=username,
        email=email,
        hashed_password="$2b$12$fakehash",
    )
    db.add(user)
    db.flush()
    return user


def _seed(db: Session) -> None:
    """Seed roles + permissions into the test DB."""
    seed_roles_and_permissions(db)


# ---------------------------------------------------------------------------
# Permission model
# ---------------------------------------------------------------------------

class TestPermissionModel:

    def test_create_permission(self, db_session: Session):
        perm = Permission(
            name="pipelines:run",
            resource="pipelines",
            action="run",
            description="Trigger pipeline runs",
        )
        db_session.add(perm)
        db_session.flush()
        assert perm.id is not None

    def test_repr(self, db_session: Session):
        perm = Permission(name="data:read", resource="data", action="read")
        assert "data:read" in repr(perm)


# ---------------------------------------------------------------------------
# Role model
# ---------------------------------------------------------------------------

class TestRoleModel:

    def test_create_role(self, db_session: Session):
        role = Role(name="test_role", display_name="Test Role")
        db_session.add(role)
        db_session.flush()
        assert role.id is not None

    def test_permission_names_empty_initially(self, db_session: Session):
        role = Role(name="empty_role", display_name="Empty")
        db_session.add(role)
        db_session.flush()
        assert role.permission_names == set()

    def test_has_permission_false_without_assignment(self, db_session: Session):
        role = Role(name="no_perm_role", display_name="NoPerm")
        db_session.add(role)
        db_session.flush()
        assert role.has_permission("pipelines:run") is False

    def test_repr(self, db_session: Session):
        role = Role(name="analyst", display_name="Analyst")
        assert "analyst" in repr(role)


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------

class TestUserModel:

    def test_create_user(self, db_session: Session):
        user = _make_user(db_session)
        assert user.id is not None
        assert user.is_active is True
        assert user.is_locked is False

    def test_can_login_active_user(self, db_session: Session):
        user = _make_user(db_session)
        assert user.can_login() is True

    def test_cannot_login_if_inactive(self, db_session: Session):
        user = _make_user(db_session, "inactive_user", "inactive@example.com")
        user.is_active = False
        assert user.can_login() is False

    def test_cannot_login_if_locked(self, db_session: Session):
        user = _make_user(db_session, "locked_user", "locked@example.com")
        user.is_locked = True
        assert user.can_login() is False

    def test_cannot_login_if_deleted(self, db_session: Session):
        user = _make_user(db_session, "deleted_user", "deleted@example.com")
        user.is_deleted = True
        assert user.can_login() is False

    def test_superuser_has_all_permissions(self, db_session: Session):
        user = _make_user(db_session, "super", "super@example.com")
        user.is_superuser = True
        assert user.has_permission("anything:at:all") is True

    def test_permission_names_empty_no_roles(self, db_session: Session):
        user = _make_user(db_session, "noroles", "noroles@example.com")
        assert user.permission_names == set()

    def test_role_names_empty_initially(self, db_session: Session):
        user = _make_user(db_session, "rolesuser", "rolesuser@example.com")
        assert user.role_names == []

    def test_repr(self, db_session: Session):
        user = _make_user(db_session)
        assert "testuser" in repr(user)


# ---------------------------------------------------------------------------
# APIKey model
# ---------------------------------------------------------------------------

class TestAPIKeyModel:

    def test_create_api_key(self, db_session: Session):
        user = _make_user(db_session)
        key = APIKey(
            user_id=user.id,
            name="test key",
            key_prefix="etl_12345678",
            key_hash="a" * 64,
            scope="readonly",
        )
        db_session.add(key)
        db_session.flush()
        assert key.id is not None

    def test_is_valid_active_key(self, db_session: Session):
        user = _make_user(db_session, "keyuser", "keyuser@example.com")
        key = APIKey(
            user_id=user.id,
            name="valid key",
            key_prefix="etl_12345678",
            key_hash="b" * 64,
            scope="readonly",
            is_active=True,
        )
        db_session.add(key)
        db_session.flush()
        assert key.is_expired() is False

    def test_expired_key(self, db_session: Session):
        user = _make_user(db_session, "expuser", "expuser@example.com")
        past = datetime.now(tz=timezone.utc) - timedelta(days=1)
        key = APIKey(
            user_id=user.id,
            name="expired",
            key_prefix="etl_12345678",
            key_hash="c" * 64,
            scope="readonly",
            expires_at=past,
        )
        db_session.add(key)
        db_session.flush()
        assert key.is_expired() is True
        assert key.is_valid() is False

    def test_revoked_key_is_invalid(self, db_session: Session):
        user = _make_user(db_session, "revuser", "revuser@example.com")
        key = APIKey(
            user_id=user.id,
            name="revoked",
            key_prefix="etl_12345678",
            key_hash="d" * 64,
            scope="readonly",
            is_active=False,
        )
        db_session.add(key)
        db_session.flush()
        assert key.is_valid() is False

    def test_repr(self, db_session: Session):
        user = _make_user(db_session, "repruser", "repr@example.com")
        key = APIKey(
            user_id=user.id,
            name="repr key",
            key_prefix="etl_12345678",
            key_hash="e" * 64,
            scope="pipeline",
        )
        assert "repr key" in repr(key)


# ---------------------------------------------------------------------------
# UserSession model
# ---------------------------------------------------------------------------

class TestUserSessionModel:

    def test_create_session(self, db_session: Session):
        user = _make_user(db_session, "sessuser", "sess@example.com")
        exp = datetime.now(tz=timezone.utc) + timedelta(days=7)
        sess = UserSession(
            user_id=user.id,
            refresh_token_hash="a" * 64,
            expires_at=exp,
        )
        db_session.add(sess)
        db_session.flush()
        assert sess.id is not None

    def test_active_session_is_valid(self, db_session: Session):
        user = _make_user(db_session, "vsessuser", "vsess@example.com")
        exp = datetime.now(tz=timezone.utc) + timedelta(days=7)
        sess = UserSession(
            user_id=user.id,
            refresh_token_hash="b" * 64,
            expires_at=exp,
            is_active=True,
        )
        db_session.add(sess)
        db_session.flush()
        assert sess.is_valid() is True

    def test_expired_session_is_invalid(self, db_session: Session):
        user = _make_user(db_session, "expsessuser", "expsess@example.com")
        past = datetime.now(tz=timezone.utc) - timedelta(days=1)
        sess = UserSession(
            user_id=user.id,
            refresh_token_hash="c" * 64,
            expires_at=past,
            is_active=True,
        )
        db_session.add(sess)
        db_session.flush()
        assert sess.is_valid() is False


# ---------------------------------------------------------------------------
# RBAC seed
# ---------------------------------------------------------------------------

class TestRBACSeeding:

    def test_seed_creates_all_roles(self, db_session: Session):
        _seed(db_session)
        from sqlalchemy import select
        roles = list(db_session.execute(select(Role)).scalars().all())
        role_names = {r.name for r in roles}
        assert "administrator" in role_names
        assert "data_engineer" in role_names
        assert "analyst" in role_names
        assert "viewer" in role_names
        assert "operator" in role_names

    def test_seed_creates_permissions(self, db_session: Session):
        _seed(db_session)
        from sqlalchemy import select
        perms = list(db_session.execute(select(Permission)).scalars().all())
        assert len(perms) >= 10

    def test_seed_is_idempotent(self, db_session: Session):
        _seed(db_session)
        _seed(db_session)  # Second call should not fail or duplicate
        from sqlalchemy import select
        roles = list(db_session.execute(select(Role)).scalars().all())
        role_names = [r.name for r in roles]
        assert role_names.count("administrator") == 1

    def test_admin_role_has_all_permissions(self, db_session: Session):
        _seed(db_session)
        from sqlalchemy import select
        admin_role = db_session.execute(
            select(Role).where(Role.name == "administrator")
        ).scalar_one()
        assert len(admin_role.permissions) >= 10
        assert "admin:all" in admin_role.permission_names

    def test_viewer_role_has_read_only(self, db_session: Session):
        _seed(db_session)
        from sqlalchemy import select
        viewer = db_session.execute(
            select(Role).where(Role.name == "viewer")
        ).scalar_one()
        perm_names = viewer.permission_names
        assert "pipelines:read" in perm_names
        assert "pipelines:run" not in perm_names
