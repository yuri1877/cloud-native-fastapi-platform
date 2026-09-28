"""Import all models here so they register on ``Base.metadata`` (used by Alembic)."""

from app.models.user import User

__all__ = ["User"]
