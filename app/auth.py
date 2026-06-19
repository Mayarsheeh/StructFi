from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


# -------------------------------------------------------------------
# StructFi Auth Configuration
# -------------------------------------------------------------------

AUTH_SECRET_KEY = os.getenv(
    "STRUCTFI_AUTH_SECRET_KEY",
    "CHANGE_THIS_STRUCTFI_SECRET_KEY_BEFORE_PRODUCTION",
)

ACCESS_TOKEN_EXPIRE_SECONDS = int(
    os.getenv("STRUCTFI_ACCESS_TOKEN_EXPIRE_SECONDS", str(60 * 60 * 24))
)

security_scheme = HTTPBearer(auto_error=False)


# -------------------------------------------------------------------
# Request / Response Models
# -------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    id: int
    name: str
    email: str
    role: str
    organization_id: int
    organization_name: str
    project_id: int
    project_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


@dataclass(frozen=True)
class AuthenticatedUser:
    id: int
    name: str
    email: str
    role: str
    organization_id: int
    organization_name: str
    project_id: int
    project_name: str

    def to_public(self) -> UserPublic:
        return UserPublic(
            id=self.id,
            name=self.name,
            email=self.email,
            role=self.role,
            organization_id=self.organization_id,
            organization_name=self.organization_name,
            project_id=self.project_id,
            project_name=self.project_name,
        )

    def to_claims(self) -> Dict[str, Any]:
        return {
            "sub": str(self.id),
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "organization_id": self.organization_id,
            "organization_name": self.organization_name,
            "project_id": self.project_id,
            "project_name": self.project_name,
        }


# -------------------------------------------------------------------
# Password Hashing
# -------------------------------------------------------------------

def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    )
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def _verify_password(password: str, salt: str, expected_hash: str) -> bool:
    actual_hash = _hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


# -------------------------------------------------------------------
# StructFi Tenant/User Store
# Later we can replace this with a real database.
# -------------------------------------------------------------------

_DEFAULT_ADMIN_PASSWORD = os.getenv("STRUCTFI_ADMIN_PASSWORD", "StructFi@123")
_DEFAULT_MANAGER_PASSWORD = os.getenv("STRUCTFI_MANAGER_PASSWORD", "Manager@123")

_ADMIN_SALT = os.getenv("STRUCTFI_ADMIN_SALT", "structfi-admin-salt")
_MANAGER_SALT = os.getenv("STRUCTFI_MANAGER_SALT", "structfi-manager-salt")


_USERS: Dict[str, Dict[str, Any]] = {
    "admin@structfi.local": {
        "id": 1,
        "name": "StructFi Admin",
        "email": "admin@structfi.local",
        "role": "admin",
        "organization_id": 1,
        "organization_name": "StructFi Enterprise",
        "project_id": 1,
        "project_name": "Building v3.01",
        "password_salt": _ADMIN_SALT,
        "password_hash": _hash_password(_DEFAULT_ADMIN_PASSWORD, _ADMIN_SALT),
        "active": True,
    },
    "manager@company.local": {
        "id": 2,
        "name": "Company Network Manager",
        "email": "manager@company.local",
        "role": "manager",
        "organization_id": 2,
        "organization_name": "Client Company",
        "project_id": 2,
        "project_name": "Main Building v3.01",
        "password_salt": _MANAGER_SALT,
        "password_hash": _hash_password(_DEFAULT_MANAGER_PASSWORD, _MANAGER_SALT),
        "active": True,
    },
}


def authenticate_user(email: str, password: str) -> Optional[AuthenticatedUser]:
    normalized_email = email.strip().lower()
    record = _USERS.get(normalized_email)

    if not record or not record.get("active", False):
        return None

    valid_password = _verify_password(
        password=password,
        salt=str(record["password_salt"]),
        expected_hash=str(record["password_hash"]),
    )

    if not valid_password:
        return None

    return AuthenticatedUser(
        id=int(record["id"]),
        name=str(record["name"]),
        email=str(record["email"]),
        role=str(record["role"]),
        organization_id=int(record["organization_id"]),
        organization_name=str(record["organization_name"]),
        project_id=int(record["project_id"]),
        project_name=str(record["project_name"]),
    )


# -------------------------------------------------------------------
# JWT-like HS256 Token Helpers
# No external dependency required.
# -------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def _sign(message: str) -> str:
    signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64url_encode(signature)


def create_access_token(user: AuthenticatedUser) -> str:
    now = int(time.time())

    header = {
        "alg": "HS256",
        "typ": "JWT",
    }

    payload = {
        **user.to_claims(),
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE_SECONDS,
    }

    encoded_header = _b64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )

    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _sign(signing_input)

    return f"{signing_input}.{signature}"


def decode_access_token(token: str) -> Dict[str, Any]:
    try:
        encoded_header, encoded_payload, signature = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token format.") from exc

    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign(signing_input)

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid token signature.")

    try:
        payload = json.loads(_b64url_decode(encoded_payload).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token payload.") from exc

    exp = int(payload.get("exp", 0))

    if exp < int(time.time()):
        raise HTTPException(status_code=401, detail="Token expired.")

    return payload


def user_from_claims(claims: Dict[str, Any]) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=int(claims["sub"]),
        name=str(claims["name"]),
        email=str(claims["email"]),
        role=str(claims["role"]),
        organization_id=int(claims["organization_id"]),
        organization_name=str(claims["organization_name"]),
        project_id=int(claims["project_id"]),
        project_name=str(claims["project_name"]),
    )


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Missing bearer token.")

    claims = decode_access_token(credentials.credentials)
    return user_from_claims(claims)
