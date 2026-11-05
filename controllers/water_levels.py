from datetime import date
import common.errors as errors

from application.all_rivers_data import get_water_level

def get(river_name : str, start_date : date, end_date : date) -> dict[date, float]:
    if (start_date >= date.today()): raise errors.UnavailableDate(f"Starting date cant be in the future: {start_date}")
    if (end_date < start_date): raise errors.UnavailableDate(f"End date should be before starting date: {end_date} < {start_date}")
    return get_water_level(river_name, start_date, end_date)