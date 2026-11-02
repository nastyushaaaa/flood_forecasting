"""Входные данные PG-LSTM: очистка уровней, погода ERA5 по бассейну, модель снега
и физическая модель маршрутизации паводковой волны.

Файл создаётся блокнотом PG_LSTM_Хабаровск.ipynb (ячейка %%writefile) — правки вносите там.
Сеть, признаки и прогноз — в pg_lstm.py.
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

GAUGES = ['khabarovsk', 'blagoveshchensk', 'poyarkovo', 'leninskoe']
UPSTREAM = GAUGES[1:]

# Точки ERA5 (Open-Meteo) по частям бассейна: (широта, долгота)
ERA5_POINTS = {
    'khabarovsk': (48.48, 135.07), 'birobidzhan': (48.79, 132.92),             # местный приток
    'blagoveshchensk': (50.28, 127.54), 'zeya': (53.73, 127.27), 'bureya': (51.10, 132.00),  # Амур, Зея, Бурея
    'harbin': (45.75, 126.65), 'jiamusi': (46.80, 130.36), 'mudanjiang': (44.58, 129.60),    # Сунгари
    'dalnerechensk': (45.93, 133.73),                                           # Уссури
}
GROUPS = {'local': ['khabarovsk', 'birobidzhan'], 'amur': ['blagoveshchensk', 'zeya', 'bureya'],
          'sungari': ['harbin', 'jiamusi', 'mudanjiang'], 'ussuri': ['dalnerechensk']}
ERA5_VARS = 'temperature_2m_mean,precipitation_sum,rain_sum,snowfall_sum,et0_fao_evapotranspiration'

DDF, T_MELT = 3.0, 0.0           # коэффициент стаивания, мм/(°C·сут), и порог таяния, °C
HORIZON = 14

ERA5_URL = 'https://archive-api.open-meteo.com/v1/archive'
ERA5_TIMEOUT_S = 120             # архив за год отдаётся долго
ERA5_RETRIES = 6
RATE_LIMIT_PAUSE_S = 65          # Open-Meteo ограничивает число запросов в минуту (ответ 429)
ERA5_CACHE_DIR = Path(__file__).resolve().parents[1] / 'data' / 'cache'
ERA5_LAG_DAYS = 7                # данные ERA5 за последнюю неделю ещё уточняются
ERA5_CACHE_TTL_H = 12            # кеш за такие свежие дни считаем актуальным полсуток

# --- очистка уровней -------------------------------------------------------
VALID_RANGE = {'khabarovsk': (-350, 900), 'blagoveshchensk': (-200, 950),
               'poyarkovo': (-250, 950), 'leninskoe': (-150, 1100)}
# допустимое отклонение от медианы соседних наблюдений, см; шире в ледоход (апрель) и ледостав (ноябрь)
SPIKE_T = {
    'khabarovsk': {1: 40, 2: 40, 3: 60, 4: 200, 5: 40, 6: 40, 7: 40, 8: 40, 9: 40, 10: 40, 11: 120, 12: 80},
    'upstream': {1: 60, 2: 60, 3: 80, 4: 250, 5: 200, 6: 150, 7: 150, 8: 150, 9: 150, 10: 150, 11: 150, 12: 100},
}
EXPERT_BAD = {'khabarovsk': [('2023-03-21', '2023-04-10')]}   # сбой датчика: от −987 до +662 см за сутки
STUB_GAP_DAYS = 7   # «0» после пропуска хотя бы такой длины — заглушка поста, а не настоящий уровень


def find_bad(levels, name):
    """Маска ошибочных значений ряда уровня, см (индекс — даты наблюдений)."""
    min_cm, max_cm = VALID_RANGE[name]
    spike_limit_cm = SPIKE_T['khabarovsk' if name == 'khabarovsk' else 'upstream']
    out_of_range = (levels < min_cm) | (levels > max_cm)                       # коды ошибок 1050/1056 и т. п.
    after_long_gap = levels.index.to_series().diff().dt.days >= STUB_GAP_DAYS
    is_stub_zero = (levels == 0) & after_long_gap
    bad = out_of_range | is_stub_zero
    for bad_from, bad_to in EXPERT_BAD.get(name, []):
        bad[bad_from:bad_to] = True
    for _ in range(50):                                                        # одиночные выбросы, по одному за шаг
        kept = levels[~bad]
        deviation_cm = (kept - kept.rolling(5, center=True, min_periods=3).median()).abs()
        spikes = deviation_cm[deviation_cm > kept.index.month.map(spike_limit_cm).values]
        if spikes.empty:
            break
        bad[spikes.idxmax()] = True
    return bad


def clean_level(levels, name, days):
    """Убирает ошибки, ставит ряд на сетку дней `days`, заполняет пропуски интерполяцией.
    Возвращает (уровень, флаг «значение восстановлено»)."""
    levels = levels.dropna().sort_index()
    levels = levels[~levels.index.duplicated()]
    levels = levels[~find_bad(levels, name)].reindex(days)
    filled = levels.isna().astype(int)
    return levels.interpolate('time', limit_direction='both').round(1), filled


# --- погода и снег ----------------------------------------------------------
def fetch_era5(name, start, end, retries=ERA5_RETRIES):
    """Суточная погода ERA5 из архива Open-Meteo для точки бассейна.
    Ответ сохраняется в ERA5_CACHE_DIR: архив не меняется, поэтому повторно его не скачиваем."""
    start_date, end_date = str(start)[:10], str(end)[:10]
    cache_path = ERA5_CACHE_DIR / f'era5_{name}_{start_date}_{end_date}.csv'
    if _is_cache_fresh(cache_path, end_date):
        return pd.read_csv(cache_path, index_col='time', parse_dates=['time'])
    weather = _download_era5(name, start_date, end_date, retries)
    _save_cache(weather, cache_path)
    return weather


def _download_era5(name, start_date, end_date, retries):
    """Один запрос к архиву Open-Meteo; при ответе 429 ждёт RATE_LIMIT_PAUSE_S и повторяет."""
    lat, lon = ERA5_POINTS[name]
    params = dict(latitude=lat, longitude=lon, start_date=start_date, end_date=end_date,
                  daily=ERA5_VARS, timezone='Asia/Vladivostok')
    for _ in range(retries):
        response = requests.get(ERA5_URL, params=params, timeout=ERA5_TIMEOUT_S)
        if response.status_code == 429:
            time.sleep(RATE_LIMIT_PAUSE_S)
            continue
        response.raise_for_status()
        weather = pd.DataFrame(response.json()['daily'])
        weather.index = pd.to_datetime(weather.pop('time'))
        return weather
    raise RuntimeError('Open-Meteo не отвечает: ' + name)


def _is_cache_fresh(cache_path, end_date):
    """Архивный период (старше ERA5_LAG_DAYS) берём из кеша всегда, свежий — если кешу меньше ERA5_CACHE_TTL_H часов."""
    if not cache_path.exists():
        return False
    is_archive = pd.Timestamp(end_date) < pd.Timestamp.today().normalize() - pd.Timedelta(days=ERA5_LAG_DAYS)
    age_h = (time.time() - cache_path.stat().st_mtime) / 3600
    return is_archive or age_h < ERA5_CACHE_TTL_H


def _save_cache(weather, cache_path):
    if not cache_path.parent.exists():
        cache_path.parent.mkdir(parents=True)
        (cache_path.parent / '.gitignore').write_text('*\n')   # кеш не попадает в git
    weather.to_csv(cache_path, index_label='time')


def snow_model(temp, precip, rain, ddf=DDF, t_melt=T_MELT):
    """Модель снежного покрова по градусо-дням.
    Твёрдые осадки (precip − rain) копятся в запасе воды в снеге SWE, тает
    min(SWE, ddf·max(T − t_melt, 0)) мм/сут. Возвращает (таяние, SWE) в мм."""
    snow = np.clip(np.asarray(precip) - np.asarray(rain), 0, None)
    temp = np.asarray(temp)
    melt, swe, S = np.zeros(len(temp)), np.zeros(len(temp)), 0.0
    for i in range(len(temp)):
        S += snow[i]
        m = min(S, ddf * max(temp[i] - t_melt, 0.0))
        S -= m
        melt[i], swe[i] = m, S
    return melt, swe


def basin_weather(era5, days):
    """Средние по частям бассейна: температура, осадки, водоотдача (дождь + таяние), запас воды в снеге."""
    pts = {}
    for n, e in era5.items():
        e = e.sort_index()
        melt, swe = snow_model(e['temperature_2m_mean'], e['precipitation_sum'], e['rain_sum'])
        pts[n] = pd.DataFrame({'temp': e['temperature_2m_mean'], 'precip': e['precipitation_sum'],
                               'water_input': e['rain_sum'] + melt, 'swe': swe}, index=e.index).reindex(days)
    out = pd.DataFrame(index=days)
    for g, names in GROUPS.items():
        m = sum(pts[n] for n in names) / len(names)
        for v, nd in [('temp', 2), ('precip', 2), ('water_input', 2), ('swe', 1)]:
            out[f'{g}_{v}'] = m[v].round(nd)
    return out


def prepare_inputs(levels, end=None, era5=None):
    """Собирает таблицу для прогноза из сырых уровней 4 постов.
    levels: {'khabarovsk': pd.Series(уровень, индекс=даты), ...} — все 4 поста из GAUGES.
    Прогноз строится от последнего наблюдения в Хабаровске (или от `end`).
    Погода ERA5 скачивается сама, с 1 сентября прошлого года: модели снега нужна вся зима."""
    if end is None:
        end = levels['khabarovsk'].dropna().index.max()
    end = pd.Timestamp(end).normalize()
    start = pd.Timestamp(year=end.year - 1, month=9, day=1)
    days = pd.date_range(start, end, freq='D')
    df = pd.DataFrame(index=days)
    df.index.name = 'date'
    for g in GAUGES:
        df[f'level_{g}'], df[f'level_{g}_filled'] = clean_level(levels[g][start:end], g, days)
    if era5 is None:
        era5 = {name: fetch_era5(name, start, end) for name in ERA5_POINTS}
    return df.join(basin_weather(era5, days))


# --- физическая модель: маршрутизация волны ---------------------------------
def routing_terms(clean, routing, t_idx):
    """Слагаемые уравнения маршрутизации для прогноза от дней t_idx (позиции строк в clean):
    ΔH(t+h) = PHI[:, h-1]·ΔH(t+h-1) + U[:, h-1].
    U — вклад постов выше по течению: Σ a·ΔH_пост(t+h-τ-d); берётся физическая модель, у которой все τ ≥ h,
    поэтому используются только уже наблюдённые приращения. Дальше приток неизвестен: U = 0, волна затухает."""
    t_idx = np.atleast_1d(np.asarray(t_idx))
    dpost = {p: np.nan_to_num(clean[f'level_{p}'].diff().values) for p in UPSTREAM}
    U, PHI = np.zeros((len(t_idx), HORIZON)), np.zeros((len(t_idx), HORIZON))
    last_model = list(routing.values())[-1]
    for h in range(1, HORIZON + 1):
        model = _routing_model_for(routing, h)
        if model is None:                      # горизонт дальше всех моделей: притока нет, волна только затухает
            PHI[:, h - 1] = last_model['phi']
            continue
        PHI[:, h - 1] = model['phi']
        k = 0
        for p in model['posts']:
            for d in (0, 1):
                U[:, h - 1] += model['a'][k] * dpost[p][t_idx + h - model['tau'][p] - d]
                k += 1
    return U, PHI


def _routing_model_for(routing, h):
    """Первая физическая модель, которая работает на горизонте h сут (h ≤ hmax); None — такой нет."""
    for model in routing.values():
        if h <= model['hmax']:
            return model
    return None


def routing_forecast(clean, routing, t_idx):
    """Прогноз чистой физикой: приращения уровня у Хабаровска к H_t на 1…14 сут, см."""
    U, PHI = routing_terms(clean, routing, t_idx)
    d = np.nan_to_num(clean['level_khabarovsk'].diff().values[np.atleast_1d(t_idx)])
    out, lev = np.zeros_like(U), 0.0
    for h in range(HORIZON):
        d = PHI[:, h] * d + U[:, h]
        lev = lev + d
        out[:, h] = lev
    return out
