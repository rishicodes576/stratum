import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import User, now

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt${salt}${digest.hex()}"


async def verify_password(password: str, encoded: str) -> bool:
    _, salt, _ = encoded.split("$")
    candidate = await asyncio.to_thread(hash_password, password, salt)
    return hmac.compare_digest(candidate, encoded)


def token_for(user: User) -> str:
    settings = get_settings()
    return jwt.encode(
        {
            "sub": user.id,
            "tid": user.tenant_id,
            "iat": now(),
            "exp": now() + timedelta(minutes=settings.session_minutes),
            "iss": "stratum",
            "aud": "stratum-api",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


@dataclass(frozen=True)
class Principal:
    id: str
    tenant_id: str
    name: str
    email: str
    role: str


async def principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    if not credentials:
        raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(
            credentials.credentials,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            issuer="stratum",
            audience="stratum-api",
            options={"require": ["sub", "tid", "exp", "iat"]},
        )
        user = await session.get(User, payload["sub"])
        if not user or user.tenant_id != payload["tid"]:
            raise HTTPException(401, "Session no longer valid")
        result = Principal(user.id, user.tenant_id, user.name, user.email, user.role)
        # Release the authentication read transaction before long-lived SSE streams.
        await session.rollback()
        return result
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "Session expired or invalid") from exc


async def operator(user: Principal = Depends(principal)) -> Principal:
    if user.role not in {"admin", "operator"}:
        raise HTTPException(403, "Operator role required")
    return user


async def admin(user: Principal = Depends(principal)) -> Principal:
    if user.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return user
