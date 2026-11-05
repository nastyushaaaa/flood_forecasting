from fastapi import FastAPI, HTTPException

from datetime import date, datetime
from dotenv import load_dotenv

import controllers.water_levels
import controllers.temperature_forecast_daily

load_dotenv(override=True)

app = FastAPI()

@app.get("/temperature-forecast/hourly")
def get_temperature_forecast_hourly(latitude : float, longitude : float, days: int) -> dict[datetime, float] | None:
    return controllers.temperature_forecast_daily.get(latitude, longitude, days)

@app.get("/temperature-forecast/daily")
def get_temperature_forecast_daily(latitude : float, longitude : float, days: int) -> dict[datetime, float] | None:
    return controllers.temperature_forecast_daily.get(latitude, longitude, days)

@app.get("/water-level/daily")
def get_water_levels(river_name: str, start: date, end: date) -> dict[date, float] | None:
    if start >= end: raise HTTPException(status_code=400, detail="start must be before end")
    controllers.water_levels.get(river_name, start, end)
