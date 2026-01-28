"""Pushover notification service."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    """Result of sending a notification."""

    success: bool
    receipt: Optional[str] = None  # For emergency priority
    error: Optional[str] = None


class PushoverService:
    """Send push notifications via Pushover."""

    API_URL = "https://api.pushover.net/1/messages.json"

    # Priority levels
    PRIORITY_LOWEST = -2
    PRIORITY_LOW = -1
    PRIORITY_NORMAL = 0
    PRIORITY_HIGH = 1
    PRIORITY_EMERGENCY = 2

    # Sound options
    SOUND_DEFAULT = "pushover"
    SOUND_BIKE = "bike"
    SOUND_BUGLE = "bugle"
    SOUND_CASH_REGISTER = "cashregister"
    SOUND_CLASSICAL = "classical"
    SOUND_COSMIC = "cosmic"
    SOUND_FALLING = "falling"
    SOUND_GAMELAN = "gamelan"
    SOUND_INCOMING = "incoming"
    SOUND_INTERMISSION = "intermission"
    SOUND_MAGIC = "magic"
    SOUND_MECHANICAL = "mechanical"
    SOUND_NONE = "none"
    SOUND_PERSISTENT = "persistent"
    SOUND_PIANO_BAR = "pianobar"
    SOUND_SIREN = "siren"
    SOUND_SPACE_ALARM = "spacealarm"
    SOUND_TUGBOAT = "tugboat"
    SOUND_ALIEN = "alien"
    SOUND_CLIMB = "climb"
    SOUND_ECHO = "echo"
    SOUND_UPDOWN = "updown"

    def __init__(self, user_key: str, api_token: str):
        """Initialize Pushover service."""
        self.user_key = user_key
        self.api_token = api_token

    def send_notification(
        self,
        title: str,
        message: str,
        priority: int = 0,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
        sound: str = "pushover",
        html: bool = False,
    ) -> NotificationResult:
        """Send a push notification.

        Args:
            title: Notification title (max 250 chars)
            message: Notification body (max 1024 chars)
            priority: -2 to 2 (see PRIORITY_* constants)
            url: Optional URL to include
            url_title: Display text for URL
            sound: Notification sound name
            html: Enable HTML formatting in message

        Returns:
            NotificationResult with success status
        """
        payload = {
            "token": self.api_token,
            "user": self.user_key,
            "title": title[:250],  # Pushover limit
            "message": message[:1024],  # Pushover limit
            "priority": priority,
            "sound": sound,
        }

        if html:
            payload["html"] = 1

        if url:
            payload["url"] = url[:512]
            if url_title:
                payload["url_title"] = url_title[:100]

        # Emergency priority requires retry/expire
        if priority == self.PRIORITY_EMERGENCY:
            payload["retry"] = 60  # Retry every 60 seconds
            payload["expire"] = 3600  # Stop after 1 hour

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.API_URL, data=payload)
                response.raise_for_status()

                result = response.json()
                return NotificationResult(
                    success=result.get("status") == 1,
                    receipt=result.get("receipt"),
                )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}"
            try:
                error_data = e.response.json()
                if "errors" in error_data:
                    error_msg = ", ".join(error_data["errors"])
            except Exception:
                pass

            logger.error(f"Pushover HTTP error: {error_msg}")
            return NotificationResult(success=False, error=error_msg)

        except httpx.TimeoutException:
            logger.error("Pushover request timed out")
            return NotificationResult(success=False, error="Request timed out")

        except Exception as e:
            logger.error(f"Pushover error: {e}")
            return NotificationResult(success=False, error=str(e))

    def send_important_email_alert(
        self,
        sender: str,
        subject: str,
        importance_reason: str,
        account_email: str,
        importance_score: float = 0.7,
        deadline_date: Optional[datetime] = None,
        deadline_text: Optional[str] = None,
    ) -> NotificationResult:
        """Send alert for important email.

        Args:
            sender: Email sender name/address
            subject: Email subject
            importance_reason: Why this email is important
            account_email: Which Gmail account received it
            importance_score: 0.0-1.0 importance score
            deadline_date: Optional detected deadline date
            deadline_text: Optional human-readable deadline description
        """
        # Determine priority based on score
        if importance_score >= 0.9:
            priority = self.PRIORITY_HIGH
            sound = self.SOUND_SIREN
        elif importance_score >= 0.8:
            priority = self.PRIORITY_HIGH
            sound = self.SOUND_INCOMING
        else:
            priority = self.PRIORITY_NORMAL
            sound = self.SOUND_DEFAULT

        # Truncate sender for title
        sender_short = sender[:40] + "..." if len(sender) > 40 else sender
        title = f"Important: {sender_short}"

        # Build message with HTML formatting
        message = (
            f"<b>Subject:</b> {subject[:200]}\n\n"
            f"<b>Account:</b> {account_email}\n\n"
            f"<b>Why important:</b> {importance_reason}"
        )

        # Add deadline warning if detected
        if deadline_date and deadline_text:
            days_until = (deadline_date.date() - datetime.now().date()).days
            if days_until < 0:
                deadline_warning = f"\n\n<b>OVERDUE:</b> {deadline_text} ({abs(days_until)} days ago!)"
            elif days_until == 0:
                deadline_warning = f"\n\n<b>DUE TODAY:</b> {deadline_text}"
            elif days_until <= 3:
                deadline_warning = f"\n\n<b>DEADLINE:</b> {deadline_text} ({days_until} days!)"
            else:
                deadline_warning = f"\n\n<b>Deadline:</b> {deadline_text} ({days_until} days)"
            message += deadline_warning

        return self.send_notification(
            title=title,
            message=message,
            priority=priority,
            sound=sound,
            html=True,
        )

    def send_test_notification(self) -> NotificationResult:
        """Send a test notification to verify configuration."""
        return self.send_notification(
            title="Email Alerter Test",
            message="If you received this, your Pushover configuration is working correctly!",
            priority=self.PRIORITY_NORMAL,
            sound=self.SOUND_DEFAULT,
        )
