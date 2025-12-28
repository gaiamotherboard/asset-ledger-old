"""
Django Forms for Asset Management
These handle user input validation for intake forms and file uploads
"""

import csv
import io
import json

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Asset, Drive
from .utils import norm_serial


class AssetIntakeForm(forms.ModelForm):
    """
    Form for updating asset intake information.
    Used when processing a device (status, condition, location, etc.)
    """

    class Meta:
        model = Asset
        fields = [
            "status",
            "device_type",
            "cosmetic_grade",
            "cosmetic_notes",
            "location",
        ]
        widgets = {
            "status": forms.Select(attrs={"class": "form-control"}),
            "device_type": forms.Select(attrs={"class": "form-control"}),
            "cosmetic_grade": forms.Select(attrs={"class": "form-control"}),
            "cosmetic_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Any scratches, dents, or cosmetic issues...",
                }
            ),
            "location": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Shelf A3, Bin 12, etc."}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional (can update just one field at a time)
        for field in self.fields.values():
            field.required = False


class HardwareScanUploadForm(forms.Form):
    """
    Form for uploading a scan bundle JSON (schema motherboard.scan_bundle.v1).

    This validates:
    - file size (uses existing MAX_LSHW_BYTES setting by default)
    - UTF-8 text
    - valid JSON object
    - required bundle structure and keys per the contract:
      * schema == "motherboard.scan_bundle.v1"
      * generated_at
      * scanner {hostname, user}
      * intake {asset_id, ...}
      * sources including 'lshw'
      * meta.status present
    On success the parsed bundle dict is stored as cleaned_data["parsed_json"].
    """

    file = forms.FileField(
        label="Scan Bundle JSON File",
        help_text="Upload the scan bundle JSON (schema motherboard.scan_bundle.v1). It must include sources.lshw.",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".json"}),
    )
    user_notes = forms.CharField(
        label="Notes (Optional)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Any notes about this scan...",
            }
        ),
    )

    def clean_file(self):
        """
        Validate the uploaded file:
        1. Check file size (max 5MB by default via MAX_LSHW_BYTES)
        2. Verify it's UTF-8 text and valid JSON
        3. Validate required scan bundle keys and basic structure
        """
        uploaded_file = self.cleaned_data.get("file")

        if not uploaded_file:
            raise ValidationError("No file was uploaded.")

        # Check file size (reuse existing setting to avoid config churn)
        max_size = getattr(settings, "MAX_LSHW_BYTES", 5242880)  # 5MB default
        if uploaded_file.size > max_size:
            raise ValidationError(
                f"File too large. Maximum size is {max_size / 1024 / 1024:.1f} MB."
            )

        # Read and validate JSON
        try:
            content = uploaded_file.read()
            # Try to decode as UTF-8
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                raise ValidationError("File must be UTF-8 encoded text.")

            # Parse JSON
            data = json.loads(text)

            # Top-level must be an object/dict
            if not isinstance(data, dict):
                raise ValidationError("Invalid scan bundle: expected JSON object.")

            # Required schema string
            schema = data.get("schema")
            if schema != "motherboard.scan_bundle.v1":
                raise ValidationError(
                    "Invalid schema: expected 'motherboard.scan_bundle.v1'."
                )

            # generated_at is required (string ISO)
            if "generated_at" not in data:
                raise ValidationError("Missing required field: generated_at")

            # scanner metadata must exist with hostname and user
            scanner = data.get("scanner")
            if (
                not isinstance(scanner, dict)
                or not scanner.get("hostname")
                or not scanner.get("user")
            ):
                raise ValidationError(
                    "Missing or invalid scanner metadata (requires hostname and user)."
                )

            # intake must exist and include asset_id
            intake = data.get("intake")
            if not isinstance(intake, dict) or not intake.get("asset_id"):
                raise ValidationError(
                    "Missing or invalid intake data (requires asset_id)."
                )

            # sources must exist and include lshw (we continue to use lshw parsing)
            sources = data.get("sources")
            if not isinstance(sources, dict) or "lshw" not in sources:
                raise ValidationError("Missing required source: sources.lshw")

            # meta.status should be present (per contract)
            meta = data.get("meta")
            if not isinstance(meta, dict) or "status" not in meta:
                raise ValidationError("Missing required field: meta.status")

            # Store parsed data for later use by the view
            self.cleaned_data["parsed_json"] = data

            # Reset file pointer in case it needs to be read again
            uploaded_file.seek(0)

        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON format: {str(e)}")

        return uploaded_file


