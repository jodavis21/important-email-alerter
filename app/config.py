"""Configuration management for Important Email Alerter."""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


@dataclass
class Config:
    """Application configuration loaded from environment variables."""

    # Required fields (no defaults) - must come first
    SECRET_KEY: str
    DATABASE_URL: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    ANTHROPIC_API_KEY: str
    PUSHOVER_USER_KEY: str
    PUSHOVER_API_TOKEN: str

    # Optional fields (with defaults)
    DEBUG: bool = False
    CLAUDE_MODEL: str = "claude-3-haiku-20240307"
    IMPORTANCE_THRESHOLD: float = 0.7
    CHECK_INTERVAL_MINUTES: int = 15
    MAX_EMAILS_PER_CHECK: int = 50

    # Digest mode settings
    DIGEST_ENABLED: bool = True
    DIGEST_THRESHOLD_LOW: float = 0.5   # Minimum score for digest (emails below this are ignored)
    DIGEST_THRESHOLD_HIGH: float = 0.69  # Maximum score for digest (above this = immediate notification)
    DIGEST_HOUR: int = 8  # Hour to send daily digest (24h format, e.g., 8 = 8 AM)

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod"),
            DEBUG=os.environ.get("DEBUG", "false").lower() == "true",
            DATABASE_URL=os.environ.get("DATABASE_URL", ""),
            GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID", ""),
            GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            GOOGLE_REDIRECT_URI=os.environ.get(
                "GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/callback"
            ),
            ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY", ""),
            CLAUDE_MODEL=os.environ.get("CLAUDE_MODEL", "claude-3-haiku-20240307"),
            PUSHOVER_USER_KEY=os.environ.get("PUSHOVER_USER_KEY", ""),
            PUSHOVER_API_TOKEN=os.environ.get("PUSHOVER_API_TOKEN", ""),
            IMPORTANCE_THRESHOLD=float(
                os.environ.get("IMPORTANCE_THRESHOLD", "0.7")
            ),
            CHECK_INTERVAL_MINUTES=int(
                os.environ.get("CHECK_INTERVAL_MINUTES", "15")
            ),
            MAX_EMAILS_PER_CHECK=int(os.environ.get("MAX_EMAILS_PER_CHECK", "50")),
            DIGEST_ENABLED=os.environ.get("DIGEST_ENABLED", "true").lower() == "true",
            DIGEST_THRESHOLD_LOW=float(os.environ.get("DIGEST_THRESHOLD_LOW", "0.5")),
            DIGEST_THRESHOLD_HIGH=float(os.environ.get("DIGEST_THRESHOLD_HIGH", "0.69")),
            DIGEST_HOUR=int(os.environ.get("DIGEST_HOUR", "8")),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of missing required fields."""
        missing = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.GOOGLE_CLIENT_ID:
            missing.append("GOOGLE_CLIENT_ID")
        if not self.GOOGLE_CLIENT_SECRET:
            missing.append("GOOGLE_CLIENT_SECRET")
        if not self.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        if not self.PUSHOVER_USER_KEY:
            missing.append("PUSHOVER_USER_KEY")
        if not self.PUSHOVER_API_TOKEN:
            missing.append("PUSHOVER_API_TOKEN")
        return missing


# Singleton config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get application configuration (singleton)."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset config singleton (useful for testing)."""
    global _config
    _config = None
