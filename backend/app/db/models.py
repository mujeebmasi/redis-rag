"""
Database Models
===============
SQLAlchemy ORM models — each class maps to a PostgreSQL table.

Currently we have:
- User: stores authenticated users (created after OTP verification)
"""

from sqlalchemy import Column, Integer, String, Boolean
from app.db.database import Base


class User(Base):
    """
    Users table.
    
    Created automatically when a user verifies their email OTP
    for the first time.
    """

    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    email = Column(
        String,
        unique=True,
        nullable=False,
    )

    is_verified = Column(
        Boolean,
        default=True,
    )