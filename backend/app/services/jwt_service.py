from datetime import datetime, timedelta
from jose import jwt
SECRET_KEY = "supersecretkey"
ALGORITHM = "HS256"
def create_access_token(email: str):
    payload = {
        "sub": email,
        "exp": datetime.utcnow() + timedelta(days=1)
        }
    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
            )