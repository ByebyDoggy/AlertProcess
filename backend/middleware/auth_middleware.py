"""
Shared JWT Authentication Middleware for ChainDetector services.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

security = HTTPBearer()


class JWTVerifier:
    def __init__(self, secret_key: str = JWT_SECRET_KEY, algorithm: str = JWT_ALGORITHM):
        self.secret_key = secret_key
        self.algorithm = algorithm

    def verify_token(self, token: str) -> dict:
        try:
            import jwt
        except ModuleNotFoundError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="JWT support is not installed; install PyJWT from requirements.txt",
            ) from e

        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
        except jwt.ExpiredSignatureError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

        self._ensure_not_expired(payload)
        return payload

    @staticmethod
    def _ensure_not_expired(payload: dict[str, Any]) -> None:
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )


jwt_verifier = JWTVerifier()


class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret_key: str, algorithm: str = "HS256", public_paths: List[str] = None):
        super().__init__(app)
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.public_paths = public_paths or []
        self.verifier = JWTVerifier(secret_key, algorithm)

    async def dispatch(self, request: Request, call_next):
        is_public = request.url.path in self.public_paths
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            if is_public:
                return await call_next(request)
            return JSONResponse(status_code=401, content={"detail": "Missing authorization header"})

        try:
            scheme, token = auth_header.split()
            if scheme.lower() != "bearer":
                if is_public:
                    return await call_next(request)
                return JSONResponse(status_code=401, content={"detail": "Invalid authentication scheme"})
        except ValueError:
            if is_public:
                return await call_next(request)
            return JSONResponse(status_code=401, content={"detail": "Invalid authorization header format"})

        try:
            request.state.user = self.verifier.verify_token(token)
        except HTTPException as e:
            if is_public:
                return await call_next(request)
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

        return await call_next(request)


async def get_current_user(request: Request) -> dict:
    if not hasattr(request.state, "user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return request.state.user


async def get_current_user_optional(request: Request) -> Optional[dict]:
    return getattr(request.state, "user", None)


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def require_permission(permission: str):
    async def check_permission(current_user: dict = Depends(get_current_user)) -> dict:
        permissions = current_user.get("permissions", [])
        if permission not in permissions and "admin" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return current_user

    return check_permission


def verify_token_sync(token: str) -> dict:
    return jwt_verifier.verify_token(token)
