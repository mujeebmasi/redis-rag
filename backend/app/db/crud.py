from sqlalchemy.orm import Session

from app.db.models import User


def get_user_by_email(db: Session,email: str):
    return (
        db.query(User)
        .filter(User.email == email)
        .first()
    )


def create_user(db: Session,email: str):
    user = User(
        email=email,
        is_verified=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user