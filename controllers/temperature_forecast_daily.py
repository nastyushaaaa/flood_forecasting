from datetime import datetime

from external_api.open_meteo_api import get_forecast

def get(latitude: float, longitude: float, days : int) -> dict[datetime, float]:
    return get_forecast(latitude, longitude, days, "daily")