"""
Database Setup
==============
SQLAlchemy engine, session factory, and base class.

- engine: the connection to PostgreSQL
- SessionLocal: creates new database sessions (one per request)
- Base: all models inherit from this (User, etc.)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()