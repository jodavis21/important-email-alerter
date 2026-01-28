"""User feedback model for tracking importance corrections."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String

from .database import Base


class UserFeedback(Base):
    """Stores user feedback on email importance."""

    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True)
    processed_email_id = Column(
        Integer, ForeignKey("processed_emails.id", ondelete="CASCADE"), nullable=False
    )
    feedback_type = Column(
        String(20), nullable=False, index=True
    )  # 'not_important', 'important'
    original_score = Column(Numeric(3, 2))  # Original importance score
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return f"<UserFeedback {self.id} type={self.feedback_type}>"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "processed_email_id": self.processed_email_id,
            "feedback_type": self.feedback_type,
            "original_score": float(self.original_score) if self.original_score else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
