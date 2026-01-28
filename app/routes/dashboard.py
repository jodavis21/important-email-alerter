"""Dashboard routes for Important Email Alerter."""

import logging

from flask import Blueprint, g, render_template

from ..models.gmail_account import GmailAccount
from ..models.processed_email import ProcessedEmail
from ..models.whitelist import WhitelistEntry

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    """Main dashboard with stats."""
    # Get statistics
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
    whitelist_count = (
        g.db.query(func.count(WhitelistEntry.id))
        .filter(WhitelistEntry.is_active == True)
        .scalar()
        or 0
    )

    # Get recent emails
    recent_emails = (
        g.db.query(ProcessedEmail)
        .order_by(ProcessedEmail.processed_at.desc())
        .limit(10)
        .all()
    )

    # Get accounts for last check time
    accounts = (
        g.db.query(GmailAccount).filter(GmailAccount.is_active == True).all()
    )

    return render_template(
        "dashboard.html",
        stats={
            "total_processed": total_processed,
            "notifications_sent": notifications_sent,
            "active_accounts": active_accounts,
            "whitelist_count": whitelist_count,
        },
        recent_emails=recent_emails,
        accounts=accounts,
    )


@dashboard_bp.route("/accounts")
def accounts():
    """Gmail accounts management page."""
    accounts = g.db.query(GmailAccount).all()

    # Separate active and inactive
    active_accounts = [a for a in accounts if a.is_active]
    inactive_accounts = [a for a in accounts if not a.is_active]

    return render_template(
        "accounts.html",
        active_accounts=active_accounts,
        inactive_accounts=inactive_accounts,
        can_add_more=len(active_accounts) < 3,
    )


@dashboard_bp.route("/history")
def history():
    """Email processing history page."""
    page = int(g.db.query(ProcessedEmail).count() > 0)

    # Get all processed emails with pagination
    emails = (
        g.db.query(ProcessedEmail)
        .order_by(ProcessedEmail.processed_at.desc())
        .limit(100)
        .all()
    )

    return render_template("history.html", emails=emails)
