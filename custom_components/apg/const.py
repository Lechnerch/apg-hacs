"""Constants for the Austrian Power Grid (APG) integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "apg"

# ---------------------------------------------------------------------------
# Peak hour API (no authentication required)
# Docs: https://awareness.cloud.apg.at/api/swagger/index.html?urls.primaryName=Peak+hour+API
# ---------------------------------------------------------------------------
PEAK_HOUR_URL: Final = "https://awareness.cloud.apg.at/api/v1/PeakHourStatus"

# Status codes used by the peak hour API.
STATUS_OFF_PEAK: Final = "1"
STATUS_PEAK: Final = "2"

# ---------------------------------------------------------------------------
# Powermonitor / Infografics API (requires a Bearer token)
# Docs: https://awareness.cloud.apg.at/api/swagger/index.html?urls.primaryName=Infografics+API
# ---------------------------------------------------------------------------
POWERMONITOR_URL: Final = "https://app.23degrees.io/api/v2/content/{slug}/data"

# The known public content slugs of the APG Powermonitor.
# The value is a human readable name used for the entity.
POWERMONITOR_SLUGS: Final[dict[str, str]] = {
    "onFQVwdMNSZ62rCN-line-erzeugung-erneuerbarer-energien": "Erzeugung erneuerbarer Energien",
    "n3vfefqpLyjsQ5s2-line-lastfluesse": "Lastflüsse",
    "dpcgsZKysiXZmwtf-bar-vertical-eigenerzeugung-von-energie-in": "Eigenerzeugung von Energie",
    "K7tley8BjdU1ng8j-bar-vertical-woechentlicher-energieverbrauch": "Wöchentlicher Energieverbrauch",
    "btohciVvwEG8jAGr-donut-verfuegbare": "Verfügbare Kapazität",
    "N8hJwwM6SllaR3bZ-donut-gaskraftwerke-erzeugungsgrad": "Gaskraftwerke Erzeugungsgrad",
    "VUGApLOeJOMFkc13-bar-vertical-import-europaeischer-reglerwerte": "Import europäischer Reglerwerte",
}

# ---------------------------------------------------------------------------
# Config / options keys
# ---------------------------------------------------------------------------
CONF_POWERMONITOR_TOKEN: Final = "powermonitor_token"
CONF_POWERMONITOR_SLUGS: Final = "powermonitor_slugs"
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=30)
MIN_SCAN_INTERVAL_MINUTES: Final = 5
DEFAULT_SCAN_INTERVAL_MINUTES: Final = 30

# Powermonitor is polled less often (its data changes slowly and the free
# token is shared). This multiplier is applied to the configured interval.
POWERMONITOR_INTERVAL_FACTOR: Final = 4

ATTRIBUTION: Final = (
    "Mehr zum Thema sichere Stromversorgung und zur Energiewende unter "
    "www.apg-powermonitor.at"
)

MANUFACTURER: Final = "Austrian Power Grid AG"
