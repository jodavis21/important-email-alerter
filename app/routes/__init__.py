"""Routes for Important Email Alerter."""

from .auth import auth_bp
from .dashboard import dashboard_bp
from .whitelist import whitelist_bp
from .api import api_bp

__all__ = ["auth_bp", "dashboard_bp", "whitelist_bp", "api_bp"]
