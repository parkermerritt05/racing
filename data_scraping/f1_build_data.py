import argparse
import time
from datetime import datetime

import fastf1
import pandas as pd

from f1_race_schema import (
    MIN_YEAR, RACE_SESSION, clean_flag, clean_int, clean_points, clean_text,
    enable_cache, format_date, format_lap_time, format_race_time, is_blank,
    make_race_id, timedelta_ms, write_outputs,
)

REQUEST_DELAY_SECONDS = 0.5
RACE_SESSION_NAME = "Race"


def load_race_session(year, round_number):
    session = fastf1.get_session(year, round_number, RACE_SESSION)
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    return session


def total_laps(session):
    lap_col = session.laps["LapNumber"] if len(session.laps) else []
    from_laps = int(lap_col.max()) if len(lap_col) else 0
    from_results = session.results["Laps"].max()
    result_laps = 0 if is_blank(from_results) else int(from_results)
    return max(from_laps, result_laps)


def build_race_row(session):
    event = session.event
    year = int(event.year)
    round_number = int(event["RoundNumber"])
    return {
        "race_id": str(make_race_id(year, round_number)),
        "name": clean_text(event.get("EventName")),
        "official_name": clean_text(event.get("OfficialEventName")),
        "date": format_date(session.date),
        "location": clean_text(event.get("Location")),
        "country": clean_text(event.get("Country")),
        "round": round_number,
        "total_laps": total_laps(session),
    }


def driver_id_of(result):
    return clean_text(result.get("DriverId")) or clean_text(
        result.get("Abbreviation")
    )


def laps_for_car(laps, number):
    numbers = laps["DriverNumber"].astype(str)
    return laps[numbers == str(number)]


def pit_stop_count(laps):
    if laps.empty or "PitInTime" not in laps.columns:
        return 0
    return int(laps["PitInTime"].notna().sum())


def best_lap(laps):
    valid = laps.dropna(subset=["LapTime"])
    if valid.empty:
        return None
    return valid.loc[valid["LapTime"].idxmin()]


def driver_result_fields(race, result):
    return {
        "race_id": race["race_id"],
        "driver_id": driver_id_of(result),
        "abbreviation": clean_text(result.get("Abbreviation")),
        "driver": clean_text(result.get("FullName")),
        "car_number": clean_text(result.get("DriverNumber")),
        "team": clean_text(result.get("TeamName")),
        "start": clean_int(result.get("GridPosition")),
        "finish": clean_int(result.get("Position")),
        "status": clean_text(result.get("Status")),
        "points": clean_points(result.get("Points")),
        "laps": clean_int(result.get("Laps")),
        "time": format_race_time(result.get("Time")),
    }


def driver_lap_fields(laps):
    best = best_lap(laps)
    fastest_lap = "" if best is None else clean_int(best.get("LapNumber"))
    fastest_time = "" if best is None else format_lap_time(best.get("LapTime"))
    return {
        "pit_stops": pit_stop_count(laps),
        "fastest_lap": fastest_lap,
        "fastest_lap_time": fastest_time,
    }


def driver_row(race, result, laps):
    return {**driver_result_fields(race, result), **driver_lap_fields(laps)}


def build_lap_row(lap, driver):
    lap_time = lap.get("LapTime")
    ms = timedelta_ms(lap_time)
    pitted = not is_blank(lap.get("PitInTime"))
    return {
        "driver_id": driver["driver_id"],
        "abbreviation": driver["abbreviation"],
        "car_number": driver["car_number"],
        "team": driver["team"],
        "lap_number": clean_int(lap.get("LapNumber")),
        "position": clean_int(lap.get("Position")),
        "lap_time": format_lap_time(lap_time),
        "lap_time_ms": "" if ms is None else ms,
        "stint": clean_int(lap.get("Stint")),
        "compound": clean_text(lap.get("Compound")),
        "tyre_life": clean_int(lap.get("TyreLife")),
        "pit_in": int(pitted),
        "deleted": clean_flag(lap.get("Deleted")),
        "is_accurate": clean_flag(lap.get("IsAccurate")),
    }


def lap_sort_key(row):
    lap = row["lap_number"] or 0
    position = row["position"] or 999
    return (lap, position)


def collect_rows(session, race):
    results = session.results.sort_values("Position", na_position="last")
    drivers, lap_rows = [], []
    for _, result in results.iterrows():
        laps = laps_for_car(session.laps, result.get("DriverNumber"))
        row = driver_row(race, result, laps)
        drivers.append(row)
        lap_rows.extend(build_lap_row(lap, row) for lap in laps.to_dict("records"))
    lap_rows.sort(key=lap_sort_key)
    return drivers, lap_rows


