"""Learned patterns model for AI score adjustments based on user feedback."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, Integer, Numeric, String, UniqueConstraint

from .database import Base


class LearnedPattern(Base):
    """Stores learned score adjustments from user feedback."""

    __tablename__ = "learned_patterns"

    id = Column(Integer, primary_key=True)
    pattern_type = Column(
        String(20), nullable=False, index=True
    )  # 'sender', 'domain', 'subject_keyword'
    pattern_value = Column(String(255), nullable=False, index=True)
    score_adjustment = Column(
        Numeric(3, 2), nullable=False
    )  # e.g., -0.15 for "not important" feedback
    feedback_count = Column(Integer, default=1)  # How many times feedback received
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("pattern_type", "pattern_value", name="uq_pattern_type_value"),
    )

    def __repr__(self) -> str:
        return f"<LearnedPattern {self.pattern_type}:{self.pattern_value} adj={self.score_adjustment}>"

    @classmethod
    def get_adjustment(
        cls, db_session, pattern_type: str, pattern_value: str
    ) -> Optional["LearnedPattern"]:
        """Get the learned adjustment for a pattern.

        Args:
            db_session: SQLAlchemy session
            pattern_type: Type of pattern ('sender', 'domain', 'subject_keyword')
            pattern_value: Value to match

        Returns:
            LearnedPattern if found, None otherwise
        """
        return (
            db_session.query(cls)
            .filter(
                cls.pattern_type == pattern_type,
                cls.pattern_value == pattern_value.lower(),
            )
            .first()
        )

    @classmethod
    def get_total_adjustment(cls, db_session, email_address: str) -> float:
        """Get total score adjustment for an email address.

        Checks both sender email and domain patterns.

        Args:
            db_session: SQLAlchemy session
            email_address: Email address to check

        Returns:
            Total score adjustment (can be positive or negative)
        """
        email_lower = email_address.lower().strip()
        domain = email_lower.split("@")[-1] if "@" in email_lower else ""

        adjustment = 0.0

        # Check sender pattern
        sender_pattern = cls.get_adjustment(db_session, "sender", email_lower)
        if sender_pattern:
            adjustment += float(sender_pattern.score_adjustment)

        # Check domain pattern
        if domain:
            domain_pattern = cls.get_adjustment(db_session, "domain", domain)
            if domain_pattern:
                adjustment += float(domain_pattern.score_adjustment)

        return adjustment

    @classmethod
    def record_feedback(
        cls,
        db_session,
        pattern_type: str,
        pattern_value: str,
        adjustment: float,
    ) -> "LearnedPattern":
        """Record or update a learned pattern from feedback.

        Args:
            db_session: SQLAlchemy session
            pattern_type: Type of pattern
            pattern_value: Value to store
            adjustment: Score adjustment to apply (negative for "not important")

        Returns:
            LearnedPattern (created or updated)
        """
        pattern_value_lower = pattern_value.lower().strip()

        existing = (
            db_session.query(cls)
            .filter(
                cls.pattern_type == pattern_type,
                cls.pattern_value == pattern_value_lower,
            )
            .first()
        )

        if existing:
            # Update existing - average the adjustments with more weight on recent feedback
            # This allows patterns to change over time if user changes their mind
            existing.feedback_count += 1
            # Weighted average: new adjustment gets more weight as feedback count increases
            weight = min(0.5, 1 / existing.feedback_count)  # Cap at 50% weight
            existing.score_adjustment = (
                float(existing.score_adjustment) * (1 - weight) + adjustment * weight
            )
            return existing
        else:
            # Create new pattern
            pattern = cls(
                pattern_type=pattern_type,
                pattern_value=pattern_value_lower,
                score_adjustment=adjustment,
            )
            db_session.add(pattern)
            return pattern

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "pattern_value": self.pattern_value,
            "score_adjustment": float(self.score_adjustment)
            if self.score_adjustment
            else None,
            "feedback_count": self.feedback_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
