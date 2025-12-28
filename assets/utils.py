"""
Shared utilities for the `assets` app.

Includes:
- Serial normalization helper used across scan intake and imports.
- Resolver for "removed before scan" imported drive pairs (DriveRemovalLink)
  to ensure real Drive rows exist for later lifecycle actions (wiped/shredded/etc).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from django.utils import timezone

from .models import Asset, Drive, DriveRemovalLink

_NON_PRINTABLE_RE = re.compile(r"[\x00-\x1F\x7F]")
_INTERNAL_WS_RE = re.compile(r"\s+")


def norm_serial(s: Optional[str]) -> str:
    """
    Normalize a serial-like identifier for consistent storage and matching.

    Rules:
    - return "" if None
    - Unicode normalize (NFKC) to reduce weird lookalikes
    - strip leading/trailing whitespace
    - collapse internal whitespace to single spaces
    - uppercase
    - remove ASCII non-printable control chars
    """
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)

    # Normalize Unicode (handles some pasted spreadsheet oddities)
    s = unicodedata.normalize("NFKC", s)

    # Remove non-printable control chars, then normalize whitespace
    s = _NON_PRINTABLE_RE.sub("", s)
    s = s.strip()
    s = _INTERNAL_WS_RE.sub(" ", s)

    return s.upper()


def resolve_removed_drives_for_asset(asset: Asset) -> int:
    """
    Ensure Drive rows exist for imported removed-before-scan pairs for this asset.

    Idempotent behavior:
    - Uses Drive(asset, serial) uniqueness to avoid duplicates.
    - Will not downgrade a Drive status if it is already beyond "present".
    - Will flag links as suspect if the same drive serial exists on other assets.

    Returns: count of links resolved (processed) for this asset.
    """
    if not getattr(asset, "computer_serial", None):
        return 0

    cs = norm_serial(asset.computer_serial)
    if not cs:
        return 0

    links = DriveRemovalLink.objects.filter(computer_serial=cs)
    resolved = 0

    for link in links:
        drive_serial = norm_serial(link.drive_serial)
        if not drive_serial:
            # Link should have been normalized at import time, but stay safe.
            continue

        drive, created = Drive.objects.get_or_create(
            asset=asset,
            serial=drive_serial,
            defaults={
                "status": "removed_before_scan",
                "source": "spreadsheet",
            },
        )

        if not created:
            # Only move "present" -> "removed_before_scan"; never downgrade.
            if drive.status == "present":
                drive.status = "removed_before_scan"
                drive.save(update_fields=["status", "status_at"])

        # Non-blocking suspect flag: same serial on other assets.
        if Drive.objects.filter(serial=drive_serial).exclude(asset=asset).exists():
            link.flagged_suspect = True
            # Preserve any existing note; append if needed.
            note = (link.flag_note or "").strip()
            new_note = "drive_serial appears on other assets (possible mis-scan)"
            if note:
                if new_note not in note:
                    link.flag_note = f"{note}\n{new_note}"
            else:
                link.flag_note = new_note

        link.resolved_asset = asset
        link.resolved_drive = drive
        link.resolved_at = timezone.now()
        link.save(
            update_fields=[
                "flagged_suspect",
                "flag_note",
                "resolved_asset",
                "resolved_drive",
                "resolved_at",
                "last_seen_at",
            ]
        )
        resolved += 1

    return resolved