def scrape_and_save(year, round_number):
    if year < MIN_YEAR:
        raise ValueError(f"Year {year} is below {MIN_YEAR}")
    session = load_race_session(year, round_number)
    race = build_race_row(session)
    drivers, lap_rows = collect_rows(session, race)
    out_dir, written, path, laps_written = write_outputs(
        race, drivers, lap_rows
    )
    return {
        "race": race,
        "drivers": drivers,
        "out_dir": out_dir,
        "written": written,
        "laps_path": path,
        "laps_written": laps_written,
    }


def years_to_scrape(min_year, year):
    if year is not None:
        return [year]
    current = datetime.now().year
    return list(range(max(min_year, MIN_YEAR), current + 1))


def race_session_date(event):
    for index in range(1, 6):
        if event.get(f"Session{index}") == RACE_SESSION_NAME:
            return event.get(f"Session{index}Date")
    return event.get("EventDate")


def is_future_event(event):
    date = race_session_date(event)
    if date is None or pd.isna(date):
        return False
    return pd.Timestamp(date).date() > datetime.now().date()


def is_supported_event(event):
    if not bool(event.get("F1ApiSupport", False)):
        return False
    round_number = int(event["RoundNumber"])
    return round_number >= 1 and not is_future_event(event)


def season_events(year, round_number=None):
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    events = []
    for _, event in schedule.iterrows():
        if not is_supported_event(event):
            continue
        event_round = int(event["RoundNumber"])
        if round_number is not None and event_round != round_number:
            continue
        events.append(event)
    return events


def collect_events(years, round_number=None):
    events = []
    for year in years:
        for event in season_events(year, round_number):
            events.append((year, int(event["RoundNumber"]), event["EventName"]))
    return events


def scrape_one(year, round_number, name, index, total):
    result = scrape_and_save(year, round_number)
    race = result["race"]
    action = "Wrote" if result["written"] else "Skipped existing"
    laps_action = "wrote laps" if result["laps_written"] else "laps exists"
    print(
        f"[{index}/{total}] {action} {race['race_id']} "
        f"({name}) -> {result['out_dir']}/ "
        f"[{laps_action}: {result['laps_path'].name}]"
    )
    return result


def print_dry_run(events, years):
    print(f"Dry run: {len(events)} GPs from {years[0]}+")
    for event_year, event_round, name in events:
        print(f"{event_year} R{event_round} {name}")
    return {"events": events, "wrote": 0, "skipped": 0, "failed": []}


def try_scrape_one(event, index, total, failed):
    event_year, event_round, name = event
    try:
        result = scrape_one(event_year, event_round, name, index, total)
        return result["written"]
    except Exception as exc:
        failed.append((event_year, event_round, str(exc)))
        print(f"[{index}/{total}] Failed {event_year} R{event_round}: {exc}")
        return None


def scrape_all_events(events):
    wrote = skipped = 0
    failed = []
    total = len(events)
    for index, event in enumerate(events, start=1):
        written = try_scrape_one(event, index, total, failed)
        if written is True:
            wrote += 1
        elif written is False:
            skipped += 1
        if index < total:
            time.sleep(REQUEST_DELAY_SECONDS)
    print(
        f"Done: {wrote} wrote, {skipped} skipped, {len(failed)} failed "
        f"({total} total)"
    )
    return {
        "events": events, "wrote": wrote, "skipped": skipped, "failed": failed,
    }


def run_pipeline(
    min_year=MIN_YEAR, dry_run=False, year=None, round_number=None
):
    enable_cache()
    years = years_to_scrape(min_year, year)
    events = collect_events(years, round_number)
    if dry_run:
        return print_dry_run(events, years)
    return scrape_all_events(events)


def main():
    parser = argparse.ArgumentParser(
        description="Import F1 race weekends from FastF1 into f1_data/YYYY"
    )
    parser.add_argument("--min-year", type=int, default=MIN_YEAR)
    parser.add_argument("--year", type=int, help="Only scrape one season")
    parser.add_argument("--round", type=int, help="Only scrape one round")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.round is not None and args.year is None:
        raise SystemExit("--round requires --year")
    run_pipeline(
        min_year=max(args.min_year, MIN_YEAR),
        dry_run=args.dry_run,
        year=args.year,
        round_number=args.round,
    )


if __name__ == "__main__":
    main()
