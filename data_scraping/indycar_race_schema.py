import re
from pathlib import Path

import pandas as pd
import raceindycar

DATA_DIR = Path("indycar_data")
CACHE_DIR = Path(".cache/raceindycar")
MIN_YEAR = 2020
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
YEAR_PREFIX_RE = re.compile(r"^\d{4}\s+")
SPONSOR_TAIL_RE = re.compile(
    r"\s+(?:presented by|available at|powered by)\b.*$",
    re.IGNORECASE,
)
RACE_FIELDS = [
    "race_id", "name", "date", "track_type", "actual_laps",
]
DRIVER_FIELDS = [
    "race_id", "driver_id", "driver", "car_number", "team", "start", "finish",
    "finish_status", "points", "laps", "laps_led", "times_led",
    "fastest_lap_speed", "avg_lap_speed", "pit_stops",
]
LAP_FIELDS = [
    "driver_name", "car_number", "team", "lap_number", "position",
    "lap_time", "lap_speed", "on_pit_road",
]


def enable_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raceindycar.enable_cache(str(CACHE_DIR), cache_format="csv")


def clean_text(value):
    return "" if pd.isna(value) or value == "" else str(value).strip()


def clean_int(value):
    if pd.isna(value) or value == "":
        return ""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return ""


def race_file_stem(race_id, name):
    short = YEAR_PREFIX_RE.sub("", name or "").strip()
    short = SPONSOR_TAIL_RE.sub("", short).strip()
    slug = NON_ALNUM_RE.sub("_", short.lower()).strip("_")
    return f"{race_id}_{slug or 'race'}"
