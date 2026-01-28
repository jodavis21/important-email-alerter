"""Processed email and notification log models."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class ProcessedEmail(Base):
    """Tracks emails that have been processed to avoid duplicates."""

    __tablename__ = "processed_emails"

    id = Column(Integer, primary_key=True)
    gmail_account_id = Column(
        Integer, ForeignKey("gmail_accounts.id", ondelete="CASCADE"), nullable=False
    )
    message_id = Column(String(255), nullable=False, index=True)  # Gmail message ID
    thread_id = Column(String(255))
    sender_email = Column(String(255), nullable=False, index=True)
    sender_name = Column(String(255))
    subject = Column(Text)
    received_at = Column(DateTime(timezone=True), index=True)
    is_whitelisted = Column(Boolean, default=False)
    importance_score = Column(Numeric(3, 2))  # 0.00 to 1.00 from Claude
    importance_reason = Column(Text)  # Claude's explanation
    notification_sent = Column(Boolean, default=False, index=True)
    notification_sent_at = Column(DateTime(timezone=True))
    detected_deadline = Column(DateTime(timezone=True))  # Extracted deadline date
    deadline_text = Column(String(255))  # Human-readable deadline text (e.g., "Tax filing due Feb 15")
    digest_eligible = Column(Boolean, default=False, index=True)  # True if email is queued for digest
    digest_sent = Column(Boolean, default=False, index=True)  # True if included in a digest
    digest_sent_at = Column(DateTime(timezone=True))  # When digest was sent
    processed_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    gmail_account = relationship("GmailAccount", backref="processed_emails")
    notifications = relationship(
        "NotificationLog", back_populates="processed_email", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "gmail_account_id", "message_id", name="uq_processed_account_message"
        ),
    )

    def __repr__(self) -> str:
        return f"<ProcessedEmail {self.message_id[:20]}...>"

    @property
    def importance_score_float(self) -> float:
        """Get importance score as float."""
        if self.importance_score is None:
            return 0.0
        return float(self.importance_score)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "gmail_account_id": self.gmail_account_id,
            "message_id": self.message_id,
            "sender_email": self.sender_email,
            "sender_name": self.sender_name,
            "subject": self.subject,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "is_whitelisted": self.is_whitelisted,
            "importance_score": float(self.importance_score)
            if self.importance_score
            else None,
            "importance_reason": self.importance_reason,
            "notification_sent": self.notification_sent,
            "detected_deadline": self.detected_deadline.isoformat() if self.detected_deadline else None,
            "deadline_text": self.deadline_text,
            "digest_eligible": self.digest_eligible,
            "digest_sent": self.digest_sent,
            "digest_sent_at": self.digest_sent_at.isoformat() if self.digest_sent_at else None,
            "processed_at": self.processed_at.isoformat()
            if self.processed_at
            else None,
        }


class NotificationLog(Base):
    """Audit log for all notifications sent."""

    __tablename__ = "notification_log"

    id = Column(Integer, primary_key=True)
    processed_email_id = Column(
        Integer, ForeignKey("processed_emails.id", ondelete="SET NULL")
    )
    notification_type = Column(String(20), default="pushover")
    title = Column(String(255))
    message = Column(Text)
    priority = Column(Integer, default=0)  # Pushover priority (-2 to 2)
    status = Column(String(20), nullable=False, index=True)  # 'sent', 'failed', 'rate_limited'
    error_message = Column(Text)
    pushover_receipt = Column(String(50))  # For emergency priority tracking
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # Relationship
    processed_email = relationship("ProcessedEmail", back_populates="notifications")

    def __repr__(self) -> str:
        return f"<NotificationLog {self.id} status={self.status}>"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "processed_email_id": self.processed_email_id,
            "notification_type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "priority": self.priority,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
