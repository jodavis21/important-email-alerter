"""Claude Haiku integration for email importance analysis."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class ImportanceAnalysis:
    """Result of email importance analysis."""

    score: float  # 0.0 to 1.0
    reason: str
    category: str  # 'urgent', 'important', 'normal', 'low'
    suggested_action: str
    deadline_date: Optional[datetime] = None  # Extracted deadline if found
    deadline_text: Optional[str] = None  # Human-readable deadline description


class ClaudeAnalyzer:
    """Analyze email importance using Claude Haiku."""

    SYSTEM_PROMPT = """You are an email importance analyzer. Your job is to determine if an email requires immediate attention and should trigger a push notification to the user's phone.

Analyze the email and return a JSON response with:
- score: float from 0.0 (spam/unimportant) to 1.0 (critical/urgent)
- reason: brief explanation (1-2 sentences max)
- category: one of 'urgent', 'important', 'normal', 'low'
- suggested_action: what the recipient should do
- deadline: object with "date" (ISO format YYYY-MM-DD) and "text" (human description) OR null if no deadline

HIGH IMPORTANCE (0.7+) - NOTIFY immediately:
- Financial alerts: fraud alerts, unusual activity, payment due
- Government/legal: tax deadlines (CDTFA, IRS), legal notices, court documents
- Security alerts: password reset requests they didn't initiate, login from new device
- Account deactivation warnings (e.g., Google Voice asking to log in)
- Health/medical: appointment reminders, test results, urgent medical info
- Work emergencies from known colleagues
- Time-sensitive deadlines with real consequences
- Family/personal emergencies

MEDIUM IMPORTANCE (0.4-0.7):
- Work emails from colleagues (non-urgent)
- Appointment confirmations
- Shipping/delivery updates for important packages
- Account statements

LOW IMPORTANCE (0.3 or below) - DO NOT notify:
- Marketing/promotional emails
- Newsletters and digests
- Social media notifications
- Automated receipts (unless large amounts > $500)
- General announcements
- Cold outreach/sales emails
- Subscription updates

DEADLINE DETECTION:
- Look for phrases like "due by", "deadline", "must respond by", "expires on", "by [date]"
- Look for specific dates in various formats
- Return deadline as {"date": "2026-02-15", "text": "Tax filing due Feb 15"} or null if none

Be conservative - only high scores (0.7+) will trigger phone notifications that interrupt the user.

Respond ONLY with valid JSON, no other text or markdown formatting."""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307", db_session=None):
        """Initialize Claude analyzer.

        Args:
            api_key: Anthropic API key
            model: Model to use for analysis
            db_session: Optional SQLAlchemy session for learned patterns lookup
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.db_session = db_session

    def analyze_email(
        self,
        sender_email: str,
        sender_name: Optional[str],
        subject: str,
        body_snippet: str,
        is_whitelisted: bool = False,
    ) -> ImportanceAnalysis:
        """Analyze email importance.

        Args:
            sender_email: Sender's email address
            sender_name: Sender's display name
            subject: Email subject line
            body_snippet: First ~500 chars of email body
            is_whitelisted: Whether sender is on whitelist

        Returns:
            ImportanceAnalysis with score and reasoning
        """
        # Build context for Claude
        sender_display = (
            f"{sender_name} <{sender_email}>" if sender_name else sender_email
        )
        whitelist_note = (
            "\n\nNOTE: This sender is on the user's trusted whitelist - they have marked this sender as important."
            if is_whitelisted
            else ""
        )

        user_message = f"""Analyze this email for importance:

From: {sender_display}{whitelist_note}
Subject: {subject}

Body preview:
{body_snippet[:500]}

Return JSON with score (0.0-1.0), reason, category, suggested_action, and deadline (or null)."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )

            # Parse JSON response
            response_text = response.content[0].text.strip()

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                # Remove first and last lines (```json and ```)
                json_lines = []
                in_json = False
                for line in lines:
                    if line.startswith("```") and not in_json:
                        in_json = True
                        continue
                    elif line.startswith("```") and in_json:
                        break
                    elif in_json:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)

            result = json.loads(response_text)

            # Get base score
            score = float(result.get("score", 0.5))

            # Boost score for whitelisted senders
            if is_whitelisted:
                score = min(1.0, score + 0.15)  # Slight boost for trusted senders

            # Apply learned adjustments from user feedback
            if self.db_session:
                learned_adjustment = self._get_learned_adjustment(sender_email)
                if learned_adjustment != 0:
                    old_score = score
                    score = max(0.0, min(1.0, score + learned_adjustment))
                    logger.info(
                        f"Applied learned adjustment {learned_adjustment:+.2f} "
                        f"for {sender_email}: {old_score:.2f} -> {score:.2f}"
                    )

            # Parse deadline if present
            deadline_date = None
            deadline_text = None
            deadline_data = result.get("deadline")
            if deadline_data and isinstance(deadline_data, dict):
                deadline_text = deadline_data.get("text")
                date_str = deadline_data.get("date")
                if date_str:
                    try:
                        deadline_date = datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        logger.warning(f"Could not parse deadline date: {date_str}")

            return ImportanceAnalysis(
                score=score,
                reason=result.get("reason", "Unable to determine importance"),
                category=result.get("category", "normal"),
                suggested_action=result.get(
                    "suggested_action", "Review when convenient"
                ),
                deadline_date=deadline_date,
                deadline_text=deadline_text,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response: {e}")
            logger.error(f"Response was: {response_text}")
            # Default to medium importance on parse failure
            return ImportanceAnalysis(
                score=0.5 if not is_whitelisted else 0.65,
                reason="Analysis parsing failed - manual review recommended",
                category="normal",
                suggested_action="Manual review recommended",
            )
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Claude analysis: {e}")
            raise

    def _get_learned_adjustment(self, sender_email: str) -> float:
        """Get learned score adjustment for a sender.

        Args:
            sender_email: Email address to check

        Returns:
            Score adjustment (positive or negative)
        """
        if not self.db_session:
            return 0.0

        try:
            from ..models.learned_patterns import LearnedPattern

            return LearnedPattern.get_total_adjustment(self.db_session, sender_email)
        except Exception as e:
            logger.warning(f"Error getting learned adjustment: {e}")
            return 0.0

    def analyze_email_batch(
        self,
        emails: list[dict],
    ) -> list[ImportanceAnalysis]:
        """Analyze multiple emails (for future batch API support).

        Currently processes sequentially, but structured for future
        batch API integration which offers 50% cost savings.

        Args:
            emails: List of dicts with sender_email, sender_name, subject,
                   body_snippet, is_whitelisted keys

        Returns:
            List of ImportanceAnalysis results
        """
        results = []
        for email in emails:
            result = self.analyze_email(
                sender_email=email["sender_email"],
                sender_name=email.get("sender_name"),
                subject=email["subject"],
                body_snippet=email.get("body_snippet", ""),
                is_whitelisted=email.get("is_whitelisted", False),
            )
            results.append(result)
        return results
