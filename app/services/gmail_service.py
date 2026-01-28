"""Gmail API service for fetching and parsing emails."""

import base64
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Parsed email message."""

    message_id: str
    thread_id: str
    sender_email: str
    sender_name: Optional[str]
    subject: str
    snippet: str
    body_text: str
    received_at: datetime
    labels: list[str]


class GmailService:
    """Service for interacting with Gmail API."""

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",  # For marking as read
        "https://www.googleapis.com/auth/userinfo.email",  # For getting user email
    ]

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        token_expiry: Optional[datetime] = None,
    ):
        """Initialize Gmail service with OAuth credentials."""
        self.credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            expiry=token_expiry,
        )
        self._service = None
        self._token_refreshed = False

    @property
    def service(self):
        """Get or create Gmail API service, refreshing token if needed."""
        if self.credentials.expired and self.credentials.refresh_token:
            self.credentials.refresh(Request())
            self._token_refreshed = True

        if self._service is None:
            self._service = build("gmail", "v1", credentials=self.credentials)

        return self._service

    def get_updated_credentials(self) -> tuple[str, str, Optional[datetime]]:
        """Return current credentials after potential refresh.

        Returns:
            Tuple of (access_token, refresh_token, expiry)
        """
        return (
            self.credentials.token,
            self.credentials.refresh_token,
            self.credentials.expiry,
        )

    @property
    def was_token_refreshed(self) -> bool:
        """Check if token was refreshed during this session."""
        return self._token_refreshed

    def fetch_new_emails(
        self,
        since_history_id: Optional[str] = None,
        max_results: int = 50,
    ) -> tuple[list[EmailMessage], str]:
        """Fetch new emails from inbox.

        Args:
            since_history_id: Gmail history ID for incremental fetch
            max_results: Maximum emails to fetch

        Returns:
            Tuple of (list of EmailMessage, new history_id)
        """
        emails = []

        if since_history_id:
            # Use history API for incremental sync
            emails = self._fetch_via_history(since_history_id, max_results)
        else:
            # Full fetch for initial sync
            emails = self._fetch_recent_emails(max_results)

        # Get current history ID
        profile = self.service.users().getProfile(userId="me").execute()
        new_history_id = profile.get("historyId")

        return emails, new_history_id

    def _fetch_recent_emails(self, max_results: int) -> list[EmailMessage]:
        """Fetch recent unread emails from inbox."""
        try:
            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    labelIds=["INBOX", "UNREAD"],
                    maxResults=max_results,
                )
                .execute()
            )

            messages = results.get("messages", [])
            emails = []

            for msg in messages:
                try:
                    email = self._get_message_details(msg["id"])
                    if email:
                        emails.append(email)
                except Exception as e:
                    logger.warning(f"Failed to fetch message {msg['id']}: {e}")

            return emails

        except HttpError as e:
            logger.error(f"Gmail API error fetching recent emails: {e}")
            raise

    def _fetch_via_history(
        self,
        history_id: str,
        max_results: int,
    ) -> list[EmailMessage]:
        """Fetch emails added since history_id."""
        try:
            results = (
                self.service.users()
                .history()
                .list(
                    userId="me",
                    startHistoryId=history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                )
                .execute()
            )

            message_ids = set()
            for history in results.get("history", []):
                for msg_added in history.get("messagesAdded", []):
                    message_ids.add(msg_added["message"]["id"])

            # Limit results
            message_ids = list(message_ids)[:max_results]

            emails = []
            for mid in message_ids:
                try:
                    email = self._get_message_details(mid)
                    if email:
                        emails.append(email)
                except Exception as e:
                    logger.warning(f"Failed to fetch message {mid}: {e}")

            return emails

        except HttpError as e:
            if e.resp.status == 404:
                # History ID too old, do full fetch
                logger.warning("History ID expired, doing full fetch")
                return self._fetch_recent_emails(max_results)
            raise

    def _get_message_details(self, message_id: str) -> Optional[EmailMessage]:
        """Get full details of a single message."""
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            headers = {
                h["name"].lower(): h["value"] for h in msg["payload"]["headers"]
            }

            # Parse sender
            from_header = headers.get("from", "")
            sender_name, sender_email = self._parse_from_header(from_header)

            # Parse date
            date_str = headers.get("date", "")
            received_at = self._parse_date(date_str)

            # Get body text
            body_text = self._extract_body_text(msg["payload"])

            return EmailMessage(
                message_id=msg["id"],
                thread_id=msg["threadId"],
                sender_email=sender_email,
                sender_name=sender_name,
                subject=headers.get("subject", "(No Subject)"),
                snippet=msg.get("snippet", ""),
                body_text=body_text[:2000],  # Limit for Claude context
                received_at=received_at,
                labels=msg.get("labelIds", []),
            )

        except HttpError as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            return None

    def _parse_from_header(self, from_header: str) -> tuple[Optional[str], str]:
        """Parse 'Name <email>' format."""
        match = re.match(r'^"?([^"<]*)"?\s*<?([^>]+)>?$', from_header.strip())
        if match:
            name = match.group(1).strip() or None
            email = match.group(2).strip()
            return name, email
        return None, from_header.strip()

    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date header."""
        try:
            return parsedate_to_datetime(date_str)
        except Exception:
            return datetime.now(timezone.utc)

    def _extract_body_text(self, payload: dict[str, Any]) -> str:
        """Extract plain text body from message payload."""
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="ignore"
                        )
                # Recurse for multipart
                text = self._extract_body_text(part)
                if text:
                    return text

        return ""

    def get_user_email(self) -> str:
        """Get the email address of the authenticated user."""
        profile = self.service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")
