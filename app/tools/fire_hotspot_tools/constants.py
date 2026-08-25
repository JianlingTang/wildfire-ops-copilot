"""Shared constants for the fire-hotspot tool package."""

from __future__ import annotations

DEA_HOTSPOTS_URL = "https://hotspots.dea.ga.gov.au/data/recent-hotspots.json"
AUTO_REGION_IDS = {"live_australia", "auto", "auto_australia"}
STATE_LABELS = {
    "ACT": "Australian Capital Territory",
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "NT": "Northern Territory",
    "WA": "Western Australia",
    "VIC": "Victoria",
    "SA": "South Australia",
    "TAS": "Tasmania",
}
STATE_FOCUS_DEFAULTS = {
    "ACT": (-35.4735, 149.0124),
    "NSW": (-32.1633, 147.0166),
    "QLD": (-21.1411, 145.3260),
    "NT": (-19.4914, 133.6146),
    "WA": (-25.2303, 121.0187),
    "VIC": (-36.7604, 144.2811),
    "SA": (-30.0002, 136.2092),
    "TAS": (-42.0409, 146.8087),
}
OVERVIEW_RADIUS_OPTIONS_KM = [30, 50, 100, 200]
DEA_REFRESH_INTERVAL_SECONDS = 600
OVERVIEW_MAP_HOTSPOT_LIMIT = 2400
FOCUS_MAP_HOTSPOT_LIMIT = 1600
