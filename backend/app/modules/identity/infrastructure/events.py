from __future__ import annotations

import logging

from app.common.events import DomainEvent, EventPublisher
from app.modules.identity.domain import (
    AuthenticationFailed,
    AuthenticationSucceeded,
    LogoutCompleted,
    RefreshReuseDetected,
    RefreshRotated,
)
from app.modules.identity.domain.account_security_events import (
    AccountLocked,
    AccountSecurityCleanupCompleted,
    AccountUnlocked,
    EmailVerificationRequested,
    EmailVerified,
    PasswordChanged,
    PasswordPolicyViolation,
    PasswordResetCompleted,
    PasswordResetRequested,
    SuspiciousLoginDetected,
)
from app.modules.identity.domain.authorization_events import (
    AuthorizationDenied,
    AuthorizationGranted,
    PermissionCacheHit,
    PermissionCacheMiss,
    PermissionGranted,
    PermissionRevoked,
    RoleAssigned,
    RoleRevoked,
)
from app.modules.identity.domain.session_events import (
    OtherSessionsRevoked,
    SessionCleanupCompleted,
    SessionCreated,
    SessionExpired,
    SessionRenamed,
    SessionRevoked,
    SessionRiskUpdated,
)
from app.observability.metrics import (
    ACCOUNT_LOCKOUTS,
    AUTHENTICATION_FAILED,
    AUTHENTICATION_LOGOUT,
    AUTHENTICATION_REFRESH_REUSE,
    AUTHENTICATION_REFRESHED,
    AUTHENTICATION_SUCCEEDED,
    EMAIL_VERIFICATIONS,
    PASSWORD_CHANGES,
    PASSWORD_RESETS,
    SECURITY_EVENTS,
)

logger = logging.getLogger(__name__)


class AuthenticationEventPublisher(EventPublisher):
    """In-process authentication event consumer for logs and metrics."""

    async def publish(self, event: DomainEvent) -> None:
        extra = {
            "event": event.event_name,
            "event_id": str(event.event_id),
            "schema_version": event.schema_version,
            **event.payload,
        }
        if isinstance(event, AuthenticationSucceeded):
            AUTHENTICATION_SUCCEEDED.inc()
            logger.info(event.event_name, extra=extra)
        elif isinstance(event, AuthenticationFailed):
            AUTHENTICATION_FAILED.inc()
            logger.warning(event.event_name, extra=extra)
        elif isinstance(event, RefreshRotated):
            AUTHENTICATION_REFRESHED.inc()
            logger.info(event.event_name, extra=extra)
        elif isinstance(event, RefreshReuseDetected):
            AUTHENTICATION_REFRESH_REUSE.inc()
            logger.warning(event.event_name, extra=extra)
        elif isinstance(event, LogoutCompleted):
            AUTHENTICATION_LOGOUT.inc()
            logger.info(event.event_name, extra=extra)
        elif isinstance(
            event,
            (
                PasswordChanged,
                PasswordResetRequested,
                PasswordResetCompleted,
                EmailVerificationRequested,
                EmailVerified,
                AccountLocked,
                AccountUnlocked,
                PasswordPolicyViolation,
                SuspiciousLoginDetected,
                AccountSecurityCleanupCompleted,
            ),
        ):
            SECURITY_EVENTS.inc()
            if isinstance(event, PasswordChanged):
                PASSWORD_CHANGES.inc()
            elif isinstance(event, PasswordResetCompleted):
                PASSWORD_RESETS.inc()
            elif isinstance(event, EmailVerified):
                EMAIL_VERIFICATIONS.inc()
            elif isinstance(event, AccountLocked):
                ACCOUNT_LOCKOUTS.inc()
            if isinstance(
                event,
                (AccountLocked, PasswordPolicyViolation, SuspiciousLoginDetected),
            ):
                logger.warning(event.event_name, extra=extra)
            else:
                logger.info(event.event_name, extra=extra)
        elif isinstance(
            event,
            (
                SessionRenamed,
                SessionRevoked,
                OtherSessionsRevoked,
                SessionCleanupCompleted,
                SessionCreated,
                SessionExpired,
                SessionRiskUpdated,
            ),
        ):
            logger.info(event.event_name, extra=extra)
        elif isinstance(event, AuthorizationDenied):
            logger.warning(event.event_name, extra=extra)
        elif isinstance(
            event,
            (
                AuthorizationGranted,
                PermissionCacheHit,
                PermissionCacheMiss,
                RoleAssigned,
                RoleRevoked,
                PermissionGranted,
                PermissionRevoked,
            ),
        ):
            logger.info(event.event_name, extra=extra)
