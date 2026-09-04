import argparse
import time
from datetime import datetime

from pynascar import NascarAPI, Race, Schedule

from nascar_race_schema import (
    CUP_SERIES_ID, DRIVER_FIELDS, LOOP_INT, MIN_YEAR, POINTS_RACE_TYPE,
    by_driver, chase_map, clean_int, clean_number, clean_text, driver_key,
    enable_cache, flag_status, fmt_pct, frame_records, ineligible_map,
    is_blank, normalize_oem, result_status_maps, track_miles, write_outputs,
)

REQUEST_DELAY_SECONDS = 0.5


def years_to_scrape(min_year, year):
    if year is not None:
        return [year]
    return list(range(max(min_year, MIN_YEAR), datetime.now().year + 1))


def season_schedule(year):
    return Schedule(year, CUP_SERIES_ID)


def match_schedule_row(schedule, race_id):
    target = int(race_id)
    hits = schedule.data[schedule.data["race_id"].astype(int) == target]
    if hits.empty:
        raise ValueError(f"No Cup race {race_id}")
    return hits.iloc[0].to_dict()


def finished_from(schedule):
    finished = schedule.get_finished_races()
    if finished.empty:
        return []
    return finished.sort_values("race_date").to_dict("records")


def collect_events(years, race_id=None):
    events = []
    for year in years:
        schedule = season_schedule(year)
        if race_id is None:
            events.extend((year, row) for row in finished_from(schedule))
            continue
        try:
            events.append((year, match_schedule_row(schedule, race_id)))
            return events
        except ValueError:
            continue
    if race_id is not None:
        raise ValueError(f"No Cup race {race_id} in {years[0]}+")
    return events


def load_session(year, race_id):
    return Race(year, CUP_SERIES_ID, int(race_id))


def load_feeds(year, race_id):
    api = NascarAPI()
    weekend = api.get_race_data(year, CUP_SERIES_ID, race_id) or {}
    live = api.get_advanced_driver_stat_data(year, CUP_SERIES_ID, race_id)
    laps = api.get_lap_time_data(year, CUP_SERIES_ID, race_id) or {}
    return weekend, live or {}, laps


def build_race_row(row):
    print(row)
    laps = row.get("scheduled_laps")
    return {
        "race_id": str(clean_int(row.get("race_id"))),
        "name": clean_text(row.get("race_name")),
        "date": clean_text(row.get("race_date")),
        "track": clean_text(row.get("track_name")),
        "track_miles": track_miles(row.get("scheduled_distance"), laps),
        "scheduled_laps": clean_number(laps),
        "scheduled_miles": clean_number(row.get("scheduled_distance")),
        "actual_laps": clean_number(row.get("actual_laps")),
        "actual_miles": clean_number(row.get("actual_distance")),
        "points_race": int(row.get("race_type_id") or 0) == POINTS_RACE_TYPE,
        "caution_laps": clean_number(row.get("number_of_caution_laps")),
    }


def driver_core(race, result):
    return {
        "race_id": race["race_id"],
        "driver_id": driver_key(result.get("driver_id")),
        "driver": clean_text(result.get("driver_name")),
        "car_number": clean_text(result.get("car_number")),
        "manufacturer": normalize_oem(result.get("manufacturer")),
        "start": clean_int(result.get("starting_position")),
        "finish": clean_int(result.get("finishing_position")),
    }


def apply_loop_stats(row, stats):
    if not stats:
        return
    for dest, source in LOOP_INT:
        value = clean_int(stats.get(source))
        if value != "":
            row[dest] = value
    arp = stats.get("avg_position")
    row["arp"] = "" if is_blank(arp) else f"{float(arp):.2f}"
    laps = stats.get("laps")
    row["pct_qp"] = fmt_pct(row.get("qp"), row.get("gfp_plus"))
    row["pct_t15"] = fmt_pct(row.get("t15_laps"), laps)
    row["pct_led"] = fmt_pct(row.get("laps_led"), laps)


def build_driver_rows(race, session, finish):
    stats = by_driver(session.driver_data.drivers)
    rows = []
    for result in frame_records(session.results.results):
        row = {field: "" for field in DRIVER_FIELDS}
        row.update(driver_core(race, result))
        apply_loop_stats(row, stats.get(row["driver_id"]))
        row["finish_status"] = finish.get(row["driver_id"], "")
        rows.append(row)
    rows.sort(key=lambda row: row["finish"] if row["finish"] != "" else 999)
    return rows


def flag_by_lap(laps_payload):
    mapping = {}
    for row in (laps_payload or {}).get("flags") or []:
        lap = clean_int(row.get("LapsCompleted"))
        if lap != "":
            mapping[lap] = flag_status(row.get("FlagState"))
    return mapping


def is_race_lap(lap):
    number = clean_int(lap.get("Lap"))
    return number != "" and number != 0 and not is_blank(lap.get("LapTime"))


