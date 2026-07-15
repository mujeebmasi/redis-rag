"""
CRUD Operations
===============
Database Create / Read / Update / Delete operations.

These functions are the ONLY place that directly talks to PostgreSQL.
Routes call these functions instead of writing queries inline.

Why separate CRUD from routes?
- Keeps routes clean (they handle HTTP, not SQL)
- Reusable across multiple routes
- Easy to test in isolation
"""

from sqlalchemy.orm import Session
from app.db.models import User


def get_user_by_email(db: Session, email: str) -> User | None:
    """Look up a user by their email. Returns None if not found."""

    return (
        db.query(User)
        .filter(User.email == email)
        .first()
    )


def create_user(db: Session, email: str) -> User:
    """Create a new user with the given email (marked as verified)."""

    user = User(
        email=email,
        is_verified=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user