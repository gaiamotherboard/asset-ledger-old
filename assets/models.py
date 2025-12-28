"""
Asset tracking models - Django ORM definitions
These replace the manual SQL tables from the FastAPI app
"""

from django.contrib.auth.models import User
from django.db import models


class Asset(models.Model):
    """
    Main asset model - represents a physical device (computer, server, etc.)
    Auto-created on first visit to /asset/{asset_tag}/
    """

    STATUS_CHOICES = [
        ("intake", "Intake"),
        ("testing", "Testing"),
        ("ready", "Ready for Sale"),
        ("sold", "Sold"),
        ("recycled", "Recycled"),
        ("returned", "Returned to Client"),
    ]

    DEVICE_TYPE_CHOICES = [
        ("laptop", "Laptop"),
        ("desktop", "Desktop"),
        ("server", "Server"),
        ("tablet", "Tablet"),
        ("phone", "Phone"),
        ("other", "Other"),
    ]

    COSMETIC_GRADE_CHOICES = [
        ("A", "Grade A - Excellent"),
        ("B", "Grade B - Good"),
        ("C", "Grade C - Fair"),
        ("D", "Grade D - Poor"),
    ]

    asset_tag = models.CharField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="assets_created"
    )

    # Computer serial (from lshw "Device Serial Number", normalized at query time)
    computer_serial = models.CharField(
        max_length=200, blank=True, null=True, db_index=True
    )

    # Intake information
    status = models.CharField(
        max_length=50, choices=STATUS_CHOICES, blank=True, default=""
    )
    device_type = models.CharField(
        max_length=100, choices=DEVICE_TYPE_CHOICES, blank=True, default=""
    )
    cosmetic_grade = models.CharField(
        max_length=20, choices=COSMETIC_GRADE_CHOICES, blank=True, default=""
    )
    cosmetic_notes = models.TextField(blank=True, default="")
    location = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Asset"
        verbose_name_plural = "Assets"

    def __str__(self):
        return f"{self.asset_tag}"


class HardwareScan(models.Model):
    """
    Hardware scan record - stores scan bundle JSON output (motherboard.scan_bundle.v1)

    We intentionally keep the existing model/table name to minimize code churn.
    The `raw_json` field continues to store the uploaded payload (previously
    it stored LSHW JSON; now it stores the full scan bundle). We add a
    content hash for deduplication, generated_at from the bundle, the schema
    string and duplicate intake fields to support easy querying in the future.
    """

    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name="hardware_scans"
    )
    device_serial = models.CharField(max_length=200, blank=True, null=True)

    # Raw uploaded bundle (previously was full lshw output; now the whole bundle)
    raw_json = models.JSONField()

    # Deduplication hash (sha256 of canonical JSON form)
    bundle_hash = models.CharField(max_length=64, db_index=True, blank=True, null=True)

    # Bundle metadata
    schema = models.CharField(max_length=200, blank=True, default="")
    generated_at = models.DateTimeField(blank=True, null=True)

    # Duplicate intake fields for easier querying/filtering
    tech_name = models.CharField(max_length=200, blank=True, default="")
    client_name = models.CharField(max_length=200, blank=True, default="")
    cosmetic_condition = models.CharField(max_length=10, blank=True, default="")
    intake_note = models.TextField(blank=True, default="")

    # Extracted summary (CPU, RAM, etc.) - unchanged
    summary = models.JSONField(blank=True, null=True)

    scanned_at = models.DateTimeField(auto_now_add=True)
    scanned_by = models.ForeignKey(User, on_delete=models.PROTECT)
    user_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-scanned_at"]
        verbose_name = "Hardware Scan"
        verbose_name_plural = "Hardware Scans"
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "bundle_hash"], name="unique_asset_bundlehash"
            )
        ]
        indexes = [
            # helpful index to query scans by asset and generation time
            models.Index(
                fields=["asset", "generated_at"], name="asset_generated_at_idx"
            ),
        ]

    def __str__(self):
        return f"Scan of {self.asset.asset_tag} at {self.scanned_at}"


