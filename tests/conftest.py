"""Pytest fixtures for testing."""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set test environment before importing app
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"
os.environ["PUSHOVER_USER_KEY"] = "test-pushover-user"
os.environ["PUSHOVER_API_TOKEN"] = "test-pushover-token"

from app import create_app
from app.models.database import Base


@pytest.fixture
def app():
    """Create application for testing."""
    application = create_app(testing=True)
    yield application


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_gmail_service(mocker):
    """Mock Gmail service."""
    mock = mocker.patch("app.services.gmail_service.GmailService")
    return mock


@pytest.fixture
def mock_claude(mocker):
    """Mock Claude analyzer."""
    from app.services.claude_analyzer import ImportanceAnalysis

    mock = mocker.patch("app.services.claude_analyzer.ClaudeAnalyzer")
    mock.return_value.analyze_email.return_value = ImportanceAnalysis(
        score=0.8,
        reason="Important financial document",
        category="important",
        suggested_action="Review immediately",
    )
    return mock


@pytest.fixture
def mock_pushover(mocker):
    """Mock Pushover service."""
    from app.services.pushover_service import NotificationResult

    mock = mocker.patch("app.services.pushover_service.PushoverService")
    mock.return_value.send_notification.return_value = NotificationResult(success=True)
    mock.return_value.send_important_email_alert.return_value = NotificationResult(
        success=True
    )
    return mock
