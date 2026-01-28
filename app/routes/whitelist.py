"""Whitelist management routes."""

import logging

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..config import get_config
from ..models.whitelist import WhitelistEntry
from ..services.whitelist_parser import parse_whitelist_input

logger = logging.getLogger(__name__)

whitelist_bp = Blueprint("whitelist", __name__, url_prefix="/whitelist")


@whitelist_bp.route("/")
def index():
    """View whitelist entries."""
    entries = (
        g.db.query(WhitelistEntry)
        .filter(WhitelistEntry.is_active == True)
        .order_by(WhitelistEntry.created_at.desc())
        .all()
    )

    # Separate by type
    email_entries = [e for e in entries if e.entry_type == "email"]
    domain_entries = [e for e in entries if e.entry_type == "domain"]

    return render_template(
        "whitelist.html",
        email_entries=email_entries,
        domain_entries=domain_entries,
        total_count=len(entries),
    )


@whitelist_bp.route("/add", methods=["POST"])
def add():
    """Add a new whitelist entry using AI to parse natural language input."""
    raw_value = request.form.get("value", "").strip()
    notes = request.form.get("notes", "").strip()

    # Validate
    if not raw_value:
        flash("Please enter an email address or domain.", "error")
        return redirect(url_for("whitelist.index"))

    # Use AI to parse the input and extract emails/domains
    config = get_config()
    parsed_entries = parse_whitelist_input(config.ANTHROPIC_API_KEY, raw_value)

    if not parsed_entries:
        flash("Could not parse any valid emails or domains from input.", "error")
        return redirect(url_for("whitelist.index"))

    added = 0
    skipped = 0

    for parsed in parsed_entries:
        entry_type = parsed.entry_type
        value = parsed.value

        # Check for duplicate
        existing = (
            g.db.query(WhitelistEntry)
            .filter(
                WhitelistEntry.entry_type == entry_type,
                WhitelistEntry.value == value,
            )
            .first()
        )

        if existing:
            if existing.is_active:
                skipped += 1
            else:
                # Reactivate
                existing.is_active = True
                existing.notes = notes or existing.notes
                g.db.commit()
                flash(f"Reactivated '{value}' in whitelist.", "success")
                logger.info(f"Reactivated whitelist entry: {entry_type}:{value}")
                added += 1
            continue

        # Create new entry
        entry = WhitelistEntry(
            entry_type=entry_type,
            value=value,
            notes=notes or None,
        )
        g.db.add(entry)
        added += 1
        logger.info(f"Added whitelist entry: {entry_type}:{value}")

    g.db.commit()

    if added:
        flash(f"Added {added} {'entry' if added == 1 else 'entries'} to whitelist.", "success")
    if skipped:
        flash(f"Skipped {skipped} duplicate or invalid {'entry' if skipped == 1 else 'entries'}.", "warning")

    return redirect(url_for("whitelist.index"))


@whitelist_bp.route("/delete/<int:entry_id>", methods=["POST"])
def delete(entry_id: int):
    """Remove a whitelist entry (soft delete)."""
    entry = g.db.query(WhitelistEntry).get(entry_id)

    if entry:
        entry.is_active = False
        g.db.commit()
        flash(f"Removed '{entry.value}' from whitelist.", "success")
        logger.info(f"Removed whitelist entry: {entry.entry_type}:{entry.value}")
    else:
        flash("Entry not found.", "error")

    return redirect(url_for("whitelist.index"))


@whitelist_bp.route("/update/<int:entry_id>", methods=["POST"])
def update(entry_id: int):
    """Update a whitelist entry's notes."""
    entry = g.db.query(WhitelistEntry).get(entry_id)

    if entry:
        notes = request.form.get("notes", "").strip()
        entry.notes = notes or None
        g.db.commit()
        flash(f"Updated notes for '{entry.value}'.", "success")
    else:
        flash("Entry not found.", "error")

    return redirect(url_for("whitelist.index"))


@whitelist_bp.route("/bulk-add", methods=["POST"])
def bulk_add():
    """Add multiple whitelist entries at once using AI to parse natural language."""
    values_text = request.form.get("values", "").strip()

    if not values_text:
        flash("Please enter at least one value.", "error")
        return redirect(url_for("whitelist.index"))

    # Use AI to parse the input and extract emails/domains
    config = get_config()
    parsed_entries = parse_whitelist_input(config.ANTHROPIC_API_KEY, values_text)

    if not parsed_entries:
        flash("Could not parse any valid emails or domains from input.", "error")
        return redirect(url_for("whitelist.index"))

    added = 0
    skipped = 0

    for parsed in parsed_entries:
        entry_type = parsed.entry_type
        value = parsed.value

        # Check for duplicate
        existing = (
            g.db.query(WhitelistEntry)
            .filter(
                WhitelistEntry.entry_type == entry_type,
                WhitelistEntry.value == value,
                WhitelistEntry.is_active == True,
            )
            .first()
        )

        if existing:
            skipped += 1
            continue

        # Create entry
        entry = WhitelistEntry(entry_type=entry_type, value=value)
        g.db.add(entry)
        added += 1

    g.db.commit()

    if added:
        flash(f"Added {added} entries to whitelist.", "success")
        logger.info(f"Bulk added {added} whitelist entries")
    if skipped:
        flash(f"Skipped {skipped} duplicates or invalid entries.", "warning")

    return redirect(url_for("whitelist.index"))
