"""
AuthService — business logic for user authentication.

Handles:
- Login (username/password → access token + refresh token)
- Token refresh (refresh token → new access token)
- Logout (revoke session)
- Change password
- User creation / registration

All DB operations are performed through SQLAlchemy sessions.
Audit events are written to audit_log via _emit_event().
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_token_expiry,
    hash_token,
)
from app.auth.password import hash_password, verify_password, needs_rehash
from app.core.exceptions import AuthenticationException, NotFoundException
from app.database.models.auth.user import User
from app.database.models.auth.user_session import UserSession
from app.logging.logger import get_logger

logger = get_logger(__name__)

# Max consecutive failed logins before account lock
MAX_FAILED_LOGINS = 5


class AuthService:
    """Service layer for authentication operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(
        self,
        username: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """
        Authenticate a user and return JWT tokens.

        Args:
            username:   Username or email.
            password:   Plaintext password.
            ip_address: Client IP for session tracking.
            user_agent: Client user-agent for session tracking.

        Returns:
            Dict with access_token, refresh_token, token_type, expires_in.

        Raises:
            AuthenticationException: Invalid credentials, locked, or inactive account.
        """
        user = self._get_user_by_username_or_email(username)
        self._check_login_allowed(user)

        if not verify_password(password, user.hashed_password):
            self._record_failed_login(user)
            raise AuthenticationException(
                message="Invalid username or password.",
                error_code="INVALID_CREDENTIALS",
            )

        # Successful login — reset fail count
        user.failed_login_count = 0
        user.last_login_at = datetime.now(tz=timezone.utc)

        # Rehash password if needed (transparent upgrade)
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        # Create session + tokens
        access_token = create_access_token(
            user_id=str(user.id),
            username=user.username,
            roles=user.role_names,
            extra_claims={"email": user.email},
        )
        raw_refresh, refresh_hash = create_refresh_token(str(user.id))

        session_record = UserSession(
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            expires_at=get_token_expiry(days=7),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._session.add(session_record)
        self._session.flush()

        self._emit_event("USER_LOGIN", user=user, ip_address=ip_address, extra={
            "session_id": str(session_record.id),
        })

        from app.core.config import get_config
        cfg = get_config()

        return {
            "access_token": access_token,
            "refresh_token": raw_refresh,
            "token_type": "bearer",
            "expires_in": cfg.jwt_expiration_minutes * 60,
            "user_id": str(user.id),
            "username": user.username,
            "roles": user.role_names,
        }

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self, raw_refresh_token: str) -> dict[str, Any]:
        """
        Issue a new access token using a valid refresh token.

        Refresh token rotation: the old session is revoked and a new one created.

        Raises:
            AuthenticationException: If token is invalid, expired, or session revoked.
        """
        payload = decode_refresh_token(raw_refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationException(
                message="Refresh token missing subject claim.",
                error_code="TOKEN_INVALID",
            )

        token_hash = hash_token(raw_refresh_token)
        session_record = self._session.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()

        if session_record is None or not session_record.is_valid():
            raise AuthenticationException(
                message="Refresh token is invalid or has been revoked.",
                error_code="REFRESH_TOKEN_INVALID",
            )

        user = self._session.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        ).scalar_one_or_none()

        if user is None or not user.can_login():
            raise AuthenticationException(
                message="User account is not active.",
                error_code="USER_INACTIVE",
            )

        # Revoke old session (refresh token rotation)
        session_record.is_active = False
        session_record.revoked_at = datetime.now(tz=timezone.utc)

        # Create new tokens + session
        new_access = create_access_token(
            user_id=str(user.id),
            username=user.username,
            roles=user.role_names,
            extra_claims={"email": user.email},
        )
        new_raw_refresh, new_hash = create_refresh_token(str(user.id))

        new_session = UserSession(
            user_id=user.id,
            refresh_token_hash=new_hash,
            expires_at=get_token_expiry(days=7),
            ip_address=session_record.ip_address,
            user_agent=session_record.user_agent,
        )
        self._session.add(new_session)
        self._session.flush()

        from app.core.config import get_config
        cfg = get_config()

        return {
            "access_token": new_access,
            "refresh_token": new_raw_refresh,
            "token_type": "bearer",
            "expires_in": cfg.jwt_expiration_minutes * 60,
        }

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self, raw_refresh_token: str, user_id: str) -> None:
        """
        Revoke the session associated with the given refresh token.

        Args:
            raw_refresh_token: The refresh token to invalidate.
            user_id:           UUID string of the requesting user.
        """
        token_hash = hash_token(raw_refresh_token)
        session_record = self._session.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == token_hash,
                UserSession.user_id == uuid.UUID(user_id),
            )
        ).scalar_one_or_none()

        if session_record:
            session_record.is_active = False
            session_record.revoked_at = datetime.now(tz=timezone.utc)
            self._session.flush()

        user = self._session.get(User, uuid.UUID(user_id))
        self._emit_event("USER_LOGOUT", user=user)
        logger.info("User logged out", user_id=user_id)

    # ------------------------------------------------------------------
    # Change password
    # ------------------------------------------------------------------

    def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        """
        Change a user's password after verifying the current password.

        Raises:
            AuthenticationException: Wrong current password.
        """
        user = self._session.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        ).scalar_one_or_none()

        if user is None:
            raise NotFoundException(message="User not found.")

        if not verify_password(current_password, user.hashed_password):
            raise AuthenticationException(
                message="Current password is incorrect.",
                error_code="INVALID_CURRENT_PASSWORD",
            )

        user.hashed_password = hash_password(new_password)
        user.password_changed_at = datetime.now(tz=timezone.utc)
        self._session.flush()

        logger.info("Password changed", user_id=user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_user_by_username_or_email(self, identifier: str) -> User:
        """Look up a user by username or email. Raises AuthenticationException if not found."""
        user = self._session.execute(
            select(User).where(
                (User.username == identifier) | (User.email == identifier),
                User.is_deleted == False,  # noqa: E712
            )
        ).scalar_one_or_none()

        if user is None:
            raise AuthenticationException(
                message="Invalid username or password.",
                error_code="INVALID_CREDENTIALS",
            )
        return user

    def _check_login_allowed(self, user: User) -> None:
        """Raise AuthenticationException if the user cannot log in."""
        if not user.is_active:
            raise AuthenticationException(
                message="User account is deactivated.",
                error_code="ACCOUNT_INACTIVE",
            )
        if user.is_locked:
            raise AuthenticationException(
                message="Account is locked due to too many failed login attempts.",
                error_code="ACCOUNT_LOCKED",
            )
        if user.is_deleted:
            raise AuthenticationException(
                message="User account does not exist.",
                error_code="INVALID_CREDENTIALS",
            )

    def _record_failed_login(self, user: User) -> None:
        """Increment failed login counter and lock account if threshold reached."""
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.is_locked = True
            user.locked_at = datetime.now(tz=timezone.utc)
            logger.warning(
                "Account locked after too many failed logins",
                user_id=str(user.id),
                username=user.username,
            )
        try:
            self._session.flush()
        except Exception:
            pass

    def _emit_event(
        self,
        event_type: str,
        user: User | None,
        ip_address: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Write a security audit event — non-fatal."""
        try:
            from app.database.models.audit.audit_log import AuditLog

            # Map auth events to supported audit_log event_type values
            # Using API_REQUEST for login/logout as those are the allowed values
            audit_event = "API_REQUEST"

            log = AuditLog(
                event_type=audit_event,
                severity="INFO",
                user_id=str(user.id) if user else None,
                source_ip=ip_address,
                message=f"{event_type}: user={user.username if user else 'unknown'}",
                context_data={
                    "auth_event": event_type,
                    **(extra or {}),
                },
            )
            self._session.add(log)
            self._session.flush()
        except Exception as exc:
            logger.warning(f"Failed to write auth audit event (non-fatal): {exc}")
            try:
                self._session.rollback()
            except Exception:
                pass
