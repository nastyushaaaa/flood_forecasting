import requests

def get_forecast(latitude: float, longitude: float, days : int, freq : str):
    session = requests.Session()

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        f"{freq}": "temperature_2m",
        "timezone": "auto",
        "forecast_days": days
    }

    response = session.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    hourly_data = data["hourly"]
    forecasts = {}
    for i in range(len(hourly_data["time"])):
        forecasts[hourly_data["time"][i]] = hourly_data["temperature_2m"][i]

    return forecasts