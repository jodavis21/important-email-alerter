#!/usr/bin/env python3
"""Initialize the database schema.

Run this script to create all database tables.

Usage:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_config
from app.models.database import init_db, get_engine


def main():
    """Initialize the database."""
    config = get_config()

    if not config.DATABASE_URL:
        print("ERROR: DATABASE_URL not set in environment")
        print("Please copy .env.example to .env and configure it")
        sys.exit(1)

    print(f"Initializing database...")
    print(f"  URL: {config.DATABASE_URL[:50]}...")

    try:
        # Test connection
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        print("  Connection: OK")

        # Create tables
        init_db()
        print("  Tables: Created")

        print("\nDatabase initialization complete!")

    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
