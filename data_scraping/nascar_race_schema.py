import csv
import re
from pathlib import Path

import pandas as pd
from pynascar import FLAG_CODE, set_options

DATA_DIR = Path("nascar_data")
CACHE_DIR = Path(".cache/pynascar")
MIN_YEAR = 2020
CUP_SERIES_ID = 1
POINTS_RACE_TYPE = 1
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
SPONSOR_TAIL_RE = re.compile(
    r"\s+(?:presented by|available at|powered by)\b.*$",
    re.IGNORECASE,
)
RACE_FIELDS = [
    "race_id", "name", "date", "track", "track_miles", "scheduled_laps",
    "scheduled_miles", "actual_laps", "actual_miles", "points_race",
    "caution_laps",
]
DRIVER_FIELDS = [
    "race_id", "driver_id", "driver", "car_number", "manufacturer", "start",
    "finish", "finish_status", "arp", "high", "low", "gfp_plus_minus",
    "gfp_plus", "gfp_minus", "qp", "pct_qp", "fastest_laps", "t15_laps",
    "pct_t15", "laps_led", "pct_led",
]
LAP_FIELDS = [
    "driver_name", "driver_id", "manufacturer", "car_number", "lap_number",
    "running_position", "lap_speed", "lap_time", "team", "playoffs",
    "points_ineligible", "starting_position", "finish_position", "statuses",
]
OEM_FULL = {
    "ford": "ford", "frd": "ford",
    "chevrolet": "chevrolet", "chevy": "chevrolet", "chv": "chevrolet",
    "toyota": "toyota", "tyt": "toyota",
}
LOOP_INT = (
    ("start", "start_position"), ("finish", "position"),
    ("high", "best_position"), ("low", "worst_position"),
    ("gfp_plus_minus", "passing_diff"), ("gfp_plus", "passes_green_flag"),
    ("gfp_minus", "passed_green_flag"), ("qp", "quality_passes"),
    ("fastest_laps", "fast_laps"), ("t15_laps", "top15_laps"),
    ("laps_led", "lead_laps"),
)


def enable_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    set_options(cache_enabled=True, cache_dir=str(CACHE_DIR))


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


def clean_number(value):
    if is_blank(value):
        return ""
    number = float(value)
    return int(number) if number.is_integer() else number


def driver_key(value):
    number = clean_int(value)
    return "" if number == "" else str(number)


def normalize_oem(value):
    key = clean_text(value).casefold()
    return OEM_FULL.get(key, key)


def flag_status(flag_state):
    if is_blank(flag_state):
        return ""
    name = FLAG_CODE.get(int(float(flag_state)), "")
    if name == "Green":
        return "green"
    if name == "Yellow":
        return "caution"
    return name.lower()


def fmt_pct(part, whole):
    if is_blank(part) or is_blank(whole) or float(whole) == 0:
        return ""
    return f"{100 * float(part) / float(whole):.2f}"


def track_miles(distance, laps):
    if is_blank(distance) or is_blank(laps) or float(laps) == 0:
        return ""
    return f"{float(distance) / float(laps):.2f}"


def race_file_stem(race_id, name):
    short = SPONSOR_TAIL_RE.sub("", name or "").strip()
    slug = NON_ALNUM_RE.sub("_", short.lower()).strip("_")
    return f"{race_id}_{slug or 'race'}"


def year_from_date(date_str):
    if not date_str:
        raise ValueError("Race date is missing; cannot determine output year")
    return str(date_str)[:4]


def existing_race_ids(path):
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {row["race_id"] for row in reader if row.get("race_id")}


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
    return DATA_DIR / year_from_date(race["date"]) / "laps" / f"{stem}.csv"


def write_outputs(race, drivers, lap_rows):
    out_dir = DATA_DIR / year_from_date(race["date"])
    races_path = out_dir / "races.csv"
    written = race["race_id"] not in existing_race_ids(races_path)
    if written:
        append_csv(races_path, RACE_FIELDS, [race])
        append_csv(out_dir / "drivers.csv", DRIVER_FIELDS, drivers)
    path = laps_path_for(race)
    laps_written = written or not path.exists()
    if laps_written:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=LAP_FIELDS)
            writer.writeheader()
            writer.writerows(lap_rows)
    return out_dir, written, path, laps_written


def frame_records(frame):
    if frame is None or getattr(frame, "empty", True):
        return []
    return frame.to_dict("records")


def by_driver(frame):
    rows = {}
    for row in frame_records(frame):
        key = driver_key(row.get("driver_id"))
        if key:
            rows[key] = row
    return rows


def weekend_results(weekend):
    races = (weekend or {}).get("weekend_race") or []
    return races[0].get("results") or [] if races else []


def result_status_maps(weekend):
    finish, points = {}, {}
    for row in weekend_results(weekend):
        key = driver_key(row.get("driver_id"))
        finish[key] = clean_text(row.get("finishing_status"))
        points[key] = row.get("points_earned")
    return finish, points


def chase_map(live):
    chase = {}
    for vehicle in (live or {}).get("vehicles") or []:
        driver = vehicle.get("driver") or {}
        did = driver_key(driver.get("driver_id"))
        chase[did] = bool(driver.get("is_in_chase"))
    return chase


def ineligible_map(race, points, session):
    mapping = {}
    if not race["points_race"]:
        return mapping
    for result in frame_records(session.results.results):
        did = driver_key(result.get("driver_id"))
        earned, laps = points.get(did), result.get("laps_completed")
        started = not is_blank(laps) and float(laps) > 0
        mapping[did] = started and not is_blank(earned) and float(earned) == 0
    return mapping
