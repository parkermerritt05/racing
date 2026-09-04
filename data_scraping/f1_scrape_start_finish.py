import argparse
import csv
import logging
import time
from pathlib import Path

import fastf1
import pandas as pd
from fastf1.ergast import Ergast
from fastf1.exceptions import ErgastInvalidRequestError

CACHE_DIR = Path(".cache/fastf1")
OUTPUT_PATH = Path("f1_data/f1_data.csv")
PAGE_LIMIT = 100
MISSING_INT = -1
REQUEST_DELAY_SECONDS = 0.5
RETRY_WAIT_SECONDS = 20
MAX_RETRIES = 6

FIELDS = [
    "Season", "Race", "Track", "Name", "Date", "Country",
    "Finish", "Start", "Car", "Driver", "Constructor",
    "Pts", "Laps", "Status", "Win",
]


def enable_cache():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))


def make_ergast():
    return Ergast(result_type="pandas", auto_cast=True, limit=PAGE_LIMIT)


def is_blank(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def format_date(value):
    if is_blank(value):
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]


def clean_int(value):
    if is_blank(value):
        return ""
    number = int(value)
    if number == MISSING_INT:
        return ""
    return number


def clean_text(value):
    if is_blank(value):
        return ""
    return str(value).strip()


def clean_points(value):
    if is_blank(value):
        return ""
    number = float(value)
    return int(number) if number.is_integer() else number


def driver_name(result):
    given = clean_text(result.get("givenName"))
    family = clean_text(result.get("familyName"))
    return f"{given} {family}".strip()


def race_fields(race):
    return {
        "Season": race.season,
        "Race": race.round,
        "Track": race.circuitName,
        "Name": race.raceName,
        "Date": format_date(race.raceDate),
        "Country": race.country,
    }


def result_row(race, result):
    finish = clean_int(result.get("position"))
    return {
        **race_fields(race),
        "Finish": finish,
        "Start": clean_int(result.get("grid")),
        "Car": clean_int(result.get("number")),
        "Driver": driver_name(result),
        "Constructor": clean_text(result.get("constructorName")),
        "Pts": clean_points(result.get("points")),
        "Laps": clean_int(result.get("laps")),
        "Status": clean_text(result.get("status")),
        "Win": int(finish == 1),
    }


def rows_from_page(page):
    rows = []
    races = page.description.itertuples(index=False)
    for race, results in zip(races, page.content):
        records = results.to_dict("records")
        rows.extend(result_row(race, item) for item in records)
    return rows


def is_rate_limit(exc):
    return "Too Many Requests" in str(exc)


def fetch_with_retry(fetch):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch()
        except ErgastInvalidRequestError as exc:
            if not is_rate_limit(exc) or attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_WAIT_SECONDS * attempt)


def next_page(page):
    time.sleep(REQUEST_DELAY_SECONDS)
    try:
        return fetch_with_retry(page.get_next_result_page)
    except ValueError:
        return None


def fetch_all_results(ergast):
    page = fetch_with_retry(ergast.get_race_results)
    rows = rows_from_page(page)
    total = page.total_results
    print(f"Fetching {total} GP results...")
    while True:
        page = next_page(page)
        if page is None:
            break
        rows.extend(rows_from_page(page))
        if len(rows) % 1000 < PAGE_LIMIT:
            print(f"  {len(rows)}/{total}", flush=True)
    return rows


def sort_rows(rows):
    return sorted(
        rows,
        key=lambda row: (
            row["Season"] or 0,
            row["Race"] or 0,
            row["Finish"] if row["Finish"] != "" else 999,
        ),
    )


def write_output(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows, path):
    seasons = {row["Season"] for row in rows}
    races = {(row["Season"], row["Race"]) for row in rows}
    grid_zero = sum(1 for row in rows if row["Start"] == 0)
    print(
        f"Wrote {len(rows)} GP results, {len(races)} races, "
        f"{len(seasons)} seasons ({min(seasons)}-{max(seasons)}) "
        f"to {path} ({grid_zero} grid-0 starts)"
    )


def run_pipeline(dry_run=False, output_path=OUTPUT_PATH):
    enable_cache()
    fastf1.set_log_level("ERROR")
    logging.getLogger("requests_cache").setLevel(logging.ERROR)
    ergast = make_ergast()
    if dry_run:
        page = ergast.get_race_results()
        print(
            f"Dry run: {page.total_results} GP results available, "
            f"{len(page.content)} races on first page (sprints excluded)"
        )
        return
    rows = sort_rows(fetch_all_results(ergast))
    write_output(rows, output_path)
    summarize(rows, output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape F1 GP start/finish results via FastF1 (no sprints)"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run, output_path=args.output)


if __name__ == "__main__":
    main()
