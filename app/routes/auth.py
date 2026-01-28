"""Gmail OAuth2 authentication routes."""

import os

# MUST be set before importing oauthlib
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

import logging

from flask import Blueprint, flash, g, redirect, request, session, url_for
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from ..config import get_config
from ..models.gmail_account import GmailAccount

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
]


def get_oauth_flow(config) -> Flow:
    """Create OAuth flow from configuration."""
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=config.GOOGLE_REDIRECT_URI,
    )


@auth_bp.route("/connect")
def connect():
    """Initiate OAuth flow to connect a Gmail account."""
    config = get_config()

    # Check if we already have 3 accounts
    count = g.db.query(GmailAccount).filter(GmailAccount.is_active == True).count()
    if count >= 3:
        flash("Maximum of 3 Gmail accounts allowed. Disconnect one first.", "error")
        return redirect(url_for("dashboard.accounts"))

    flow = get_oauth_flow(config)

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",  # Force consent to get refresh token
    )

    session["oauth_state"] = state
    return redirect(authorization_url)


@auth_bp.route("/callback")
def callback():
    """Handle OAuth callback and store credentials."""
    config = get_config()

    # Check for error
    error = request.args.get("error")
    if error:
        flash(f"Authorization failed: {error}", "error")
        return redirect(url_for("dashboard.accounts"))

    # Verify state
    state = request.args.get("state")
    if state != session.get("oauth_state"):
        flash("Invalid OAuth state. Please try again.", "error")
        return redirect(url_for("dashboard.accounts"))

    try:
        # Manually exchange code for tokens (bypasses scope check)
        import requests as http_requests

        code = request.args.get("code")
        token_response = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": config.GOOGLE_CLIENT_ID,
                "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": config.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_response.json()

        if "error" in token_data:
            raise Exception(f"Token error: {token_data.get('error_description', token_data['error'])}")

        credentials = Credentials(
            token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
        )

        # Get user email
        oauth2_service = build("oauth2", "v2", credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        email = user_info.get("email")
        display_name = user_info.get("name")

        if not email:
            flash("Could not retrieve email from Google. Please try again.", "error")
            return redirect(url_for("dashboard.accounts"))

        # Check for existing account
        existing = g.db.query(GmailAccount).filter(GmailAccount.email == email).first()

        if existing:
            # Update existing account
            existing.access_token = credentials.token
            if credentials.refresh_token:
                existing.refresh_token = credentials.refresh_token
            existing.token_expiry = credentials.expiry
            existing.display_name = display_name
            existing.is_active = True
            existing.last_history_id = None  # Reset for fresh sync
            flash(f"Updated credentials for {email}", "success")
            logger.info(f"Updated credentials for {email}")
        else:
            # Check limit again (race condition protection)
            count = (
                g.db.query(GmailAccount).filter(GmailAccount.is_active == True).count()
            )
            if count >= 3:
                flash("Maximum of 3 Gmail accounts allowed.", "error")
                return redirect(url_for("dashboard.accounts"))

            # Create new account
            account = GmailAccount(
                email=email,
                display_name=display_name,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                token_expiry=credentials.expiry,
            )
            g.db.add(account)
            flash(f"Connected {email}", "success")
            logger.info(f"Connected new account: {email}")

        g.db.commit()

    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        flash(f"Failed to connect account: {str(e)}", "error")

    # Clear session state
    session.pop("oauth_state", None)

    return redirect(url_for("dashboard.accounts"))


@auth_bp.route("/disconnect/<int:account_id>", methods=["POST"])
def disconnect(account_id: int):
    """Disconnect a Gmail account."""
    account = g.db.query(GmailAccount).get(account_id)

    if account:
        # Soft delete - just mark as inactive
        account.is_active = False
        g.db.commit()
        flash(f"Disconnected {account.email}", "success")
        logger.info(f"Disconnected account: {account.email}")
    else:
        flash("Account not found", "error")

    return redirect(url_for("dashboard.accounts"))


@auth_bp.route("/delete/<int:account_id>", methods=["POST"])
def delete(account_id: int):
    """Permanently delete a Gmail account and its data."""
    account = g.db.query(GmailAccount).get(account_id)

    if account:
        email = account.email
        g.db.delete(account)
        g.db.commit()
        flash(f"Deleted {email} and all associated data", "success")
        logger.info(f"Deleted account: {email}")
    else:
        flash("Account not found", "error")

    return redirect(url_for("dashboard.accounts"))
