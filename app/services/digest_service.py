"""Digest service for batching lower-priority important emails into daily summaries."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.processed_email import NotificationLog, ProcessedEmail
from .pushover_service import PushoverService

logger = logging.getLogger(__name__)


class DigestService:
    """Build and send daily digest of notable emails."""

    def __init__(
        self,
        db_session: Session,
        pushover_service: PushoverService,
    ):
        """Initialize digest service."""
        self.db = db_session
        self.pushover = pushover_service

    def get_pending_digest_emails(self) -> list[ProcessedEmail]:
        """Get all emails that are eligible for digest but not yet sent.

        Returns:
            List of ProcessedEmail objects pending digest
        """
        return (
            self.db.query(ProcessedEmail)
            .filter(
                ProcessedEmail.digest_eligible == True,
                ProcessedEmail.digest_sent == False,
            )
            .order_by(ProcessedEmail.importance_score.desc())
            .all()
        )

    def build_digest_message(self, emails: list[ProcessedEmail]) -> Optional[str]:
        """Build the digest message content.

        Args:
            emails: List of emails to include in digest

        Returns:
            Formatted digest message or None if empty
        """
        if not emails:
            return None

        # Group by sender domain for organization
        lines = [f"<b>{len(emails)} notable emails</b>\n"]

        for i, email in enumerate(emails[:10], 1):  # Cap at 10 in digest
            sender = email.sender_name or email.sender_email
            sender_short = sender[:25] + "..." if len(sender) > 25 else sender
            subject_short = (email.subject or "")[:40]
            if len(email.subject or "") > 40:
                subject_short += "..."
            score = float(email.importance_score) if email.importance_score else 0

            line = f"{i}. <b>{sender_short}</b>\n   {subject_short}\n   Score: {score:.0%}"

            # Add deadline if present
            if email.deadline_text:
                line += f"\n   Deadline: {email.deadline_text}"

            lines.append(line)

        if len(emails) > 10:
            lines.append(f"\n...and {len(emails) - 10} more")

        return "\n\n".join(lines)

    def send_digest(self) -> dict:
        """Send digest notification for all pending emails.

        Returns:
            Dict with success status and counts
        """
        emails = self.get_pending_digest_emails()

        if not emails:
            logger.info("No pending digest emails to send")
            return {
                "success": True,
                "emails_included": 0,
                "message": "No pending emails for digest",
            }

        message = self.build_digest_message(emails)

        if not message:
            return {
                "success": True,
                "emails_included": 0,
                "message": "No digest message to send",
            }

        # Send via Pushover
        result = self.pushover.send_notification(
            title=f"Email Digest ({len(emails)} emails)",
            message=message,
            priority=self.pushover.PRIORITY_LOW,  # Low priority for digest
            sound=self.pushover.SOUND_NONE,  # Silent
            html=True,
        )

        # Log the digest notification
        notification_log = NotificationLog(
            notification_type="digest",
            title=f"Email Digest ({len(emails)} emails)",
            message=message[:1000],
            priority=-1,  # Low priority
            status="sent" if result.success else "failed",
            error_message=result.error,
            pushover_receipt=result.receipt,
        )
        self.db.add(notification_log)

        if result.success:
            # Mark all emails as digest_sent
            now = datetime.now(timezone.utc)
            for email in emails:
                email.digest_sent = True
                email.digest_sent_at = now
                # Link to notification log
                email.notifications.append(notification_log)

            self.db.commit()
            logger.info(f"Digest sent successfully with {len(emails)} emails")

            return {
                "success": True,
                "emails_included": len(emails),
                "message": f"Digest sent with {len(emails)} emails",
            }
        else:
            self.db.commit()  # Still save the notification log
            logger.error(f"Failed to send digest: {result.error}")

            return {
                "success": False,
                "emails_included": 0,
                "error": result.error,
            }

    def get_digest_stats(self) -> dict:
        """Get statistics about digest emails.

        Returns:
            Dict with digest stats
        """
        from sqlalchemy import func

        pending = (
            self.db.query(func.count(ProcessedEmail.id))
            .filter(
                ProcessedEmail.digest_eligible == True,
                ProcessedEmail.digest_sent == False,
            )
            .scalar()
            or 0
        )

        total_digested = (
            self.db.query(func.count(ProcessedEmail.id))
            .filter(ProcessedEmail.digest_sent == True)
            .scalar()
            or 0
        )

        return {
            "pending_digest": pending,
            "total_digested": total_digested,
        }
