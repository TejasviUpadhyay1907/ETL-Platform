"""Reset admin password and fix login."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.engine import get_session
from app.auth.password import hash_password, verify_password
from app.database.models.auth.user import User
from app.database.models.auth.role import Role
from sqlalchemy import select

NEW_PASSWORD = "Admin1234!"

with get_session() as session:
    # Get admin user
    user = session.execute(
        select(User).where(User.username == "admin")
    ).scalar_one_or_none()

    if user is None:
        print("Admin user not found — creating fresh...")
        from app.auth.rbac import seed_roles_and_permissions
        seed_roles_and_permissions(session)

        user = User(
            username="admin",
            email="admin@etlplatform.local",
            hashed_password=hash_password(NEW_PASSWORD),
            is_active=True,
            is_superuser=True,
            failed_login_count=0,
            is_locked=False,
            is_deleted=False,
        )
        role = session.execute(
            select(Role).where(Role.name == "administrator")
        ).scalar_one_or_none()
        if role:
            user.roles.append(role)
        session.add(user)
    else:
        print(f"Found admin user: id={user.id}")
        print(f"  is_active:  {user.is_active}")
        print(f"  is_locked:  {user.is_locked}")
        print(f"  is_deleted: {user.is_deleted}")
        print(f"  failed_login_count: {user.failed_login_count}")

        # Reset everything that could block login
        user.hashed_password   = hash_password(NEW_PASSWORD)
        user.is_active         = True
        user.is_locked         = False
        user.is_deleted        = False
        user.failed_login_count = 0
        user.locked_at         = None
        user.is_superuser      = True

        # Make sure administrator role assigned
        role_names = [r.name for r in user.roles]
        if "administrator" not in role_names:
            role = session.execute(
                select(Role).where(Role.name == "administrator")
            ).scalar_one_or_none()
            if role:
                user.roles.append(role)

    session.commit()

    # Verify password works
    ok = verify_password(NEW_PASSWORD, user.hashed_password)
    print()
    print(f"Password hash updated. Verify test: {ok}")
    print(f"Roles: {[r.name for r in user.roles]}")
    print()
    print("=" * 40)
    print("LOGIN CREDENTIALS:")
    print(f"  Username: admin")
    print(f"  Password: {NEW_PASSWORD}")
    print(f"  API URL:  http://localhost:8001")
    print("=" * 40)
