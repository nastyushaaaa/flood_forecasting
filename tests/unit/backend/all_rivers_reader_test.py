import pytest
from datetime import date
import csv

from src.application.all_rivers_data import get_water_level
from src.common.errors import CsvReadError, UnavailableDate

def read_csv_helper(path : str) -> dict[date, float]:
    out: dict[date, float] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                dt = date.fromisoformat(row["date"])
                value = float(row["level_cm"])
            except (KeyError, TypeError, ValueError):
                continue
            out[dt] = value
    return out
"""
def test_function_existence():
    get_water_level()

def test_function_returns_dict():
    water_levels : dict[datetime, float] = get_water_level()

def test_function_returns_nonempty_dict():
    water_levels : dict[datetime, float] = get_water_level()
    assert len(water_levels) > 0

def test_function_reads_csv():
    test_csv = read_csv_helper("tests/test.csv")
    water_levels : dict[datetime, float] = get_water_level()
    assert water_levels == test_csv

def test_function_reads_any_csv():
    path = "tests/test.csv"
    test_csv = read_csv_helper(path)
    water_levels : dict[date, float] = get_water_level(path)
    assert water_levels == test_csv

def test_funtion_reads_by_river_name():
    river_name = "test_river"
    test_csv = read_csv_helper(f"data/{river_name}")
    water_levels : dict[date, float] = get_water_level(river_name)
    assert water_levels == test_csv

def test_funtion_throws_on_missing_name():
    river_name = "test_missing_name"
    with pytest.raises(CsvReadError): get_water_level(river_name)

def test_funtion_returns_from_date():
    river_name = "test_river"
    test_csv = read_csv_helper(f"tests/{river_name}_trimmed.csv")
    start_date = date.fromisoformat("2026-01-01")
    water_levels : dict[date, float] = get_water_level(river_name, start_date)
    assert test_csv == water_levels


def test_funtion_handles_late_start_date():
    river_name = "test_river"
    start_date = date.fromisoformat("2027-01-01")
    with pytest.raises(UnavailableDate): get_water_level(river_name, start_date)

def test_funtion_returns_in_range():
    river_name = "test_river"
    test_csv = read_csv_helper(f"tests/{river_name}_trimmed.csv")
    start_date = date.fromisoformat("2026-01-01")
    end_date = date.fromisoformat("2026-11-01")
    water_levels : dict[date, float] = get_water_level(river_name, start_date, end_date)
    assert test_csv == water_levels
"""
"""
def test_function_handles_reversed_date():
    river_name = "test_river"
    end_date = date.fromisoformat("2026-01-01")
    start_date = date.fromisoformat("2026-11-01")
    with pytest.raises(UnavailableDate): get_water_level(river_name, start_date, end_date)

def test_function_is_empty_when_range_has_no_matches():
    river_name = "test_river"
    test_csv = read_csv_helper(f"tests/{river_name}_trimmed.csv")
    start_date = date.fromisoformat("2021-01-01")
    end_date = date.fromisoformat("2022-11-01")
    water_levels : dict[date, float] = get_water_level(river_name, start_date, end_date)
    assert len(water_levels) == 0

def test_function_returns_sorted_by_date():
    river_name = "test_unsorted_river"
    start_date = date.fromisoformat("2021-01-01")
    end_date = date.fromisoformat("2022-11-01")
    water_levels : dict[date, float] = get_water_level(river_name, start_date, end_date)

    old_date : date = date.fromisoformat("1900-01-01")
    is_non_decreasing = True
    for new_date in water_levels.keys():
        if new_date >= old_date:
            old_date = new_date
        else:
            is_non_decreasing = False
            break
    assert is_non_decreasing


def test_function_throws_on_missing_file():
    river_name = "test_nonexistent_river"
    start_date = date.fromisoformat("2026-01-01")
    end_date = date.fromisoformat("2026-11-01")
    with pytest.raises(CsvReadError): get_water_level(river_name, start_date, end_date)

"""
def test_function_throws_on_wrong_columns():
    river_name = "test_wrong_table"
    start_date = date.fromisoformat("2026-01-01")
    end_date = date.fromisoformat("2026-11-01")
    with pytest.raises(CsvReadError): get_water_level(river_name, start_date, end_date)