from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import SecretStr


class PasswordViolationCode(StrEnum):
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    UPPERCASE_REQUIRED = "uppercase_required"
    LOWERCASE_REQUIRED = "lowercase_required"
    NUMBER_REQUIRED = "number_required"
    SYMBOL_REQUIRED = "symbol_required"
    FORBIDDEN_PASSWORD = "forbidden_password"
    EMAIL_SIMILARITY = "email_similarity"
    RECENTLY_USED = "recently_used"


@dataclass(frozen=True, slots=True)
class PasswordViolation:
    code: PasswordViolationCode
    message: str


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    minimum_length: int
    maximum_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_number: bool
    require_symbol: bool
    forbidden_passwords: frozenset[str]


class PasswordPolicyValidator:
    """Pure password policy validation that never retains candidate secrets."""

    def __init__(self, policy: PasswordPolicy) -> None:
        self._policy = policy

    def validate_password(
        self,
        password: SecretStr,
        *,
        email: str,
    ) -> tuple[PasswordViolation, ...]:
        candidate = password.get_secret_value()
        violations: list[PasswordViolation] = []
        if len(candidate) < self._policy.minimum_length:
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.TOO_SHORT,
                    f"Use at least {self._policy.minimum_length} characters.",
                )
            )
        if len(candidate) > self._policy.maximum_length:
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.TOO_LONG,
                    f"Use no more than {self._policy.maximum_length} characters.",
                )
            )
        if self._policy.require_uppercase and not any(
            character.isupper() for character in candidate
        ):
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.UPPERCASE_REQUIRED,
                    "Include an uppercase letter.",
                )
            )
        if self._policy.require_lowercase and not any(
            character.islower() for character in candidate
        ):
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.LOWERCASE_REQUIRED,
                    "Include a lowercase letter.",
                )
            )
        if self._policy.require_number and not any(
            character.isdigit() for character in candidate
        ):
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.NUMBER_REQUIRED,
                    "Include a number.",
                )
            )
        if self._policy.require_symbol and not any(
            not character.isalnum() for character in candidate
        ):
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.SYMBOL_REQUIRED,
                    "Include a symbol.",
                )
            )
        normalized = candidate.casefold()
        if normalized in self._policy.forbidden_passwords:
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.FORBIDDEN_PASSWORD,
                    "Choose a less common password.",
                )
            )
        email_local_part = email.split("@", maxsplit=1)[0].casefold()
        compact_local_part = "".join(
            character for character in email_local_part if character.isalnum()
        )
        compact_password = "".join(
            character for character in normalized if character.isalnum()
        )
        if len(compact_local_part) >= 3 and compact_local_part in compact_password:
            violations.append(
                PasswordViolation(
                    PasswordViolationCode.EMAIL_SIMILARITY,
                    "Do not include your email name in the password.",
                )
            )
        return tuple(violations)
