from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from hourly_forecast import get_hourly_forecast, HourlyForecast

from dotenv import load_dotenv
load_dotenv(override=True)

app = FastAPI()

@app.get("/hourly_forecast")
def read_hourly_forecast(latitude : float, longitude : float, days: int) -> list[HourlyForecast]:
    return get_hourly_forecast(latitude, longitude, days)


# Сайт (папка frontend) открывается по адресу http://127.0.0.1:8000/
# Подключаем последним: эндпоинты API, объявленные выше, имеют приоритет.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

