"""Interfaces for future domain-event transport integration."""

from app.common.events.contracts import DomainEvent, EventHandler, EventPublisher

__all__ = ["DomainEvent", "EventHandler", "EventPublisher"]
