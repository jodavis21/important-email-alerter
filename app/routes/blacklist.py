"""Blacklist management routes."""

import logging

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..models.blacklist import BlacklistEntry

logger = logging.getLogger(__name__)

blacklist_bp = Blueprint("blacklist", __name__, url_prefix="/blacklist")


@blacklist_bp.route("/")
def index():
    """View blacklist entries."""
    entries = (
        g.db.query(BlacklistEntry)
        .filter(BlacklistEntry.is_active == True)
        .order_by(BlacklistEntry.created_at.desc())
        .all()
    )

    # Separate by type
    email_entries = [e for e in entries if e.entry_type == "email"]
    domain_entries = [e for e in entries if e.entry_type == "domain"]

    return render_template(
        "blacklist.html",
        email_entries=email_entries,
        domain_entries=domain_entries,
        total_count=len(entries),
    )


@blacklist_bp.route("/add", methods=["POST"])
def add():
    """Add a new blacklist entry."""
    entry_type = request.form.get("entry_type", "email")
    value = request.form.get("value", "").strip().lower()
    notes = request.form.get("notes", "").strip()

    # Validate
    if not value:
        flash("Please enter an email address or domain.", "error")
        return redirect(url_for("blacklist.index"))

    if entry_type not in ("email", "domain"):
        flash("Invalid entry type.", "error")
        return redirect(url_for("blacklist.index"))

    # Clean up domain (remove @ if present)
    if entry_type == "domain" and value.startswith("@"):
        value = value[1:]

    # Validate email format
    if entry_type == "email" and "@" not in value:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("blacklist.index"))

    # Check for duplicate
    existing = (
        g.db.query(BlacklistEntry)
        .filter(
            BlacklistEntry.entry_type == entry_type,
            BlacklistEntry.value == value,
        )
        .first()
    )

    if existing:
        if existing.is_active:
            flash(f"'{value}' is already in the blacklist.", "warning")
        else:
            # Reactivate
            existing.is_active = True
            existing.notes = notes or existing.notes
            g.db.commit()
            flash(f"Reactivated '{value}' in blacklist.", "success")
            logger.info(f"Reactivated blacklist entry: {entry_type}:{value}")
        return redirect(url_for("blacklist.index"))

    # Create new entry
    entry = BlacklistEntry(
        entry_type=entry_type,
        value=value,
        notes=notes or None,
    )
    g.db.add(entry)
    g.db.commit()

    flash(f"Added '{value}' to blacklist.", "success")
    logger.info(f"Added blacklist entry: {entry_type}:{value}")

    return redirect(url_for("blacklist.index"))


@blacklist_bp.route("/delete/<int:entry_id>", methods=["POST"])
def delete(entry_id: int):
    """Remove a blacklist entry (soft delete)."""
    entry = g.db.query(BlacklistEntry).get(entry_id)

    if entry:
        entry.is_active = False
        g.db.commit()
        flash(f"Removed '{entry.value}' from blacklist.", "success")
        logger.info(f"Removed blacklist entry: {entry.entry_type}:{entry.value}")
    else:
        flash("Entry not found.", "error")

    return redirect(url_for("blacklist.index"))


@blacklist_bp.route("/update/<int:entry_id>", methods=["POST"])
def update(entry_id: int):
    """Update a blacklist entry's notes."""
    entry = g.db.query(BlacklistEntry).get(entry_id)

    if entry:
        notes = request.form.get("notes", "").strip()
        entry.notes = notes or None
        g.db.commit()
        flash(f"Updated notes for '{entry.value}'.", "success")
    else:
        flash("Entry not found.", "error")

    return redirect(url_for("blacklist.index"))


@blacklist_bp.route("/bulk-add", methods=["POST"])
def bulk_add():
    """Add multiple blacklist entries at once."""
    entry_type = request.form.get("entry_type", "email")
    values_text = request.form.get("values", "").strip()

    if not values_text:
        flash("Please enter at least one value.", "error")
        return redirect(url_for("blacklist.index"))

    # Parse values (one per line or comma-separated)
    values = []
    for line in values_text.replace(",", "\n").split("\n"):
        value = line.strip().lower()
        if value:
            # Clean up domain
            if entry_type == "domain" and value.startswith("@"):
                value = value[1:]
            values.append(value)

    added = 0
    skipped = 0

    for value in values:
        # Skip invalid emails
        if entry_type == "email" and "@" not in value:
            skipped += 1
            continue

        # Check for duplicate
        existing = (
            g.db.query(BlacklistEntry)
            .filter(
                BlacklistEntry.entry_type == entry_type,
                BlacklistEntry.value == value,
                BlacklistEntry.is_active == True,
            )
            .first()
        )

        if existing:
            skipped += 1
            continue

        # Create entry
        entry = BlacklistEntry(entry_type=entry_type, value=value)
        g.db.add(entry)
        added += 1

    g.db.commit()

    if added:
        flash(f"Added {added} entries to blacklist.", "success")
        logger.info(f"Bulk added {added} blacklist entries")
    if skipped:
        flash(f"Skipped {skipped} duplicates or invalid entries.", "warning")

    return redirect(url_for("blacklist.index"))
