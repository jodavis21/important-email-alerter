"""Flask application factory for Important Email Alerter."""

import os

# MUST set before ANY imports that use oauthlib
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

import logging

from flask import Flask, g

from .config import get_config
from .models.database import close_db, get_db, init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app(testing: bool = False) -> Flask:
    """Create and configure the Flask application.

    Args:
        testing: If True, configure for testing

    Returns:
        Configured Flask application
    """
    app = Flask(__name__)

    # Load configuration
    config = get_config()
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["DEBUG"] = config.DEBUG if not testing else True

    # Store config in app
    app.config["APP_CONFIG"] = config

    # Database setup
    @app.before_request
    def before_request():
        """Set up database session for each request."""
        g.db = get_db()

    @app.teardown_request
    def teardown_request(exception=None):
        """Close database session after each request."""
        db = g.pop("db", None)
        if db is not None:
            if exception:
                db.rollback()
            db.close()

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.whitelist import whitelist_bp
    from .routes.blacklist import blacklist_bp
    from .routes.api import api_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(whitelist_bp)
    app.register_blueprint(blacklist_bp)
    app.register_blueprint(api_bp)

    # Initialize database on first request
    with app.app_context():
        init_db()
        logger.info("Database initialized")

    # Log startup
    logger.info(f"Email Alerter started (debug={app.config['DEBUG']})")

    return app


def get_app_config():
    """Get the application configuration from Flask app context."""
    from flask import current_app
    return current_app.config.get("APP_CONFIG", get_config())
