"""Email processing orchestrator - ties all services together."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..models.blacklist import BlacklistEntry
from ..models.gmail_account import GmailAccount
from ..models.processed_email import NotificationLog, ProcessedEmail
from ..models.whitelist import WhitelistEntry
from .claude_analyzer import ClaudeAnalyzer
from .gmail_service import EmailMessage, GmailService
from .pushover_service import PushoverService

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing emails for one account."""

    account_email: str
    emails_fetched: int = 0
    emails_analyzed: int = 0
    notifications_sent: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ProcessingSummary:
    """Summary of processing all accounts."""

    accounts_processed: int = 0
    total_emails_fetched: int = 0
    total_emails_analyzed: int = 0
    total_notifications_sent: int = 0
    account_results: list[ProcessingResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "accounts_processed": self.accounts_processed,
            "total_emails_fetched": self.total_emails_fetched,
            "total_emails_analyzed": self.total_emails_analyzed,
            "total_notifications_sent": self.total_notifications_sent,
            "account_results": [
                {
                    "account_email": r.account_email,
                    "emails_fetched": r.emails_fetched,
                    "emails_analyzed": r.emails_analyzed,
                    "notifications_sent": r.notifications_sent,
                    "errors": r.errors,
                }
                for r in self.account_results
            ],
            "errors": self.errors,
        }