class DriveStatusForm(forms.ModelForm):
    """
    Form for updating drive status (wiped, shredded, removed, etc.)
    """

    class Meta:
        model = Drive
        fields = ["status", "status_note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-control"}),
            "status_note": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 2,
                    "placeholder": "Optional notes about this status change...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status_note"].required = False


class DriveRemovalImportForm(forms.Form):
    """
    Upload/paste a 2-column list of:
      computer_serial, drive_serial

    Accepts CSV or TSV (auto-detected by sniffing or simple fallback).
    The view is responsible for creating DriveRemovalBatch + upserting DriveRemovalLink;
    this form provides parsing helpers + validation.
    """

    file = forms.FileField(
        label="CSV/TSV file (optional)",
        required=False,
        widget=forms.FileInput(
            attrs={"class": "form-control", "accept": ".csv,.tsv,.txt"}
        ),
    )
    manual_text = forms.CharField(
        label="Paste lines (optional)",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 10,
                "placeholder": "computer_serial,drive_serial\nCOMPUTER123,DRIVE456\n...\n\nYou can also tab-separate columns.",
            }
        ),
    )
    note = forms.CharField(
        label="Note (optional)",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def clean(self):
        cleaned = super().clean()
        uploaded_file = cleaned.get("file")
        manual_text = (cleaned.get("manual_text") or "").strip()

        if not uploaded_file and not manual_text:
            raise ValidationError(
                "Provide either a file upload or pasted text (or both)."
            )

        return cleaned

    def iter_pairs(self):
        """
        Yield tuples: (computer_serial_norm, drive_serial_norm, raw_line, row_index)

        - For manual_text: row_index is 1-based line number.
        - For file: row_index is 1-based CSV row number (including header if present).
        """
        uploaded_file = self.cleaned_data.get("file")
        manual_text = self.cleaned_data.get("manual_text") or ""

        if uploaded_file:
            content = uploaded_file.read()
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError:
                raise ValidationError("Upload must be UTF-8 text (CSV/TSV).")

            # Reset file pointer so the view/model FileField save still works if needed.
            try:
                uploaded_file.seek(0)
            except Exception:
                pass

            # Try sniffing delimiter; fall back to tab if file looks TSV, else comma.
            sample = text[:4096]
            delimiter = ","
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
                delimiter = dialect.delimiter
            except Exception:
                if "\t" in sample and "," not in sample:
                    delimiter = "\t"

            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            for idx, row in enumerate(reader, start=1):
                if not row:
                    continue
                # Support accidental extra columns; take first two only
                c = row[0] if len(row) > 0 else ""
                d = row[1] if len(row) > 1 else ""
                cs = norm_serial(c)
                ds = norm_serial(d)
                raw_line = delimiter.join(row)
                yield (cs, ds, raw_line, idx)

        if manual_text:
            for idx, line in enumerate(manual_text.splitlines(), start=1):
                raw = line.rstrip("\n")
                if not raw.strip():
                    continue
                # Accept comma or tab separators (prefer tab if present)
                if "\t" in raw:
                    parts = raw.split("\t")
                else:
                    parts = raw.split(",")
                c = parts[0] if len(parts) > 0 else ""
                d = parts[1] if len(parts) > 1 else ""
                cs = norm_serial(c)
                ds = norm_serial(d)
                yield (cs, ds, raw, idx)
