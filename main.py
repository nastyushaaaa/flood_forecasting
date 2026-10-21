from fastapi import FastAPI
from hourly_forecast import get_hourly_forecast, HourlyForecast

from dotenv import load_dotenv
load_dotenv(override=True)

app = FastAPI()

@app.get("/hourly_forecast")
def read_hourly_forecast(latitude : float, longitude : float, days: int) -> list[HourlyForecast]:
    return get_hourly_forecast(latitude, longitude, days)