class EmailProcessor:
    """Orchestrates email fetching, analysis, and notifications."""

    def __init__(
        self,
        db_session: Session,
        claude_analyzer: ClaudeAnalyzer,
        pushover_service: PushoverService,
        google_client_id: str,
        google_client_secret: str,
        importance_threshold: float = 0.7,
        max_emails_per_check: int = 50,
        digest_enabled: bool = True,
        digest_threshold_low: float = 0.5,
        digest_threshold_high: float = 0.69,
    ):
        """Initialize email processor."""
        self.db = db_session
        self.claude = claude_analyzer
        self.pushover = pushover_service
        self.google_client_id = google_client_id
        self.google_client_secret = google_client_secret
        self.importance_threshold = importance_threshold
        self.max_emails = max_emails_per_check
        self.digest_enabled = digest_enabled
        self.digest_threshold_low = digest_threshold_low
        self.digest_threshold_high = digest_threshold_high

    def process_all_accounts(self) -> ProcessingSummary:
        """Process emails for all active Gmail accounts.

        Returns:
            ProcessingSummary with counts and details
        """
        summary = ProcessingSummary()

        accounts = (
            self.db.query(GmailAccount)
            .filter(GmailAccount.is_active == True)
            .all()
        )

        if not accounts:
            logger.info("No active Gmail accounts to process")
            return summary

        for account in accounts:
            try:
                result = self.process_account(account)
                summary.accounts_processed += 1
                summary.total_emails_fetched += result.emails_fetched
                summary.total_emails_analyzed += result.emails_analyzed
                summary.total_notifications_sent += result.notifications_sent
                summary.account_results.append(result)

                if result.errors:
                    summary.errors.extend(
                        [f"{account.email}: {e}" for e in result.errors]
                    )

            except Exception as e:
                error_msg = f"Error processing {account.email}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                summary.errors.append(error_msg)
                summary.account_results.append(
                    ProcessingResult(
                        account_email=account.email,
                        errors=[str(e)],
                    )
                )

        # Commit all changes
        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            self.db.rollback()
            summary.errors.append(f"Database commit failed: {str(e)}")

        return summary

    def process_account(self, account: GmailAccount) -> ProcessingResult:
        """Process emails for a single Gmail account."""
        result = ProcessingResult(account_email=account.email)

        logger.info(f"Processing account: {account.email}")

        # Create Gmail service
        gmail = GmailService(
            access_token=account.access_token,
            refresh_token=account.refresh_token,
            client_id=self.google_client_id,
            client_secret=self.google_client_secret,
            token_expiry=account.token_expiry,
        )

        try:
            # Fetch new emails
            emails, new_history_id = gmail.fetch_new_emails(
                since_history_id=account.last_history_id,
                max_results=self.max_emails,
            )
            result.emails_fetched = len(emails)
            logger.info(f"Fetched {len(emails)} emails from {account.email}")

            # Update account with refreshed token if needed
            if gmail.was_token_refreshed:
                new_token, new_refresh, new_expiry = gmail.get_updated_credentials()
                account.access_token = new_token
                if new_refresh:
                    account.refresh_token = new_refresh
                account.token_expiry = new_expiry

            # Update history ID and last check time
            account.last_history_id = new_history_id
            account.last_check = datetime.now(timezone.utc)

            # Process each email
            for email in emails:
                if self._is_already_processed(account.id, email.message_id):
                    logger.debug(f"Skipping already processed: {email.message_id}")
                    continue

                try:
                    processed = self._process_single_email(account, email)
                    if processed:
                        result.emails_analyzed += 1
                        if processed.notification_sent:
                            result.notifications_sent += 1
                except Exception as e:
                    error_msg = f"Failed to process email {email.message_id}: {str(e)}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)

        except Exception as e:
            error_msg = f"Failed to fetch emails: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result.errors.append(error_msg)

        return result

    def _process_single_email(
        self,
        account: GmailAccount,
        email: EmailMessage,
    ) -> Optional[ProcessedEmail]:
        """Process a single email message."""
        logger.debug(f"Processing email: {email.subject[:50]}...")

        # Check blacklist FIRST - skip entirely if blacklisted
        if BlacklistEntry.is_blacklisted(self.db, email.sender_email):
            logger.info(f"Skipping blacklisted sender: {email.sender_email}")
            return None

        # Check whitelist
        is_whitelisted = WhitelistEntry.is_whitelisted(self.db, email.sender_email)

        # Analyze with Claude
        analysis = self.claude.analyze_email(
            sender_email=email.sender_email,
            sender_name=email.sender_name,
            subject=email.subject,
            body_snippet=email.body_text,
            is_whitelisted=is_whitelisted,
        )

        logger.info(
            f"Email '{email.subject[:30]}...' scored {analysis.score:.2f} "
            f"({analysis.category})"
        )

        # Log deadline if detected
        if analysis.deadline_date:
            logger.info(
                f"Deadline detected for '{email.subject[:30]}...': "
                f"{analysis.deadline_text} ({analysis.deadline_date})"
            )

        # Create processed email record
        processed = ProcessedEmail(
            gmail_account_id=account.id,
            message_id=email.message_id,
            thread_id=email.thread_id,
            sender_email=email.sender_email,
            sender_name=email.sender_name,
            subject=email.subject,
            received_at=email.received_at,
            is_whitelisted=is_whitelisted,
            importance_score=Decimal(str(round(analysis.score, 2))),
            importance_reason=analysis.reason,
            detected_deadline=analysis.deadline_date,
            deadline_text=analysis.deadline_text,
        )

        # Determine notification handling based on score
        if analysis.score >= self.importance_threshold:
            # High importance - send immediately
            logger.info(f"Sending notification for: {email.subject[:50]}...")

            notification_result = self.pushover.send_important_email_alert(
                sender=email.sender_name or email.sender_email,
                subject=email.subject,
                importance_reason=analysis.reason,
                account_email=account.email,
                importance_score=analysis.score,
                deadline_date=analysis.deadline_date,
                deadline_text=analysis.deadline_text,
            )

            # Log the notification
            notification_log = NotificationLog(
                notification_type="pushover",
                title=f"Important: {email.sender_name or email.sender_email}"[:255],
                message=f"Subject: {email.subject}\nReason: {analysis.reason}"[:1000],
                priority=1 if analysis.score >= 0.8 else 0,
                status="sent" if notification_result.success else "failed",
                error_message=notification_result.error,
                pushover_receipt=notification_result.receipt,
            )

            if notification_result.success:
                processed.notification_sent = True
                processed.notification_sent_at = datetime.now(timezone.utc)
                logger.info(f"Notification sent successfully for: {email.subject[:30]}")
            else:
                logger.warning(
                    f"Notification failed for: {email.subject[:30]} - "
                    f"{notification_result.error}"
                )

            self.db.add(notification_log)
            processed.notifications.append(notification_log)

        elif (
            self.digest_enabled
            and analysis.score >= self.digest_threshold_low
            and analysis.score <= self.digest_threshold_high
        ):
            # Medium importance - queue for digest
            processed.digest_eligible = True
            logger.info(
                f"Email '{email.subject[:30]}...' queued for digest "
                f"(score: {analysis.score:.2f})"
            )

        self.db.add(processed)
        return processed

    def _is_already_processed(self, account_id: int, message_id: str) -> bool:
        """Check if email was already processed."""
        return (
            self.db.query(ProcessedEmail)
            .filter(
                ProcessedEmail.gmail_account_id == account_id,
                ProcessedEmail.message_id == message_id,
            )
            .first()
            is not None
        )

    def get_recent_processed_emails(
        self,
        limit: int = 50,
        account_id: Optional[int] = None,
    ) -> list[ProcessedEmail]:
        """Get recently processed emails.

        Args:
            limit: Maximum number to return
            account_id: Filter to specific account (optional)

        Returns:
            List of ProcessedEmail objects
        """
        query = self.db.query(ProcessedEmail)

        if account_id:
            query = query.filter(ProcessedEmail.gmail_account_id == account_id)

        return (
            query.order_by(ProcessedEmail.processed_at.desc())
            .limit(limit)
            .all()
        )

    def get_stats(self) -> dict:
        """Get processing statistics."""
        from sqlalchemy import func

        # Total emails processed
        total_processed = self.db.query(func.count(ProcessedEmail.id)).scalar()

        # Notifications sent
        notifications_sent = (
            self.db.query(func.count(ProcessedEmail.id))
            .filter(ProcessedEmail.notification_sent == True)
            .scalar()
        )

        # Active accounts
        active_accounts = (
            self.db.query(func.count(GmailAccount.id))
            .filter(GmailAccount.is_active == True)
            .scalar()
        )

        # Whitelist entries
        whitelist_count = (
            self.db.query(func.count(WhitelistEntry.id))
            .filter(WhitelistEntry.is_active == True)
            .scalar()
        )

        # Blacklist entries
        blacklist_count = (
            self.db.query(func.count(BlacklistEntry.id))
            .filter(BlacklistEntry.is_active == True)
            .scalar()
        )

        # Average importance score
        avg_score = (
            self.db.query(func.avg(ProcessedEmail.importance_score)).scalar()
        )

        return {
            "total_emails_processed": total_processed or 0,
            "notifications_sent": notifications_sent or 0,
            "active_accounts": active_accounts or 0,
            "whitelist_entries": whitelist_count or 0,
            "blacklist_entries": blacklist_count or 0,
            "average_importance_score": float(avg_score) if avg_score else 0.0,
        }
