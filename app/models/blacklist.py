"""Blacklist model for blocked senders and domains."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from .database import Base


class BlacklistEntry(Base):
    """Stores blacklisted senders and domains that should always be ignored."""

    __tablename__ = "blacklist_entries"

    id = Column(Integer, primary_key=True)
    entry_type = Column(
        String(20), nullable=False, index=True
    )  # 'email' or 'domain'
    value = Column(String(255), nullable=False, index=True)  # email or domain
    notes = Column(Text)  # Optional description/reason
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("entry_type", "value", name="uq_blacklist_type_value"),
    )

    def __repr__(self) -> str:
        return f"<BlacklistEntry {self.entry_type}:{self.value}>"

    @classmethod
    def is_blacklisted(cls, db_session, email: str) -> bool:
        """Check if an email address or its domain is blacklisted.

        Args:
            db_session: SQLAlchemy session
            email: Email address to check

        Returns:
            True if email or domain is blacklisted
        """
        email_lower = email.lower().strip()
        domain = email_lower.split("@")[-1] if "@" in email_lower else ""

        # Check for exact email match
        email_match = (
            db_session.query(cls)
            .filter(
                cls.entry_type == "email",
                cls.value == email_lower,
                cls.is_active == True,
            )
            .first()
        )

        if email_match:
            return True

        # Check for domain match
        if domain:
            domain_match = (
                db_session.query(cls)
                .filter(
                    cls.entry_type == "domain",
                    cls.value == domain,
                    cls.is_active == True,
                )
                .first()
            )
            return domain_match is not None

        return False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "entry_type": self.entry_type,
            "value": self.value,
            "notes": self.notes,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
