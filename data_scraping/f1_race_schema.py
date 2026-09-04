import csv
import re
from pathlib import Path

import fastf1
import pandas as pd

DATA_DIR = Path("f1_data")
CACHE_DIR = Path(".cache/fastf1")
MIN_YEAR = 2020
YEAR_FACTOR = 100
RACE_SESSION = "R"
MS_PER_HOUR = 3_600_000
MS_PER_MINUTE = 60_000
MS_PER_SECOND = 1000
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

RACE_FIELDS = [
    "race_id", "name", "official_name", "date", "location", "country",
    "round", "total_laps",
]
DRIVER_FIELDS = [
    "race_id", "driver_id", "abbreviation", "driver", "car_number", "team",
    "start", "finish", "status", "points", "laps", "time", "pit_stops",
    "fastest_lap", "fastest_lap_time",
]
LAP_FIELDS = [
    "driver_id", "abbreviation", "car_number", "team", "lap_number",
    "position", "lap_time", "lap_time_ms", "stint", "compound", "tyre_life",
    "pit_in", "deleted", "is_accurate"
]


def enable_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    fastf1.set_log_level("ERROR")


def make_race_id(year, round_number):
    return year * YEAR_FACTOR + round_number


def is_blank(value):
    if value is None or value == "":
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def clean_text(value):
    return "" if is_blank(value) else str(value).strip()


def clean_int(value):
    return "" if is_blank(value) else int(float(value))


def clean_points(value):
    if is_blank(value):
        return ""
    number = float(value)
    return int(number) if number.is_integer() else number


def clean_flag(value):
    return "" if is_blank(value) else int(bool(value))


def timedelta_ms(value):
    if is_blank(value):
        return None
    return int(round(pd.Timedelta(value).total_seconds() * MS_PER_SECOND))


def format_clock(ms, include_hours=False):
    hours, rest = divmod(ms, MS_PER_HOUR)
    minutes, rest = divmod(rest, MS_PER_MINUTE)
    seconds, millis = divmod(rest, MS_PER_SECOND)
    if include_hours and hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def format_lap_time(value):
    ms = timedelta_ms(value)
    return "" if ms is None else format_clock(ms)


def format_race_time(value):
    ms = timedelta_ms(value)
    return "" if ms is None else format_clock(ms, include_hours=True)


def format_date(value):
    if is_blank(value):
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def race_file_stem(race_id, name):
    slug = NON_ALNUM_RE.sub("_", (name or "").lower()).strip("_")
    return f"{race_id}_{slug or 'race'}"


def year_from_date(date_str):
    if not date_str:
        raise ValueError("Race date is missing; cannot determine output year")
    return str(date_str)[:4]


def existing_race_ids(path):
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["race_id"] for row in csv.DictReader(handle) if row.get("race_id")}


def csv_fields(path):
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        return csv.DictReader(handle).fieldnames


def is_legacy_year(path, year):
    fields = csv_fields(path)
    if fields is None:
        return False
    if list(fields) != RACE_FIELDS:
        return True
    for race_id in existing_race_ids(path):
        value = clean_int(race_id)
        if value == "" or value // YEAR_FACTOR != year:
            return True
    return False


def clear_year_output(year_dir):
    for name in ("races.csv", "drivers.csv"):
        path = year_dir / name
        if path.exists():
            path.unlink()
    laps_dir = year_dir / "laps"
    if not laps_dir.exists():
        return
    for old in laps_dir.glob("*.csv"):
        old.unlink()


def append_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def laps_path_for(race):
    stem = race_file_stem(race["race_id"], race["name"])
    year = year_from_date(race["date"])
    return DATA_DIR / year / "laps" / f"{stem}.csv"


def save_laps_csv(race, lap_rows):
    path = laps_path_for(race)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LAP_FIELDS)
        writer.writeheader()
        writer.writerows(lap_rows)
    return path


def write_outputs(race, drivers, lap_rows):
    out_dir = DATA_DIR / year_from_date(race["date"])
    races_path = out_dir / "races.csv"
    if is_legacy_year(races_path, int(out_dir.name)):
        clear_year_output(out_dir)
    written = race["race_id"] not in existing_race_ids(races_path)
    if written:
        append_csv(races_path, RACE_FIELDS, [race])
        append_csv(out_dir / "drivers.csv", DRIVER_FIELDS, drivers)
    path = laps_path_for(race)
    laps_written = written or not path.exists()
    if laps_written:
        path = save_laps_csv(race, lap_rows)
    return out_dir, written, path, laps_written
