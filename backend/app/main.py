from fastapi import FastAPI
from dotenv import load_dotenv
from app.api.auth import router as auth_router

from app.db.database import Base, engine
from app.db import models

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(auth_router)