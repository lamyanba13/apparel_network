from __future__ import annotations

from collections import defaultdict
from hashlib import sha256

from app.modules.notifications.gateways.protocols import GatewayResult


class NullNotificationGateway:
    """Deterministic, network-free production-safe notification gateway."""

    def __init__(self, *, failures_before_success: int = 0) -> None:
        self._failures_before_success = failures_before_success
        self._attempts: defaultdict[str, int] = defaultdict(int)

    async def send_email(
        self, recipient: str, subject: str, body: str, idempotency_key: str
    ) -> GatewayResult:
        return self._send("email", recipient, idempotency_key)

    async def send_sms(
        self, recipient: str, body: str, idempotency_key: str
    ) -> GatewayResult:
        return self._send("sms", recipient, idempotency_key)

    async def send_push(
        self, recipient: str, subject: str, body: str, idempotency_key: str
    ) -> GatewayResult:
        return self._send("push", recipient, idempotency_key)

    async def send_in_app(
        self, recipient: str, subject: str, body: str, idempotency_key: str
    ) -> GatewayResult:
        return self._send("in_app", recipient, idempotency_key)

    def _send(self, channel: str, recipient: str, key: str) -> GatewayResult:
        self._attempts[key] += 1
        reference = sha256(f"{channel}:{recipient}:{key}".encode()).hexdigest()[:32]
        if self._attempts[key] <= self._failures_before_success:
            return GatewayResult(
                False,
                reference,
                "null_gateway_failure",
                "Configured deterministic failure",
            )
        return GatewayResult(True, reference)
