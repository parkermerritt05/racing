import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from raceindycar import get_season_events, get_session

from indycar_race_schema import clean_int, clean_text, enable_cache

MIN_YEAR = 1996
OUTPUT_PATH = Path("indycar_data/indycar_data.csv")
FIELDS = [
    "Season", "Race", "Track", "Name", "Date", "Surface", "Finish", "Start",
    "Car", "Driver", "Team", "Pts", "Laps", "Led", "Status", "Win",
]


def build_result_rows(year, round_number, results):
    rows = []
    for _, row in results.iterrows():
        finish = clean_int(row.get("PositionFinish"))
        rows.append({
            "Season": year,
            "Race": round_number,
            "Track": clean_text(row.get("RaceName")),
            "Name": clean_text(row.get("RaceName")),
            "Date": clean_text(row.get("Date")),
            "Surface": clean_text(row.get("TrackType")),
            "Finish": finish,
            "Start": clean_int(row.get("PositionStart")),
            "Car": clean_text(row.get("CarNumber")),
            "Driver": clean_text(row.get("FullName")),
            "Team": clean_text(row.get("Team")),
            "Pts": clean_int(row.get("PointsEarned")),
            "Laps": clean_int(row.get("LapsComplete")),
            "Led": clean_int(row.get("LapsLed")),
            "Status": clean_text(row.get("Status")),
            "Win": 1 if finish == 1 else 0,
        })
    return rows


def scrape_year(year):
    schedule = get_season_events(year)
    rows = []
    for _, event_row in schedule.sort_values("round_number").iterrows():
        try:
            session = get_session(year, event_row["race_id"], session="R").load()
        except Exception as exc:
            print(f"  Failed round {event_row['round_number']}: {exc}")
            continue
        rows.extend(build_result_rows(year, event_row["round_number"], session.results))
        print(f"  round {event_row['round_number']} {event_row['EventName']}")
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Build indycar_data.csv from raceindycar (1996+)"
    )
    parser.add_argument("--min-year", type=int, default=MIN_YEAR)
    args = parser.parse_args()

    enable_cache()
    rows = []
    for year in range(args.min_year, datetime.now().year + 1):
        print(f"{year}:")
        rows.extend(scrape_year(year))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=FIELDS).to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(rows)} results to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
