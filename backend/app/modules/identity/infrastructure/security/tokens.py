from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from cryptography.hazmat.primitives import serialization
from jwt import InvalidTokenError
from pydantic import SecretStr
from uuid6 import uuid7

from app.common.config import Settings
from app.common.errors import ErrorCode
from app.common.exceptions import AppError
from app.modules.identity.application.services import AccessTokenClaims

_ALLOWED_ALGORITHMS = {"EdDSA", "ES256"}


class JwtTokenService:
    """Issue identity-only access JWTs and opaque refresh credentials."""

    def __init__(self, settings: Settings) -> None:
        if settings.jwt_algorithm not in _ALLOWED_ALGORITHMS:
            raise ValueError("Unsupported JWT algorithm")
        if settings.jwt_private_key_pem is None:
            raise RuntimeError("JWT signing key is not configured")

        self._algorithm = settings.jwt_algorithm
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._key_id = settings.jwt_current_key_id
        self._private_key = settings.jwt_private_key_pem.get_secret_value()
        self._lifetime_seconds = settings.auth_access_token_lifetime_seconds
        self._clock_skew_seconds = settings.jwt_clock_skew_seconds
        private_key = serialization.load_pem_private_key(
            self._private_key.encode(),
            password=None,
        )
        current_public_key = (
            private_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        self._public_keys = {
            **settings.jwt_previous_public_keys,
            self._key_id: current_public_key,
        }

    @property
    def access_token_lifetime_seconds(self) -> int:
        return self._lifetime_seconds

    def create_access_token(self, *, user_id: UUID, session_id: UUID) -> str:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._lifetime_seconds)
        claims = {
            "ver": 1,
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid7()),
            "iss": self._issuer,
            "aud": self._audience,
            "iat": now,
            "nbf": now,
            "exp": expires_at,
            "type": "access",
        }
        return jwt.encode(
            claims,
            self._private_key,
            algorithm=self._algorithm,
            headers={"kid": self._key_id, "typ": "JWT"},
        )

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            header = jwt.get_unverified_header(token)
            key_id = header.get("kid")
            algorithm = header.get("alg")
            if not isinstance(key_id, str) or algorithm not in _ALLOWED_ALGORITHMS:
                raise InvalidTokenError("Invalid JWT header")
            public_key = self._public_keys.get(key_id)
            if public_key is None:
                raise InvalidTokenError("Unknown signing key")
            claims = jwt.decode(
                token,
                public_key,
                algorithms=sorted(_ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
                options={
                    "require": [
                        "sub",
                        "ver",
                        "sid",
                        "jti",
                        "iss",
                        "aud",
                        "iat",
                        "nbf",
                        "exp",
                        "type",
                    ]
                },
            )
            if claims.get("type") != "access":
                raise InvalidTokenError("Invalid token type")
            if claims.get("ver") != 1:
                raise InvalidTokenError("Unsupported token version")
            return AccessTokenClaims(
                version=claims["ver"],
                subject=UUID(claims["sub"]),
                session_id=UUID(claims["sid"]),
                token_id=UUID(claims["jti"]),
                issued_at=datetime.fromtimestamp(claims["iat"], UTC),
                not_before=datetime.fromtimestamp(claims["nbf"], UTC),
                expires_at=datetime.fromtimestamp(claims["exp"], UTC),
            )
        except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise AppError(
                code=ErrorCode.UNAUTHORIZED,
                title="Authentication failed",
                detail="Authentication credentials are invalid.",
                status_code=401,
            ) from error

    @staticmethod
    def generate_refresh_token() -> SecretStr:
        return SecretStr(secrets.token_urlsafe(32))

    @staticmethod
    def hash_refresh_token(token: SecretStr | str) -> str:
        value = token.get_secret_value() if isinstance(token, SecretStr) else token
        return hashlib.sha256(value.encode()).hexdigest()
