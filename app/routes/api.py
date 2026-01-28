"""API routes for Important Email Alerter."""

import logging

from flask import Blueprint, g, jsonify, request

from ..config import get_config
from ..models.gmail_account import GmailAccount
from ..models.learned_patterns import LearnedPattern
from ..models.processed_email import ProcessedEmail
from ..models.user_feedback import UserFeedback
from ..services.claude_analyzer import ClaudeAnalyzer
from ..services.digest_service import DigestService
from ..services.email_processor import EmailProcessor
from ..services.pushover_service import PushoverService

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/check-now", methods=["POST"])
def check_now():
    """Manually trigger email check for all accounts.

    This endpoint is called by Cloud Scheduler every 15 minutes,
    or can be triggered manually from the dashboard.
    """
    config = get_config()

    # Validate required configuration
    missing = config.validate()
    if missing:
        return jsonify({
            "success": False,
            "error": f"Missing configuration: {', '.join(missing)}",
        }), 500

    try:
        # Create services
        claude = ClaudeAnalyzer(
            api_key=config.ANTHROPIC_API_KEY,
            model=config.CLAUDE_MODEL,
            db_session=g.db,  # Pass db for learned patterns lookup
        )

        pushover = PushoverService(
            user_key=config.PUSHOVER_USER_KEY,
            api_token=config.PUSHOVER_API_TOKEN,
        )

        processor = EmailProcessor(
            db_session=g.db,
            claude_analyzer=claude,
            pushover_service=pushover,
            google_client_id=config.GOOGLE_CLIENT_ID,
            google_client_secret=config.GOOGLE_CLIENT_SECRET,
            importance_threshold=config.IMPORTANCE_THRESHOLD,
            max_emails_per_check=config.MAX_EMAILS_PER_CHECK,
            digest_enabled=config.DIGEST_ENABLED,
            digest_threshold_low=config.DIGEST_THRESHOLD_LOW,
            digest_threshold_high=config.DIGEST_THRESHOLD_HIGH,
        )

        # Process all accounts
        summary = processor.process_all_accounts()

        logger.info(
            f"Email check complete: {summary.total_emails_fetched} fetched, "
            f"{summary.total_notifications_sent} notifications sent"
        )

        return jsonify({
            "success": True,
            "summary": summary.to_dict(),
        })

    except Exception as e:
        logger.error(f"Email check failed: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_bp.route("/stats")
def stats():
    """Get processing statistics."""
    from sqlalchemy import func

    total_processed = g.db.query(func.count(ProcessedEmail.id)).scalar() or 0
    notifications_sent = (
        g.db.query(func.count(ProcessedEmail.id))
        .filter(ProcessedEmail.notification_sent == True)
        .scalar()
        or 0
    )
    active_accounts = (
        g.db.query(func.count(GmailAccount.id))
        .filter(GmailAccount.is_active == True)
        .scalar()
        or 0
    )

    return jsonify({
        "total_processed": total_processed,
        "notifications_sent": notifications_sent,
        "active_accounts": active_accounts,
    })


@api_bp.route("/recent-emails")
def recent_emails():
    """Get recently processed emails."""
    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)  # Cap at 100

    emails = (
        g.db.query(ProcessedEmail)
        .order_by(ProcessedEmail.processed_at.desc())
        .limit(limit)
        .all()
    )

    return jsonify({
        "emails": [e.to_dict() for e in emails],
    })