class Drive(models.Model):
    """
    Storage drives attached to an asset
    Tracks drive lifecycle: present, removed, wiped, shredded, etc.
    """

    STATUS_CHOICES = [
        ("present", "Present"),
        ("removed", "Removed"),
        ("removed_before_scan", "Removed Before Scan"),
        ("wiped", "Wiped"),
        ("shredded", "Shredded"),
        ("returned_to_client", "Returned to Client"),
    ]

    SOURCE_CHOICES = [
        ("lshw", "LSHW Scan"),
        ("manual", "Manual Entry"),
        ("spreadsheet", "Spreadsheet Import"),
    ]

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="drives")
    serial = models.CharField(max_length=200)  # Drive serial number
    logicalname = models.CharField(
        max_length=100, blank=True, default=""
    )  # e.g., /dev/sda
    capacity_bytes = models.BigIntegerField(blank=True, null=True)
    model = models.CharField(max_length=200, blank=True, default="")
    source = models.CharField(max_length=50, choices=SOURCE_CHOICES, default="lshw")

    # Status tracking
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default="present")
    status_note = models.TextField(blank=True, default="")
    status_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="drive_status_updates",
    )
    status_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Each serial is unique per asset (same drive can't be in asset twice)
        unique_together = [["asset", "serial"]]
        ordering = ["id"]
        verbose_name = "Drive"
        verbose_name_plural = "Drives"

    def __str__(self):
        return f"{self.serial} on {self.asset.asset_tag}"

    @property
    def capacity_human(self):
        """Human-readable capacity (e.g., 256 GB)"""
        if not self.capacity_bytes:
            return None
        # Simple formatter - use local variable to avoid mutation bug
        bytes_remaining = float(self.capacity_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_remaining < 1024.0:
                return f"{bytes_remaining:.1f} {unit}"
            bytes_remaining /= 1024.0
        return f"{bytes_remaining:.1f} PB"

    @property
    def serial_tag(self):
        """Display tag for serial (handles NOSERIAL- case)"""
        if not self.serial:
            return None
        if self.serial.startswith("NOSERIAL-"):
            return "(no serial)"
        return f"(SN {self.serial})"


class DriveRemovalBatch(models.Model):
    """
    One import session of removed-before-scan drive pairs.

    Stores original upload / pasted text for audit + simple per-batch stats.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, blank=True, null=True
    )

    original_file = models.FileField(upload_to="drive_removals/", blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True, default="")
    manual_text = models.TextField(blank=True, default="")
    note = models.TextField(blank=True, default="")

    total_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Drive Removal Batch"
        verbose_name_plural = "Drive Removal Batches"

    def __str__(self):
        return f"DriveRemovalBatch {self.id} at {self.created_at}"


class DriveRemovalLink(models.Model):
    """
    One logical pair (computer_serial, drive_serial), deduped for idempotency.

    Later resolved to real Asset/Drive rows when possible.
    """

    computer_serial = models.CharField(max_length=200, db_index=True)  # normalized
    drive_serial = models.CharField(max_length=200, db_index=True)  # normalized

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    seen_count = models.PositiveIntegerField(default=1)

    last_batch = models.ForeignKey(
        DriveRemovalBatch, on_delete=models.SET_NULL, blank=True, null=True
    )

    resolved_asset = models.ForeignKey(
        Asset, on_delete=models.SET_NULL, blank=True, null=True
    )
    resolved_drive = models.ForeignKey(
        "Drive", on_delete=models.SET_NULL, blank=True, null=True
    )
    resolved_at = models.DateTimeField(blank=True, null=True)

    flagged_suspect = models.BooleanField(default=False)
    flag_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-last_seen_at"]
        verbose_name = "Drive Removal Link"
        verbose_name_plural = "Drive Removal Links"
        constraints = [
            models.UniqueConstraint(
                fields=["computer_serial", "drive_serial"],
                name="uniq_drive_removal_pair",
            )
        ]

    def __str__(self):
        return f"{self.computer_serial} -> {self.drive_serial}"


class AssetTouch(models.Model):
    """
    Audit trail - records every interaction with an asset
    This is your complete history log
    """

    TOUCH_TYPE_CHOICES = [
        ("view", "Viewed"),
        ("scan_upload", "Hardware Scan Uploaded"),
        ("intake_update", "Intake Information Updated"),
        ("drive_status", "Drive Status Changed"),
        ("note", "Note Added"),
    ]

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="touches")
    touch_type = models.CharField(max_length=50, choices=TOUCH_TYPE_CHOICES)
    touched_by = models.ForeignKey(User, on_delete=models.PROTECT)
    touched_at = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(blank=True, null=True)  # Flexible details storage

    class Meta:
        ordering = ["-touched_at"]
        verbose_name = "Asset Touch"
        verbose_name_plural = "Asset Touches"

    def __str__(self):
        return f"{self.touch_type} on {self.asset.asset_tag} by {self.touched_by}"
