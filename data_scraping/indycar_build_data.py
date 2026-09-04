import argparse
from datetime import datetime

import pandas as pd
from raceindycar import get_season_events, get_session

from indycar_race_schema import (
    DATA_DIR, DRIVER_FIELDS, LAP_FIELDS, MIN_YEAR, RACE_FIELDS,
    clean_int, clean_text, enable_cache, race_file_stem,
)


def build_race_row(event):
    return {
        "race_id": clean_text(event.race_id),
        "name": clean_text(event.EventName),
        "date": clean_text(event.date),
        "track_type": clean_text(event.track_type),
        "actual_laps": clean_int(event.actual_laps),
    }


def build_driver_rows(race_id, results):
    return [{
        "race_id": race_id,
        "driver_id": clean_text(row.get("DriversID")),
        "driver": clean_text(row.get("FullName")),
        "car_number": clean_text(row.get("CarNumber")),
        "team": clean_text(row.get("Team")),
        "start": clean_int(row.get("PositionStart")),
        "finish": clean_int(row.get("PositionFinish")),
        "finish_status": clean_text(row.get("Status")),
        "points": clean_int(row.get("PointsEarned")),
        "laps": clean_int(row.get("LapsComplete")),
        "laps_led": clean_int(row.get("LapsLed")),
        "times_led": clean_int(row.get("TimesLed")),
        "fastest_lap_speed": clean_text(row.get("BestSpeed")),
        "avg_lap_speed": clean_text(row.get("SpeedAvg")),
        "pit_stops": clean_int(row.get("PitStops")),
    } for _, row in results.iterrows()]


def build_lap_rows(laps):
    rows = [{
        "driver_name": clean_text(row.get("Driver")),
        "car_number": clean_text(row.get("DriverNumber")),
        "team": clean_text(row.get("Team")),
        "lap_number": clean_int(row.get("LapNumber")),
        "position": clean_int(row.get("Position")),
        "lap_time": clean_text(row.get("LapTime")),
        "lap_speed": clean_text(row.get("LapSpeed")),
        "on_pit_road": clean_text(row.get("OnPitRoad")),
    } for _, row in laps.iterrows()]
    rows.sort(key=lambda row: (row["lap_number"] or 0, row["position"] or 999))
    return rows


def save_laps(year, race, laps):
    stem = race_file_stem(race["race_id"], race["name"])
    path = DATA_DIR / str(year) / "laps" / f"{stem}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(build_lap_rows(laps), columns=LAP_FIELDS).to_csv(path, index=False)


def save_year(year, races, drivers):
    year_dir = DATA_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(races, columns=RACE_FIELDS).to_csv(year_dir / "races.csv", index=False)
    pd.DataFrame(drivers, columns=DRIVER_FIELDS).to_csv(year_dir / "drivers.csv", index=False)


def scrape_year(year):
    schedule = get_season_events(year)
    races, drivers = [], []
    for _, event_row in schedule.sort_values("round_number").iterrows():
        race_id = event_row["race_id"]
        try:
            session = get_session(year, race_id, session="R").load(laps=True)
        except Exception as exc:
            print(f"  Failed {race_id} ({event_row['EventName']}): {exc}")
            continue
        race = build_race_row(session.event)
        races.append(race)
        drivers.extend(build_driver_rows(race["race_id"], session.results))
        save_laps(year, race, session.laps)
        print(f"  {race['race_id']} {race['name']}")
    return races, drivers


def main():
    parser = argparse.ArgumentParser(
        description="Build indycar_data/YYYY from raceindycar"
    )
    parser.add_argument("--year", type=int, help="Only scrape one season")
    parser.add_argument("--min-year", type=int, default=MIN_YEAR)
    args = parser.parse_args()

    enable_cache()
    years = [args.year] if args.year else range(args.min_year, datetime.now().year + 1)
    for year in years:
        print(f"{year}:")
        races, drivers = scrape_year(year)
        save_year(year, races, drivers)


if __name__ == "__main__":
    main()