@api_bp.route("/test-pushover", methods=["POST"])
def test_pushover():
    """Send a test notification to verify Pushover configuration."""
    config = get_config()

    if not config.PUSHOVER_USER_KEY or not config.PUSHOVER_API_TOKEN:
        return jsonify({
            "success": False,
            "error": "Pushover not configured",
        }), 400

    try:
        pushover = PushoverService(
            user_key=config.PUSHOVER_USER_KEY,
            api_token=config.PUSHOVER_API_TOKEN,
        )

        result = pushover.send_test_notification()

        return jsonify({
            "success": result.success,
            "error": result.error,
        })

    except Exception as e:
        logger.error(f"Test notification failed: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_bp.route("/health")
def health():
    """Health check endpoint for Cloud Run."""
    return jsonify({"status": "healthy"})


@api_bp.route("/send-digest", methods=["POST"])
def send_digest():
    """Send the daily digest of notable emails.

    This endpoint is called by Cloud Scheduler at the configured digest hour,
    or can be triggered manually.
    """
    config = get_config()

    if not config.DIGEST_ENABLED:
        return jsonify({
            "success": False,
            "error": "Digest mode is disabled",
        }), 400

    if not config.PUSHOVER_USER_KEY or not config.PUSHOVER_API_TOKEN:
        return jsonify({
            "success": False,
            "error": "Pushover not configured",
        }), 400

    try:
        pushover = PushoverService(
            user_key=config.PUSHOVER_USER_KEY,
            api_token=config.PUSHOVER_API_TOKEN,
        )

        digest_service = DigestService(
            db_session=g.db,
            pushover_service=pushover,
        )

        result = digest_service.send_digest()

        logger.info(f"Digest endpoint called: {result}")

        return jsonify(result)

    except Exception as e:
        logger.error(f"Digest send failed: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_bp.route("/digest-stats")
def digest_stats():
    """Get digest statistics."""
    config = get_config()

    pushover = PushoverService(
        user_key=config.PUSHOVER_USER_KEY,
        api_token=config.PUSHOVER_API_TOKEN,
    )

    digest_service = DigestService(
        db_session=g.db,
        pushover_service=pushover,
    )

    stats = digest_service.get_digest_stats()
    stats["digest_enabled"] = config.DIGEST_ENABLED
    stats["digest_hour"] = config.DIGEST_HOUR
    stats["digest_threshold_low"] = config.DIGEST_THRESHOLD_LOW
    stats["digest_threshold_high"] = config.DIGEST_THRESHOLD_HIGH

    return jsonify(stats)


@api_bp.route("/accounts/<int:account_id>/emails")
def account_emails(account_id: int):
    """Get processed emails for a specific account."""
    limit = request.args.get("limit", 20, type=int)
    limit = min(limit, 100)

    account = g.db.query(GmailAccount).get(account_id)
    if not account:
        return jsonify({"error": "Account not found"}), 404

    emails = (
        g.db.query(ProcessedEmail)
        .filter(ProcessedEmail.gmail_account_id == account_id)
        .order_by(ProcessedEmail.processed_at.desc())
        .limit(limit)
        .all()
    )

    return jsonify({
        "account": account.to_dict(),
        "emails": [e.to_dict() for e in emails],
    })


@api_bp.route("/feedback/<int:email_id>", methods=["POST"])
def submit_feedback(email_id: int):
    """Submit feedback for an email's importance rating.

    Mark an email as "not important" to train the system over time.
    Query param: type=not_important or type=important
    """
    feedback_type = request.args.get("type", "not_important")

    if feedback_type not in ("not_important", "important"):
        return jsonify({
            "success": False,
            "error": "Invalid feedback type. Use 'not_important' or 'important'",
        }), 400

    # Get the processed email
    email = g.db.query(ProcessedEmail).get(email_id)
    if not email:
        return jsonify({"error": "Email not found"}), 404

    try:
        # Record the feedback
        feedback = UserFeedback(
            processed_email_id=email_id,
            feedback_type=feedback_type,
            original_score=email.importance_score,
        )
        g.db.add(feedback)

        # Determine adjustment based on feedback type
        # "not_important" = negative adjustment, "important" = positive adjustment
        if feedback_type == "not_important":
            adjustment = -0.15  # Reduce future scores
        else:
            adjustment = 0.10  # Boost future scores

        # Learn from sender email
        sender_pattern = LearnedPattern.record_feedback(
            g.db, "sender", email.sender_email, adjustment
        )

        # Learn from sender domain
        if "@" in email.sender_email:
            domain = email.sender_email.split("@")[-1]
            # Domain gets half the adjustment (less specific)
            domain_pattern = LearnedPattern.record_feedback(
                g.db, "domain", domain, adjustment * 0.5
            )

        g.db.commit()

        logger.info(
            f"Feedback recorded: {feedback_type} for email from {email.sender_email} "
            f"(original score: {email.importance_score})"
        )

        return jsonify({
            "success": True,
            "message": f"Feedback recorded. Future emails from {email.sender_email} will be adjusted.",
            "sender_adjustment": float(sender_pattern.score_adjustment),
        })

    except Exception as e:
        g.db.rollback()
        logger.error(f"Failed to record feedback: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@api_bp.route("/learned-patterns")
def learned_patterns():
    """Get all learned patterns from user feedback."""
    patterns = (
        g.db.query(LearnedPattern)
        .order_by(LearnedPattern.feedback_count.desc())
        .all()
    )

    return jsonify({
        "patterns": [p.to_dict() for p in patterns],
    })


@api_bp.route("/feedback-stats")
def feedback_stats():
    """Get feedback statistics."""
    from sqlalchemy import func

    total_feedback = g.db.query(func.count(UserFeedback.id)).scalar() or 0
    not_important_count = (
        g.db.query(func.count(UserFeedback.id))
        .filter(UserFeedback.feedback_type == "not_important")
        .scalar()
        or 0
    )
    important_count = (
        g.db.query(func.count(UserFeedback.id))
        .filter(UserFeedback.feedback_type == "important")
        .scalar()
        or 0
    )
    learned_patterns_count = g.db.query(func.count(LearnedPattern.id)).scalar() or 0

    return jsonify({
        "total_feedback": total_feedback,
        "not_important_count": not_important_count,
        "important_count": important_count,
        "learned_patterns_count": learned_patterns_count,
    })
