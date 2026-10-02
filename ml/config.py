"""Single source of truth for paths, data sources and time conventions."""

from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"

# --- Ausgrid Solar Home Electricity Data -----------------------------------
# Ausgrid withdrew the download from ausgrid.com.au (the original URLs now 404,
# checked 2026-10-02). The only reachable copy is a self-hosted mirror by
# Pierre Haessig, who is unaffiliated with Ausgrid. Because the provenance is a
# third party, we pin the archive's SHA-256 on first download and validate the
# contents structurally (300 customers, 3 financial years, 48 half-hour columns).
# Dataset reference: Ratnam, Weller, Kellett & Murray (2017), "Residential load
# and rooftop PV generation: an Australian distribution network dataset",
# Int. J. Sustainable Energy, doi:10.1080/14786451.2015.1100196.
AUSGRID_URL = "https://pierreh.eu/downloads/Ausgrid_solar_home_data.zip"
# Pinned 2026-10-02 after checking the archive holds the three yearly CSVs and
# Ausgrid's own "data notes (Aug 2014).pdf", with 2014-15 file timestamps.
AUSGRID_SHA256 = "5a766f52b6c8b3b72730380f4422e478934bc94640a4b089dd0e0e3c055c5d82"
AUSGRID_ZIP = DATA_RAW / "Ausgrid_solar_home_data.zip"
AUSGRID_DIR = DATA_RAW / "ausgrid"

# Postcode centroids for the dataset's postcodes, geocoded by the same author
# (CC BY 4.0). Pinned to a commit so the file cannot change under us.
POSTCODES_URL = (
    "https://raw.githubusercontent.com/pierre-haessig/ausgrid-solar-data/"
    "0a51db9206b9b662f07b1f7ddee8969a67bb0f68/postcodes/postcodes.csv"
)
POSTCODES_CSV = DATA_RAW / "postcodes.csv"

# --- Open-Meteo historical archive (ERA5 reanalysis for 2010-2013) ---------
OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_DIR = DATA_RAW / "weather"
# Radiation variables are means over the PRECEDING hour; temperature and cloud
# cover are instantaneous at the timestamp. weather.py aligns each accordingly.
WEATHER_HOURLY_MEAN_VARS = ["shortwave_radiation", "direct_radiation", "diffuse_radiation"]
WEATHER_HOURLY_INSTANT_VARS = ["temperature_2m", "cloud_cover"]

# --- Time convention -------------------------------------------------------
# Every timestamp in the processed panel is the START of a half-hour settlement
# period, stored in UTC. Slot numbers 1..48 are computed in a fixed UTC+10
# offset (AEST, no daylight saving), so a slot means the same solar time all
# year. The RAW files are in Sydney clock time WITH daylight saving;
# preprocess.py converts them and proves the conversion against solar noon.
LOCAL_TZ = timezone(timedelta(hours=10), name="AEST")
PERIOD = timedelta(minutes=30)
SLOTS_PER_DAY = 48

PANEL_PARQUET = DATA_PROCESSED / "panel.parquet"
WEATHER_PARQUET = DATA_PROCESSED / "weather.parquet"
CUSTOMERS_PARQUET = DATA_PROCESSED / "customers.parquet"
QUALITY_JSON = DATA_PROCESSED / "quality_report.json"
