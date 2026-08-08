from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GatewayResult:
    delivered: bool
    reference: str
    error_code: str | None = None
    error_detail: str | None = None


class NotificationGateway(Protocol):
    async def send_email(
        self, recipient: str, subject: str, body: str, idempotency_key: str
    ) -> GatewayResult: ...
    async def send_sms(
        self, recipient: str, body: str, idempotency_key: str
    ) -> GatewayResult: ...
    async def send_push(
        self, recipient: str, subject: str, body: str, idempotency_key: str
    ) -> GatewayResult: ...
    async def send_in_app(
        self, recipient: str, subject: str, body: str, idempotency_key: str
    ) -> GatewayResult: ...