def race_laps_for(driver):
    return [lap for lap in driver.get("Laps") or [] if is_race_lap(lap)]


def lap_identity(driver, lap):
    time = lap.get("LapTime")
    return {
        "driver_name": clean_text(driver.get("FullName")),
        "driver_id": driver_key(driver.get("NASCARDriverID")),
        "manufacturer": clean_text(driver.get("Manufacturer")),
        "car_number": clean_text(driver.get("Number")),
        "lap_number": clean_int(lap.get("Lap")),
        "running_position": clean_int(lap.get("RunningPos")),
        "lap_speed": clean_text(lap.get("LapSpeed")),
        "lap_time": "" if is_blank(time) else f"{float(time):.3f}",
    }


def apply_lap_context(row, flags, context):
    info = context.get(row["driver_id"], {})
    row["team"] = info.get("team", "")
    row["playoffs"] = info.get("playoffs", False)
    row["points_ineligible"] = info.get("ineligible", False)
    row["starting_position"] = info.get("start", "")
    row["finish_position"] = info.get("finish", "")
    row["statuses"] = flags.get(row["lap_number"], "")


def result_context(session, chase, ineligible):
    context = {}
    for result in frame_records(session.results.results):
        did = driver_key(result.get("driver_id"))
        context[did] = {
            "team": clean_text(result.get("team")),
            "start": clean_int(result.get("starting_position")),
            "finish": clean_int(result.get("finishing_position")),
            "playoffs": chase.get(did, False),
            "ineligible": ineligible.get(did, False),
        }
    return context


def build_lap_rows(laps_payload, context):
    flags = flag_by_lap(laps_payload)
    rows = []
    for driver in (laps_payload or {}).get("laps") or []:
        for lap in race_laps_for(driver):
            row = lap_identity(driver, lap)
            apply_lap_context(row, flags, context)
            rows.append(row)
    rows.sort(key=lambda row: (row["lap_number"] or 0, row["running_position"] or 999))
    return rows


def rows_from_feeds(schedule_row, session, weekend, live, laps):
    race = build_race_row(schedule_row)
    finish, points = result_status_maps(weekend)
    drivers = build_driver_rows(race, session, finish)
    context = result_context(
        session, chase_map(live), ineligible_map(race, points, session),
    )
    return race, drivers, build_lap_rows(laps, context)


def scrape_and_save(year, schedule_row):
    if year < MIN_YEAR:
        raise ValueError(f"Year {year} is below {MIN_YEAR}")
    enable_cache()
    race_id = int(schedule_row["race_id"])
    race, drivers, lap_rows = rows_from_feeds(
        schedule_row, load_session(year, race_id), *load_feeds(year, race_id),
    )
    out_dir, written, path, laps_written = write_outputs(
        race, drivers, lap_rows,
    )
    return {
        "race": race, "drivers": drivers, "out_dir": out_dir,
        "written": written, "laps_path": path, "laps_written": laps_written,
    }


def print_dry_run(events, years):
    print(f"Dry run: {len(events)} Cup races from {years[0]}+")
    for year, row in events:
        print(f"{year} {row.get('race_id')} {row.get('race_name')}")
    return {"events": events, "wrote": 0, "skipped": 0, "failed": []}


def scrape_one(year, row, index, total):
    result = scrape_and_save(year, row)
    race = result["race"]
    action = "Wrote" if result["written"] else "Skipped existing"
    laps_action = "wrote laps" if result["laps_written"] else "laps exists"
    print(
        f"[{index}/{total}] {action} {race['race_id']} "
        f"({race['name']}) -> {result['out_dir']}/ "
        f"[{laps_action}: {result['laps_path'].name}]"
    )
    return result


def try_scrape_one(event, index, total, failed):
    year, row = event
    try:
        return scrape_one(year, row, index, total)["written"]
    except Exception as exc:
        failed.append((year, row.get("race_id"), str(exc)))
        print(f"[{index}/{total}] Failed {row.get('race_id')}: {exc}")
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
    return {"events": events, "wrote": wrote, "skipped": skipped, "failed": failed}


def run_pipeline(min_year=MIN_YEAR, dry_run=False, year=None, race_id=None):
    enable_cache()
    years = years_to_scrape(min_year, year)
    events = collect_events(years, race_id)
    if dry_run:
        return print_dry_run(events, years)
    return scrape_all_events(events)


def main():
    parser = argparse.ArgumentParser(
        description="Import Cup races from pynascar into nascar_data/YYYY"
    )
    parser.add_argument("--min-year", type=int, default=MIN_YEAR)
    parser.add_argument("--year", type=int, help="Only scrape one season")
    parser.add_argument("--race-id", type=int, help="Only scrape one race")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_pipeline(
        min_year=max(args.min_year, MIN_YEAR),
        dry_run=args.dry_run,
        year=args.year,
        race_id=args.race_id,
    )


if __name__ == "__main__":
    main()
