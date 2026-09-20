"""
Minimal auth. No JWT library, no user DB, no bcrypt — just enough to gate
the demo behind a login screen with a real signed, expiring token.
"""
import os
import time
import hmac
import hashlib
import base64
import json
from fastapi import Header, HTTPException

SECRET = os.getenv("AUTH_SECRET", "change-this-demo-secret").encode()
DEMO_USERNAME = os.getenv("DEMO_USERNAME", "admin")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "admin123")
TOKEN_TTL_SECONDS = 8 * 60 * 60  # 8 hour session


def _sign(payload: str) -> str:
    return hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()


def create_token(username: str) -> str:
    body = json.dumps({"u": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS})
    b64 = base64.urlsafe_b64encode(body.encode()).decode()
    sig = _sign(b64)
    return f"{b64}.{sig}"


def verify_token(token: str) -> str:
    try:
        b64, sig = token.split(".")
        expected = _sign(b64)
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        data = json.loads(base64.urlsafe_b64decode(b64.encode()))
        if data["exp"] < time.time():
            raise ValueError("expired")
        return data["u"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")


def check_credentials(username: str, password: str) -> bool:
    return username == DEMO_USERNAME and password == DEMO_PASSWORD


def require_auth(authorization: str = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing session token")
    token = authorization.removeprefix("Bearer ").strip()
    return verify_token(token)
