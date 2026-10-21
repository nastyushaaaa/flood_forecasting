import requests
from dataclasses import dataclass

@dataclass
class HourlyForecast:
    """Represents a single hour of weather forecast."""
    time: str
    temperature_2m: float
    relative_humidity_2m: float
    precipitation: float
    wind_speed_10m: float

def get_hourly_forecast(latitude: float, longitude: float, days : int) -> list[HourlyForecast]:
    """
    Fetches hourly weather forecast from Open-Meteo for the given coordinates.
    Returns a list of HourlyForecast objects.
    """
    session = requests.Session()

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "timezone": "auto",
        "forecast_days": days
    }

    response = session.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    hourly_data = data["hourly"]
    forecasts = []
    for i in range(len(hourly_data["time"])):
        forecast = HourlyForecast(
            time=hourly_data["time"][i],
            temperature_2m=hourly_data["temperature_2m"][i],
            relative_humidity_2m=hourly_data["relative_humidity_2m"][i],
            precipitation=hourly_data["precipitation"][i],
            wind_speed_10m=hourly_data["wind_speed_10m"][i],
        )
        forecasts.append(forecast)

    return forecasts