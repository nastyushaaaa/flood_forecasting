# PG-LSTM: прогноз уровня Амура у Хабаровска на 14 суток

Физически-информированная LSTM. Учится на истории уровней 4 постов и погоды бассейна, а физика
входит в неё двумя путями:
1. уравнение маршрутизации паводковой волны (Маскингам / Калинин–Милюков) само строит прогноз,
   а сеть учится его поправлять;
2. в функции потерь сеть штрафуется за нарушение этого уравнения и предельной скорости изменения уровня.

Тест на 2019–2026 годах (данные вне обучения), средняя абсолютная ошибка:

| | 1 сут | 7 сут | 14 сут |
|---|---|---|---|
| PG-LSTM | 4 см | 24 см | 42 см |
| инерционный прогноз | 8 см | 44 см | 71 см |

Подробности, графики и метрики — в блокноте.

## Что в папке

| Файл | Что это |
|---|---|
| `PG_LSTM_Хабаровск.ipynb` | блокнот: данные → физика → обучение → тест → прогноз |
| `pg_lstm.py` | модуль модели (создаётся блокнотом; правьте ячейку `%%writefile` в блокноте) |
| `model/pg_lstm_khabarovsk.pt` | обученная модель: ансамбль из 5 сетей + все настройки |
| `model/test_metrics.csv` | метрики всех моделей на тесте 2019–2026 по горизонтам 1…14 сут |
| `data/amur_khabarovsk_clean.csv` | чистый датасет 2002-01-01 — 2026-08-01 (описание колонок — в блокноте, п. 2.5) |
| `data/raw/` | исходники: выгрузки allrivers.info, NASA POWER, ERA5 по 9 точкам бассейна |
| `figures/` | все графики блокнота в PNG (для отчёта и презентации) |

## Запуск

- **Компьютер:** `pip install numpy pandas matplotlib requests torch jupyter`, открыть блокнот, Run All (около 15 минут на Mac M4).
- **Google Colab:** загрузить папку `amur_pg_lstm` на Google Диск, открыть блокнот, в первой ячейке раскомментировать две строки (`drive.mount` и `os.chdir`). Для скорости можно поставить `FAST = True`.

## Прогноз без блокнота

```python
import pandas as pd
import pg_lstm

model, cfg = pg_lstm.load_model('model/pg_lstm_khabarovsk.pt')
clean = pd.read_csv('data/amur_khabarovsk_clean.csv', parse_dates=['date'], index_col='date')
print(pg_lstm.forecast(clean, model, cfg))                      # от последней даты в таблице
print(pg_lstm.forecast(clean, model, cfg, date='2019-08-01'))   # от любой даты
```

Результат — таблица `date, horizon, level, level_low, level_high` (уровень в см, коридор 80%).

## Подключение к river_monitor

1. Скопировать `pg_lstm.py` → `river_monitor/pg_lstm.py`, `model/pg_lstm_khabarovsk.pt` → `river_monitor/data/`.
2. В `requirements.txt` добавить строку `torch>=2.0`.
3. В `forecast.py` добавить функцию (загрузчики уровней там уже есть):

```python
import pg_lstm


def get_pg_lstm_forecast() -> pd.DataFrame | None:
    """Прогноз PG-LSTM на 1…14 сут. Columns: date, horizon, level, level_low, level_high."""
    path = DATA_DIR / "pg_lstm_khabarovsk.pt"
    if not path.exists():
        return None
    model, cfg = pg_lstm.load_model(path)
    up = _load_upstream_levels()
    levels = {
        "khabarovsk":      _load_base_levels().set_index("date")["level"],
        "blagoveshchensk": up["amur-blagoveshensk"],
        "poyarkovo":       up["amur-poyarkovo"],
        "leninskoe":       up["amur-leninskoe"],
    }
    clean = pg_lstm.prepare_inputs(levels)   # очистка, флаги пропусков, ERA5 по бассейну, модель снега
    return pg_lstm.forecast(clean, model, cfg)
```

4. В `dashboard.py` вызвать `fc_module.get_pg_lstm_forecast()` рядом с `get_short_term_forecast_daily()`
   и нарисовать `level` с коридором `level_low…level_high`.

Что важно:
- нужны уровни всех 4 постов минимум за 60 последних суток; пропуски допустимы — модуль их восстановит;
- погоду ERA5 модуль скачивает сам (Open-Meteo, без ключа, ~9 запросов);
- прогноз «честный»: будущая погода не используется, поэтому прогноз погоды Open-Meteo не нужен.

## Как переобучить на свежих данных

1. Скачать новые выгрузки постов с allrivers.info и положить в `data/raw/` под именами
   `allrivers_khabarovsk.csv`, `allrivers_blagoveshchensk.csv`, `allrivers_poyarkovo.csv`, `allrivers_leninskoe.csv`.
2. Удалить `data/raw/era5_*.csv` и `data/raw/nasa_power_khabarovsk.csv` — блокнот скачает их заново до новой даты.
3. Run All и скопировать новый `model/pg_lstm_khabarovsk.pt` в проект.
