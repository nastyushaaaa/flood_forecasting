from datetime import datetime

from application.open_meteo_api import get_forecast

def get(latitude: float, longitude: float, days : int) -> dict[datetime, float]:
    return get_forecast(latitude, longitude, days, "hourly")
