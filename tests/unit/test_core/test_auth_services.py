"""
Tests for Phase 10 auth services:
- password hashing
- JWT handler
- API key manager
- AuthService (login/logout/refresh/change-password)
- UserService (CRUD)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.auth.password import hash_password, verify_password, needs_rehash
from app.auth.jwt_handler import (
    create_access_token, create_refresh_token,
    decode_access_token, decode_refresh_token,
    hash_token, get_token_expiry,
)
from app.auth.rbac import seed_roles_and_permissions
from app.database.models.auth.user import User
from app.database.models.auth.role import Role


# ---------------------------------------------------------------------------
# Helper: seed and create a real user
# ---------------------------------------------------------------------------

def _setup_user(db: Session, username: str = "alice", password: str = "secret123") -> User:
    seed_roles_and_permissions(db)
    from app.auth.user_service import UserService
    svc = UserService(db)
    return svc.create_user(
        username=username,
        email=f"{username}@example.com",
        password=password,
        role_names=["data_engineer"],
    )


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

class TestPassword:

    def test_hash_and_verify(self):
        hashed = hash_password("mysecret")
        assert verify_password("mysecret", hashed) is True

    def test_wrong_password_fails(self):
        hashed = hash_password("mysecret")
        assert verify_password("wrongpassword", hashed) is False

    def test_empty_password_fails_gracefully(self):
        assert verify_password("", "invalid_hash") is False

    def test_needs_rehash_for_valid_hash_is_false(self):
        hashed = hash_password("password123")
        assert needs_rehash(hashed) is False

    def test_needs_rehash_for_invalid_is_false(self):
        # Invalid hash → returns False gracefully, never raises
        assert needs_rehash("not_a_real_hash") is False


# ---------------------------------------------------------------------------
# JWT handler
# ---------------------------------------------------------------------------

class TestJWTHandler:

    def test_create_and_decode_access_token(self):
        uid = str(uuid.uuid4())
        token = create_access_token(uid, "alice", ["data_engineer"])
        payload = decode_access_token(token)
        assert payload["sub"] == uid
        assert payload["username"] == "alice"
        assert "data_engineer" in payload["roles"]
        assert payload["scope"] == "access"

    def test_access_token_has_jti(self):
        token = create_access_token(str(uuid.uuid4()), "bob", [])
        payload = decode_access_token(token)
        assert "jti" in payload

    def test_create_and_decode_refresh_token(self):
        uid = str(uuid.uuid4())
        raw, _hash = create_refresh_token(uid)
        payload = decode_refresh_token(raw)
        assert payload["sub"] == uid
        assert payload["scope"] == "refresh"

    def test_refresh_token_hash_is_sha256(self):
        raw, h = create_refresh_token(str(uuid.uuid4()))
        assert len(h) == 64  # SHA-256 hex = 64 chars

    def test_expired_access_token_raises(self):
        from jose import jwt
        from app.core.config import get_config
        cfg = get_config()
        past = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
        token = jwt.encode(
            {"sub": "u1", "scope": "access", "exp": past},
            cfg.jwt_secret, algorithm=cfg.jwt_algorithm,
        )
        from app.core.exceptions import AuthenticationException
        with pytest.raises(AuthenticationException):
            decode_access_token(token)

    def test_wrong_scope_raises(self):
        uid = str(uuid.uuid4())
        raw, _ = create_refresh_token(uid)
        from app.core.exceptions import AuthenticationException
        with pytest.raises(AuthenticationException):
            decode_access_token(raw)  # refresh token used as access token — wrong scope

    def test_hash_token_is_deterministic(self):
        raw = "etl_abc123"
        assert hash_token(raw) == hash_token(raw)

    def test_get_token_expiry_future(self):
        exp = get_token_expiry(days=7)
        assert exp > datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# API Key Manager
# ---------------------------------------------------------------------------

class TestAPIKeyManager:

    def test_create_and_validate_key(self, db_session: Session):
        user = _setup_user(db_session, "keyalice", "pass1234!")
        from app.auth.api_key_manager import create_api_key, validate_api_key

        key_record, raw = create_api_key(db_session, user.id, name="CI Key", scope="pipeline")
        assert raw.startswith("etl_")
        assert key_record.key_prefix == raw[:12]

        # Validate the key
        validated = validate_api_key(db_session, raw)
        assert str(validated.id) == str(key_record.id)

    def test_invalid_key_raises(self, db_session: Session):
        from app.auth.api_key_manager import validate_api_key
        from app.core.exceptions import AuthenticationException

        with pytest.raises(AuthenticationException):
            validate_api_key(db_session, "etl_nonexistent_key_xxxx")

    def test_bad_format_raises(self, db_session: Session):
        from app.auth.api_key_manager import validate_api_key
        from app.core.exceptions import AuthenticationException

        with pytest.raises(AuthenticationException, match="format"):
            validate_api_key(db_session, "bad_format_key")

    def test_revoke_key(self, db_session: Session):
        user = _setup_user(db_session, "revbob", "pass1234!")
        from app.auth.api_key_manager import create_api_key, revoke_api_key, validate_api_key
        from app.core.exceptions import AuthenticationException

        key_record, raw = create_api_key(db_session, user.id, name="to revoke")
        revoke_api_key(db_session, key_record.id, user.id)

        with pytest.raises(AuthenticationException, match="revoked"):
            validate_api_key(db_session, raw)

    def test_rotate_key(self, db_session: Session):
        user = _setup_user(db_session, "rotcarol", "pass1234!")
        from app.auth.api_key_manager import create_api_key, rotate_api_key, validate_api_key
        from app.core.exceptions import AuthenticationException

        old_record, old_raw = create_api_key(db_session, user.id, name="old key")
        new_record, new_raw = rotate_api_key(db_session, old_record.id, user.id)

        # Old key is revoked
        with pytest.raises(AuthenticationException):
            validate_api_key(db_session, old_raw)

        # New key works
        validated = validate_api_key(db_session, new_raw)
        assert str(validated.id) == str(new_record.id)


# ---------------------------------------------------------------------------
# AuthService
# ---------------------------------------------------------------------------

class TestAuthService:

    def test_login_success(self, db_session: Session):
        _setup_user(db_session, "loginuser", "correctpass")
        from app.auth.auth_service import AuthService
        svc = AuthService(db_session)
        result = svc.login("loginuser", "correctpass")
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["username"] == "loginuser"

    def test_login_wrong_password_raises(self, db_session: Session):
        _setup_user(db_session, "wrongpwuser", "rightpass")
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException, match="Invalid"):
            svc.login("wrongpwuser", "wrongpass")

    def test_login_unknown_user_raises(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException):
            svc.login("ghost_user_xyz", "anypass")

    def test_login_locked_account_raises(self, db_session: Session):
        user = _setup_user(db_session, "lockeduser", "pass1234!")
        user.is_locked = True
        db_session.flush()
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException, match="locked"):
            svc.login("lockeduser", "pass1234!")

    def test_login_inactive_account_raises(self, db_session: Session):
        user = _setup_user(db_session, "inactiveauth", "pass1234!")
        user.is_active = False
        db_session.flush()
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException, match="deactivated"):
            svc.login("inactiveauth", "pass1234!")

    def test_login_by_email(self, db_session: Session):
        _setup_user(db_session, "emailuser", "pass1234!")
        from app.auth.auth_service import AuthService
        svc = AuthService(db_session)
        result = svc.login("emailuser@example.com", "pass1234!")
        assert result["username"] == "emailuser"

    def test_failed_login_increments_counter(self, db_session: Session):
        user = _setup_user(db_session, "failcount", "pass1234!")
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        try:
            svc.login("failcount", "wrongpassword")
        except AuthenticationException:
            pass
        assert user.failed_login_count == 1

    def test_failed_login_locks_after_5(self, db_session: Session):
        user = _setup_user(db_session, "lockme", "pass1234!")
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        for _ in range(5):
            try:
                svc.login("lockme", "wrongpassword")
            except AuthenticationException:
                pass
        assert user.is_locked is True

    def test_refresh_token(self, db_session: Session):
        _setup_user(db_session, "refreshme", "pass1234!")
        from app.auth.auth_service import AuthService
        svc = AuthService(db_session)
        tokens = svc.login("refreshme", "pass1234!")
        new_tokens = svc.refresh(tokens["refresh_token"])
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens

    def test_refresh_rotates_token(self, db_session: Session):
        """Old refresh token should be invalid after rotation."""
        _setup_user(db_session, "rotaterefresh", "pass1234!")
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        tokens = svc.login("rotaterefresh", "pass1234!")
        old_refresh = tokens["refresh_token"]
        svc.refresh(old_refresh)
        # Old refresh token should now be revoked
        with pytest.raises(AuthenticationException):
            svc.refresh(old_refresh)

    def test_logout_revokes_session(self, db_session: Session):
        _setup_user(db_session, "logoutuser", "pass1234!")
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        tokens = svc.login("logoutuser", "pass1234!")
        svc.logout(tokens["refresh_token"], tokens["user_id"])
        # Refresh after logout should fail
        with pytest.raises(AuthenticationException):
            svc.refresh(tokens["refresh_token"])

    def test_change_password_success(self, db_session: Session):
        user = _setup_user(db_session, "changepw", "oldpassword123")
        from app.auth.auth_service import AuthService
        svc = AuthService(db_session)
        svc.change_password(str(user.id), "oldpassword123", "newpassword456")
        # Can now login with new password
        result = svc.login("changepw", "newpassword456")
        assert result["username"] == "changepw"

    def test_change_password_wrong_current_raises(self, db_session: Session):
        user = _setup_user(db_session, "wrongcurrent", "correctpass")
        from app.auth.auth_service import AuthService
        from app.core.exceptions import AuthenticationException
        svc = AuthService(db_session)
        with pytest.raises(AuthenticationException, match="incorrect"):
            svc.change_password(str(user.id), "wrongpass", "newpass123")


# ---------------------------------------------------------------------------
# UserService
# ---------------------------------------------------------------------------

class TestUserService:

    def test_create_and_retrieve_user(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        user = svc.create_user("carol", "carol@example.com", "pass1234!", role_names=["viewer"])
        retrieved = svc.get_user_by_id(user.id)
        assert retrieved.username == "carol"
        assert "viewer" in retrieved.role_names

    def test_duplicate_username_raises(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        from app.core.exceptions import AuthenticationException
        svc = UserService(db_session)
        svc.create_user("dupuser", "dup@example.com", "pass1234!")
        with pytest.raises(AuthenticationException, match="taken"):
            svc.create_user("dupuser", "dup2@example.com", "pass1234!")

    def test_duplicate_email_raises(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        from app.core.exceptions import AuthenticationException
        svc = UserService(db_session)
        svc.create_user("user1email", "same@example.com", "pass1234!")
        with pytest.raises(AuthenticationException, match="registered"):
            svc.create_user("user2email", "same@example.com", "pass1234!")

    def test_list_users_returns_created_users(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        svc.create_user("listuser1", "lu1@example.com", "pass1234!")
        svc.create_user("listuser2", "lu2@example.com", "pass1234!")
        users, total = svc.list_users()
        assert total >= 2

    def test_update_user_full_name(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        user = svc.create_user("updfn", "updfn@example.com", "pass1234!")
        updated = svc.update_user(user.id, full_name="Alice Smith")
        assert updated.full_name == "Alice Smith"

    def test_assign_and_revoke_role(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        user = svc.create_user("roleuser", "roleuser@example.com", "pass1234!")
        user = svc.assign_role(user.id, "analyst")
        assert "analyst" in user.role_names
        user = svc.revoke_role(user.id, "analyst")
        assert "analyst" not in user.role_names

    def test_unlock_user(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        svc = UserService(db_session)
        user = svc.create_user("locktest", "locktest@example.com", "pass1234!")
        user.is_locked = True
        user.failed_login_count = 5
        db_session.flush()
        svc.unlock_user(user.id)
        assert user.is_locked is False
        assert user.failed_login_count == 0

    def test_soft_delete_user(self, db_session: Session):
        seed_roles_and_permissions(db_session)
        from app.auth.user_service import UserService
        from app.core.exceptions import NotFoundException
        svc = UserService(db_session)
        user = svc.create_user("deleteuser", "deleteuser@example.com", "pass1234!")
        user_id = user.id
        svc.delete_user(user_id)
        with pytest.raises(NotFoundException):
            svc.get_user_by_id(user_id)

    def test_get_nonexistent_user_raises(self, db_session: Session):
        from app.auth.user_service import UserService
        from app.core.exceptions import NotFoundException
        svc = UserService(db_session)
        with pytest.raises(NotFoundException):
            svc.get_user_by_id(uuid.uuid4())
