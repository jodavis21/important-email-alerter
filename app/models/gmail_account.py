"""Gmail account model for storing OAuth credentials."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from .database import Base


class GmailAccount(Base):
    """Stores OAuth tokens and settings for each monitored Gmail account."""

    __tablename__ = "gmail_accounts"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255))
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expiry = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True, index=True)
    last_check = Column(DateTime(timezone=True))
    last_history_id = Column(String(50))  # Gmail history ID for incremental sync
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<GmailAccount {self.email}>"

    @property
    def is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if self.token_expiry is None:
            return True
        return datetime.now(timezone.utc) >= self.token_expiry

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "email": self.email,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
