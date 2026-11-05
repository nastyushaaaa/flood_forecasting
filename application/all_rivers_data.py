from datetime import date
import csv

import common.errors as errors

river_data_paths : dict[str, str] = {
    "test_river": "tests/test_river_trimmed.csv",
    "amur": "data/amur/blagoveshensk.csv",
    "test_unsorted_river" : "tests/test_unsorted_river.csv"
}

def verify_river_name(river_name : str) -> None:
    if (river_name not in river_data_paths): raise errors.CsvReadError(f"No table for this name: {river_name}")
    try: f = open(river_data_paths[river_name])
    except FileNotFoundError: raise errors.CsvReadError(f"Table file missing for {river_name}: {river_data_paths[river_name]}")

def get_water_level(river_name : str, start_date : date, end_date : date) -> dict[date, float]:
    verify_river_name(river_name)

    out: dict[date, float] = {}
    with open(river_data_paths[river_name], newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if fieldnames != ["date", "level_cm"]: raise errors.CsvReadError(f"Wrong tale structure: {fieldnames}")
        for row in reader:
            try:
                dt = date.fromisoformat(row["date"])
                value = float(row["level_cm"])
            except (KeyError, TypeError, ValueError):
                continue
            if (dt >= start_date and dt <= end_date): out[dt] = value
    return dict(sorted(out.items()))