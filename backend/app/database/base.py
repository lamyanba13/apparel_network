from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

from app.database.metadata import metadata


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative root shared by future module-owned persistence models."""

    metadata = metadata
