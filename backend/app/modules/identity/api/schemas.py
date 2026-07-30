from pydantic import BaseModel, ConfigDict, Field, SecretStr


class AuthenticationRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "email": "identity@example.com",
                    "password": "correct horse battery staple",
                    "device_name": "Personal phone",
                }
            ]
        },
    )

    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)
    device_name: str | None = Field(default=None, min_length=1, max_length=120)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"refresh_token": "opaque-refresh-credential"}]
        },
    )

    refresh_token: SecretStr = Field(min_length=32, max_length=512)


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "access_token": "eyJ...signed-access-token",
                    "refresh_token": "opaque-refresh-credential",
                    "expires_in": 900,
                    "token_type": "Bearer",
                }
            ]
        }
    )

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str


class LogoutAllResponse(BaseModel):
    revoked_sessions: int
