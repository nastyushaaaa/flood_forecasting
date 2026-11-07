from fastapi import FastAPI, HTTPException

from datetime import date, datetime
from dotenv import load_dotenv

from backend.external_api import open_meteo_api
from backend.application import all_rivers_data
from backend.common import errors

load_dotenv(override=True)

app = FastAPI()

@app.get("/temperature-forecast/hourly")
def get_temperature_forecast_hourly(latitude : float, longitude : float, days: int) -> dict[datetime, float] | None:
    return open_meteo_api.get_forecast(latitude, longitude, days, "hourly")

@app.get("/temperature-forecast/daily")
def get_temperature_forecast_daily(latitude : float, longitude : float, days: int) -> dict[datetime, float] | None:
    return open_meteo_api.get_forecast(latitude, longitude, days, "daily")

@app.get("/water-level/daily")
def get_water_levels(river_name: str, start_date: date, end_date: date) -> dict[date, float] | None:
    if start_date >= end_date: raise HTTPException(status_code=400, detail="start must be before end")
    if (start_date >= date.today()): raise errors.UnavailableDate(f"Starting date cant be in the future: {start_date}")
    if (end_date < start_date): raise errors.UnavailableDate(f"End date should be before starting date: {end_date} < {start_date}")
    return all_rivers_data.get_water_level(river_name, start_date, end_date)
