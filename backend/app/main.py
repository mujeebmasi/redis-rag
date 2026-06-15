from fastapi import FastAPI
from app.core.redis_client import redis_client

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Redis RAG API Running"}

@app.get("/redis-test")
def redis_test():
    redis_client.set("name", "Mujeeb")
    value = redis_client.get("name")

    return {
        "redis_working": True,
        "value": value
    }