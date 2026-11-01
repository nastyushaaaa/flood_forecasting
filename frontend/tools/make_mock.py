"""Готовит тестовые JSON-файлы для фронтенда (папка frontend/mock).

Пока бэкенд не отдаёт данные, сайт читает эти файлы. Формат файлов = формат будущего API
(см. frontend/README.md, раздел «Контракт API»), поэтому потом меняется только адрес запроса.

Откуда данные:
- уровни 4 постов на Амуре, прогноз и климатическая норма — настоящие, из папки amur_pg_lstm;
- остальные посты (Лена, Обь, Кубань …) и все пороги — условные, для демонстрации дизайна.

Запуск из корня репозитория:  python frontend/tools/make_mock.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]          # корень репозитория
MODEL_DIR = ROOT / 'amur_pg_lstm'
OUT_DIR = ROOT / 'frontend' / 'mock'
sys.path.insert(0, str(MODEL_DIR))
import pg_lstm  # noqa: E402  (модуль модели лежит в amur_pg_lstm)

clean = pd.read_csv(MODEL_DIR / 'data' / 'amur_khabarovsk_clean.csv', parse_dates=['date'], index_col='date')
today = clean.index[-1]                              # «сегодня» = последняя дата в данных


def save(name, data):
    """Записывает словарь в frontend/mock/<name>.json."""
    path = OUT_DIR / f'{name}.json'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    print('записан', path.relative_to(ROOT))


def series_to_list(s):
    """pd.Series с датами в индексе -> [{"date": "2026-08-01", "level": 405.0}, ...]."""
    return [{'date': d.strftime('%Y-%m-%d'), 'level': round(float(v), 1)} for d, v in s.dropna().items()]


# --- 1. Посты и текущие уровни --------------------------------------------------------------
def last_level(gauge):
    return round(float(clean[f'level_{gauge}'].iloc[-1]), 1)


# Пороги (watch = готовность/критический, flood = выход на пойму, danger = опасный) — условные!
stations = [
    # настоящие уровни из датасета модели
    dict(id='khabarovsk', name='Хабаровск', river='Амур', okrug='ДФО', lat=48.48, lon=135.07,
         level=last_level('khabarovsk'), thresholds=dict(watch=300, flood=470, danger=550)),
    dict(id='blagoveshchensk', name='Благовещенск', river='Амур', okrug='ДФО', lat=50.26, lon=127.53,
         level=last_level('blagoveshchensk'), thresholds=dict(watch=450, flood=600, danger=700)),
    dict(id='poyarkovo', name='Поярково', river='Амур', okrug='ДФО', lat=49.62, lon=128.68,
         level=last_level('poyarkovo'), thresholds=dict(watch=500, flood=650, danger=750)),
    dict(id='leninskoe', name='Ленинское', river='Амур', okrug='ДФО', lat=47.93, lon=132.62,
         level=last_level('leninskoe'), thresholds=dict(watch=650, flood=760, danger=850)),
    # демонстрационные посты из дизайн-макета
    dict(id='lensk', name='Ленск', river='Лена', okrug='ДФО', lat=60.72, lon=114.93,
         level=1384, thresholds=dict(watch=1100, flood=1250, danger=1350)),
    dict(id='yakutsk', name='Якутск', river='Лена', okrug='ДФО', lat=62.03, lon=129.73,
         level=812, thresholds=dict(watch=800, flood=900, danger=1000)),
    dict(id='barnaul', name='Барнаул', river='Обь', okrug='СФО', lat=53.35, lon=83.78,
         level=436, thresholds=dict(watch=420, flood=450, danger=472)),
    dict(id='kemerovo', name='Кемерово', river='Томь', okrug='СФО', lat=55.36, lon=86.09,
         level=312, thresholds=dict(watch=600, flood=700, danger=800)),
    dict(id='novokuznetsk', name='Новокузнецк', river='Томь', okrug='СФО', lat=53.76, lon=87.12,
         level=254, thresholds=dict(watch=450, flood=550, danger=650)),
    dict(id='krasnodar', name='Краснодар', river='Кубань', okrug='ЮФО', lat=45.04, lon=38.98,
         level=-137, thresholds=dict(watch=0, flood=30, danger=50)),
    dict(id='sochi', name='Сочи', river='Сочи', okrug='ЮФО', lat=43.59, lon=39.72,
         level=None, thresholds=dict(watch=150, flood=200, danger=250)),   # None = нет данных
]
for st in stations:
    # дата замера: у Сочи — устаревшая, чтобы показать статус «нет данных»
    st['measured_at'] = (today - pd.Timedelta(days=2) if st['level'] is None else today).strftime('%Y-%m-%d')

save('stations', {
    'updated_at': f'{today:%Y-%m-%d}T10:30:00+03:00',
    'next_update_at': f'{today:%Y-%m-%d}T20:00:00+03:00',
    'stations': stations,
})

# --- 2. Краткосрочный прогноз PG-LSTM для Хабаровска ------------------------------------------
model, cfg = pg_lstm.load_model(MODEL_DIR / 'model' / 'pg_lstm_khabarovsk.pt')
fc = pg_lstm.forecast(clean, model, cfg)              # date, horizon, level, level_low, level_high
history = clean['level_khabarovsk'].loc[today - pd.Timedelta(days=120):]

save('forecast_khabarovsk', {
    'station_id': 'khabarovsk',
    'model': 'PG-LSTM',
    'model_note': 'Физически-информированная LSTM, прогноз на 14 суток по уровням 4 постов и погоде бассейна',
    'interval_label': 'Коридор 80 %',
    'today': f'{today:%Y-%m-%d}',
    'history': series_to_list(history),
    'forecast': [{'date': f'{r.date:%Y-%m-%d}', 'horizon': int(r.horizon), 'level': round(float(r.level), 1),
                  'level_low': round(float(r.level_low), 1), 'level_high': round(float(r.level_high), 1)}
                 for r in fc.itertuples()],
})

# --- 3. Сезонный ход: климатическая норма 2002…прошлый год -------------------------------------
# Заглушка до подключения Prophet: для каждого дня года берём медиану и 10/90 % квантили уровня
# по всем прошлым годам, затем сглаживаем скользящим окном 15 суток.
past = clean.loc[clean.index.year < today.year, 'level_khabarovsk']
by_doy = past.groupby(past.index.dayofyear)
clim = pd.DataFrame({'level': by_doy.median(), 'level_low': by_doy.quantile(0.1),
                     'level_high': by_doy.quantile(0.9)})
clim = clim.rolling(15, center=True, min_periods=1).mean()

future_days = pd.date_range(today + pd.Timedelta(days=1), periods=365)
seasonal = [{'date': f'{d:%Y-%m-%d}',
             **{k: round(float(clim.loc[min(d.dayofyear, 365), k]), 1) for k in clim.columns}}
            for d in future_days]

save('seasonal_khabarovsk', {
    'station_id': 'khabarovsk',
    'model': 'Климатическая норма',
    'model_note': f'Медиана уровня по годам {past.index.year.min()}–{past.index.year.max()}, '
                  f'коридор 10–90 % (временно, до подключения Prophet)',
    'today': f'{today:%Y-%m-%d}',
    'fact': series_to_list(clean['level_khabarovsk'].loc[f'{today.year}-01-01':]),
    'seasonal': seasonal,
})
