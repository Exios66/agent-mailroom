from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from agent_mailroom.operator.db import lookup_user, migrate, verify_password, write_audit

log = logging.getLogger("agent_mailroom.operator.auth")

router = APIRouter(prefix="/v1/auth", tags=["operator-auth"])
security = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"
_warned_default_secret = False


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserProfile(BaseModel):
    username: str
    role: str
    user_id: Optional[int] = None


def auth_required() -> bool:
    raw = os.environ.get("MAILROOM_OPERATOR_AUTH", "0").strip().lower()
    return raw in ("1", "true", "on", "yes")


def jwt_secret() -> str:
    global _warned_default_secret
    secret = (
        os.environ.get("MAILROOM_OPERATOR_JWT_SECRET")
        or os.environ.get("JWT_SECRET")
        or ""
    ).strip()
    if not secret:
        secret = "dev-secret-change-me"
        if not _warned_default_secret:
            log.warning("MAILROOM_OPERATOR_JWT_SECRET unset — using local-dev default")
            _warned_default_secret = True
    return secret


def jwt_expiry_hours() -> int:
    try:
        return max(1, int(os.environ.get("MAILROOM_OPERATOR_JWT_HOURS", "24")))
    except ValueError:
        return 24


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def create_access_token(username: str, role: str, user_id: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "uid": user_id,
        "exp": int((now + timedelta(hours=jwt_expiry_hours())).timestamp()),
        "iat": int(now.timestamp()),
    }
    try:
        import jwt

        return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)
    except ImportError:
        header = _b64url(json.dumps({"alg": JWT_ALGORITHM, "typ": "JWT"}).encode())
        body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
        signing = f"{header}.{body}"
        sig = hmac.new(jwt_secret().encode("utf-8"), signing.encode("ascii"), hashlib.sha256).digest()
        return f"{signing}.{_b64url(sig)}"


def decode_token(token: str) -> UserProfile:
    secret = jwt_secret()
    try:
        import jwt
        from jwt import ExpiredSignatureError, InvalidTokenError

        try:
            payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        except ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="Token expired") from exc
        except InvalidTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc
    except ImportError:
        parts = token.split(".")
        if len(parts) != 3:
            raise HTTPException(status_code=401, detail="Invalid token")
        signing = f"{parts[0]}.{parts[1]}"
        expected = hmac.new(secret.encode("utf-8"), signing.encode("ascii"), hashlib.sha256).digest()
        try:
            actual = _b64url_decode(parts[2])
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc
        if not hmac.compare_digest(expected, actual):
            raise HTTPException(status_code=401, detail="Invalid token")
        payload = json.loads(_b64url_decode(parts[1]))
        exp = payload.get("exp")
        if isinstance(exp, (int, float)) and datetime.now(timezone.utc).timestamp() > float(exp):
            raise HTTPException(status_code=401, detail="Token expired")
    username = str(payload.get("sub") or "")
    role = str(payload.get("role") or "viewer")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")
    uid = payload.get("uid")
    return UserProfile(
        username=username,
        role=role,
        user_id=int(uid) if isinstance(uid, int) else None,
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UserProfile:
    if not auth_required():
        if credentials:
            try:
                return decode_token(credentials.credentials)
            except HTTPException:
                return UserProfile(username="anonymous", role="viewer")
        return UserProfile(username="anonymous", role="viewer")
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return decode_token(credentials.credentials)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    migrate()
    row = lookup_user(req.username)
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(row["username"], row["role"], user_id=row["id"])
    write_audit(action="login", user_id=row["id"], metadata={"username": row["username"]})
    return TokenResponse(access_token=token, role=row["role"])


@router.get("/me", response_model=UserProfile)
async def me(user: UserProfile = Depends(get_current_user)):
    return user


@router.post("/logout")
async def logout(user: UserProfile = Depends(get_current_user)):
    write_audit(action="logout", user_id=user.user_id, metadata={"username": user.username})
    return {"message": "Logged out"}
