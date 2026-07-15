"""
Database Dependencies
=====================
FastAPI dependency injection for database sessions.

Usage:
    @router.post("/something")
    def my_route(db: Session = Depends(get_db)):
        # db is a SQLAlchemy session — automatically closed after request
        ...

Why use a dependency?
- Each request gets its own session (no shared state)
- Session is automatically closed after the request (even if it errors)
- Easy to swap for testing (override the dependency)
"""

from app.db.database import SessionLocal


def get_db():
    """
    Yield a database session for the duration of a request.
    The session is closed automatically when the request finishes.
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()