from sqlalchemy import Column, Integer, String, Boolean
from app.db.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(
        Integer,
        primary_key = True,
        index = True
    )
    
    email = Column(
        String,
        unique = True,
        nullable = False
    )
    
    is_verified = Column(
        Boolean,
        default = True
    )