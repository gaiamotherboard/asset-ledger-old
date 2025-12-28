"""
URL Configuration for Assets App
Maps URLs to views - replaces FastAPI route decorators
"""

from django.urls import path

from . import views

urlpatterns = [
    # Drive removals import (removed-before-scan)
    path(
        "drive-removals/import/",
        views.drive_removals_import,
        name="drive_removals_import",
    ),
    # Home page
    path("", views.home, name="home"),
    # Asset detail (auto-creates on first visit)
    path("asset/<str:asset_tag>/", views.asset_detail, name="asset_detail"),
    # Asset intake form update
    path(
        "asset/<str:asset_tag>/intake/",
        views.asset_intake_update,
        name="asset_intake_update",
    ),
    # Hardware scan upload (single asset)
    path(
        "asset/<str:asset_tag>/upload/",
        views.asset_scan_upload,
        name="asset_scan_upload",
    ),
    # Hardware scan upload (bulk: multiple files -> multiple assets)
    path(
        "asset/scan/bulk-upload/",
        views.asset_scan_bulk_upload,
        name="asset_scan_bulk_upload",
    ),
    # Drive status update
    path(
        "asset/<str:asset_tag>/drive/<int:drive_id>/status/",
        views.drive_status_update,
        name="drive_status_update",
    ),
    # Drive search by serial (JSON API)
    path("api/drive/by_serial/", views.drive_search_by_serial, name="drive_search"),
    # Asset list JSON API
    path("api/assets/", views.asset_list_json, name="asset_list_json"),
]
