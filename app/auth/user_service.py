"""
UserService — CRUD operations for User accounts.

Separated from AuthService to follow Single Responsibility:
- AuthService: authentication (login/logout/tokens)
- UserService: user lifecycle (create/update/delete/assign roles)
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.password import hash_password
from app.auth.rbac import BUILT_IN_ROLES
from app.core.exceptions import (
    AuthenticationException,
    NotFoundException,
)
from app.database.models.auth.role import Role
from app.database.models.auth.user import User
from app.logging.logger import get_logger

logger = get_logger(__name__)


class UserService:
    """Service layer for user management operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str | None = None,
        role_names: list[str] | None = None,
        is_superuser: bool = False,
    ) -> User:
        """
        Create a new user account.

        Args:
            username:    Unique username.
            email:       Unique email address.
            password:    Plaintext password (hashed before storage).
            full_name:   Optional display name.
            role_names:  Roles to assign (e.g. ['data_engineer']).
            is_superuser: Grant superuser flag (bypasses permission checks).

        Returns:
            Newly created User ORM instance.

        Raises:
            AuthenticationException: Username or email already exists.
        """
        # Check uniqueness
        if self._username_exists(username):
            raise AuthenticationException(
                message=f"Username '{username}' is already taken.",
                error_code="USERNAME_TAKEN",
            )
        if self._email_exists(email):
            raise AuthenticationException(
                message=f"Email '{email}' is already registered.",
                error_code="EMAIL_TAKEN",
            )

        user = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_superuser=is_superuser,
        )

        # Assign roles
        if role_names:
            for role_name in role_names:
                role = self._get_role(role_name)
                if role:
                    user.roles.append(role)

        self._session.add(user)
        self._session.flush()

        logger.info("User created", user_id=str(user.id), username=username)
        return user

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_user_by_id(self, user_id: uuid.UUID) -> User:
        """
        Retrieve a user by UUID.

        Raises:
            NotFoundException: User not found.
        """
        user = self._session.execute(
            select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
        ).scalar_one_or_none()

        if user is None:
            raise NotFoundException(message=f"User {user_id} not found.")
        return user

    def get_user_by_username(self, username: str) -> User | None:
        """Return user by username, or None if not found."""
        return self._session.execute(
            select(User).where(
                User.username == username,
                User.is_deleted == False,  # noqa: E712
            )
        ).scalar_one_or_none()

    def list_users(
        self,
        offset: int = 0,
        limit: int = 20,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        """
        Return paginated users.

        Returns:
            Tuple of (user_list, total_count).
        """
        stmt = select(User).where(User.is_deleted == False)  # noqa: E712
        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
        stmt = stmt.order_by(User.username)

        all_users = list(self._session.execute(stmt).scalars().all())
        total = len(all_users)
        paged = all_users[offset: offset + limit]
        return paged, total

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_user(
        self,
        user_id: uuid.UUID,
        full_name: str | None = None,
        email: str | None = None,
        is_active: bool | None = None,
    ) -> User:
        """Update user profile fields."""
        user = self.get_user_by_id(user_id)

        if full_name is not None:
            user.full_name = full_name
        if email is not None:
            if self._email_exists(email) and user.email != email:
                raise AuthenticationException(
                    message=f"Email '{email}' is already registered.",
                    error_code="EMAIL_TAKEN",
                )
            user.email = email
        if is_active is not None:
            user.is_active = is_active

        self._session.flush()
        return user

    def assign_role(self, user_id: uuid.UUID, role_name: str) -> User:
        """Assign a role to a user (idempotent)."""
        user = self.get_user_by_id(user_id)
        role = self._get_role(role_name)
        if role is None:
            raise NotFoundException(message=f"Role '{role_name}' not found.")
        if role not in user.roles:
            user.roles.append(role)
            self._session.flush()
        return user

    def revoke_role(self, user_id: uuid.UUID, role_name: str) -> User:
        """Remove a role from a user."""
        user = self.get_user_by_id(user_id)
        user.roles = [r for r in user.roles if r.name != role_name]
        self._session.flush()
        return user

    def unlock_user(self, user_id: uuid.UUID) -> User:
        """Reset the failed login counter and unlock the account."""
        user = self.get_user_by_id(user_id)
        user.is_locked = False
        user.failed_login_count = 0
        user.locked_at = None
        self._session.flush()
        return user

    # ------------------------------------------------------------------
    # Delete (soft)
    # ------------------------------------------------------------------

    def delete_user(self, user_id: uuid.UUID) -> None:
        """Soft-delete a user account."""
        from datetime import datetime, timezone
        user = self.get_user_by_id(user_id)
        user.is_deleted = True
        user.is_active = False
        user.deleted_at = datetime.now(tz=timezone.utc)
        self._session.flush()
        logger.info("User soft-deleted", user_id=str(user_id))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _username_exists(self, username: str) -> bool:
        return self._session.execute(
            select(User.id).where(User.username == username)
        ).scalar_one_or_none() is not None

    def _email_exists(self, email: str) -> bool:
        return self._session.execute(
            select(User.id).where(User.email == email)
        ).scalar_one_or_none() is not None

    def _get_role(self, role_name: str) -> Role | None:
        return self._session.execute(
            select(Role).where(Role.name == role_name)
        ).scalar_one_or_none()
