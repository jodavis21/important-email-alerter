#!/usr/bin/env python3
"""Standalone email checker script.

This script can be run independently to check emails.
Useful for testing or running via cron/Cloud Scheduler.

Usage:
    python scripts/check_emails.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

from app.config import get_config
from app.models.database import get_db_session
from app.services.claude_analyzer import ClaudeAnalyzer
from app.services.email_processor import EmailProcessor
from app.services.pushover_service import PushoverService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Run email check for all accounts."""
    config = get_config()

    # Validate configuration
    missing = config.validate()
    if missing:
        logger.error(f"Missing configuration: {', '.join(missing)}")
        sys.exit(1)

    logger.info("Starting email check...")

    try:
        # Create services
        claude = ClaudeAnalyzer(
            api_key=config.ANTHROPIC_API_KEY,
            model=config.CLAUDE_MODEL,
        )

        pushover = PushoverService(
            user_key=config.PUSHOVER_USER_KEY,
            api_token=config.PUSHOVER_API_TOKEN,
        )

        # Process emails within database session
        with get_db_session() as db:
            processor = EmailProcessor(
                db_session=db,
                claude_analyzer=claude,
                pushover_service=pushover,
                google_client_id=config.GOOGLE_CLIENT_ID,
                google_client_secret=config.GOOGLE_CLIENT_SECRET,
                importance_threshold=config.IMPORTANCE_THRESHOLD,
                max_emails_per_check=config.MAX_EMAILS_PER_CHECK,
            )

            summary = processor.process_all_accounts()

        # Log summary
        logger.info(
            f"Email check complete: "
            f"{summary.accounts_processed} accounts, "
            f"{summary.total_emails_fetched} emails fetched, "
            f"{summary.total_emails_analyzed} analyzed, "
            f"{summary.total_notifications_sent} notifications sent"
        )

        if summary.errors:
            for error in summary.errors:
                logger.error(f"Error: {error}")

    except Exception as e:
        logger.error(f"Email check failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
