from pydantic import BaseModel, ConfigDict, Field, SecretStr


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "current_password": "current-secret",
                    "new_password": "A-new-strong-secret-42!",
                }
            ]
        },
    )

    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=1, max_length=1024)


class PasswordForgotRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"email": "identity@example.com"}]},
    )

    email: str = Field(min_length=3, max_length=320)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "token": "opaque-password-reset-token",
                    "new_password": "A-new-strong-secret-42!",
                }
            ]
        },
    )

    token: SecretStr = Field(min_length=32, max_length=512)
    new_password: SecretStr = Field(min_length=1, max_length=1024)


class EmailVerifyRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"token": "opaque-email-verification-token"}]},
    )

    token: SecretStr = Field(min_length=32, max_length=512)


class EmailResendRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"email": "identity@example.com"}]},
    )

    email: str = Field(min_length=3, max_length=320)


class GenericAcceptedResponse(BaseModel):
    message: str
