"""Входные данные PG-LSTM: очистка уровней, погода ERA5 по бассейну, модель снега
и физическая модель маршрутизации паводковой волны.

Файл создаётся блокнотом PG_LSTM_Хабаровск.ipynb (ячейка %%writefile) — правки вносите там.
Сеть, признаки и прогноз — в pg_lstm.py.
"""
import time

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

# --- очистка уровней -------------------------------------------------------
VALID_RANGE = {'khabarovsk': (-350, 900), 'blagoveshchensk': (-200, 950),
               'poyarkovo': (-250, 950), 'leninskoe': (-150, 1100)}
# допустимое отклонение от медианы соседних наблюдений, см; шире в ледоход (апрель) и ледостав (ноябрь)
SPIKE_T = {
    'khabarovsk': {1: 40, 2: 40, 3: 60, 4: 200, 5: 40, 6: 40, 7: 40, 8: 40, 9: 40, 10: 40, 11: 120, 12: 80},
    'upstream': {1: 60, 2: 60, 3: 80, 4: 250, 5: 200, 6: 150, 7: 150, 8: 150, 9: 150, 10: 150, 11: 150, 12: 100},
}
EXPERT_BAD = {'khabarovsk': [('2023-03-21', '2023-04-10')]}   # сбой датчика: от −987 до +662 см за сутки


def find_bad(s, name):
    """Маска ошибочных значений ряда уровня (индекс — даты наблюдений)."""
    lo, hi = VALID_RANGE[name]
    thr = SPIKE_T['khabarovsk' if name == 'khabarovsk' else 'upstream']
    bad = (s < lo) | (s > hi)                                        # коды ошибок 1050/1056 и т. п.
    bad |= (s == 0) & (s.index.to_series().diff().dt.days >= 7)      # «0» — заглушка после пропуска
    for a, b in EXPERT_BAD.get(name, []):
        bad[a:b] = True
    for _ in range(50):                                              # одиночные выбросы, по одному за шаг
        x = s[~bad]
        dev = (x - x.rolling(5, center=True, min_periods=3).median()).abs()
        cand = dev[dev > x.index.month.map(thr).values]
        if cand.empty:
            break
        bad[cand.idxmax()] = True
    return bad


def clean_level(s, name, days):
    """Убирает ошибки, ставит ряд на сетку дней `days`, заполняет пропуски интерполяцией.
    Возвращает (уровень, флаг «значение восстановлено»)."""
    s = s.dropna().sort_index()
    s = s[~s.index.duplicated()]
    s = s[~find_bad(s, name)].reindex(days)
    filled = s.isna().astype(int)
    return s.interpolate('time', limit_direction='both').round(1), filled


# --- погода и снег ----------------------------------------------------------
def fetch_era5(name, start, end, retries=6):
    """Суточная погода ERA5 из архива Open-Meteo для точки бассейна."""
    lat, lon = ERA5_POINTS[name]
    for _ in range(retries):
        r = requests.get('https://archive-api.open-meteo.com/v1/archive', timeout=120, params=dict(
            latitude=lat, longitude=lon, start_date=str(start)[:10], end_date=str(end)[:10],
            daily=ERA5_VARS, timezone='Asia/Vladivostok'))
        if r.status_code == 429:          # лимит запросов в минуту — ждём
            time.sleep(65)
            continue
        r.raise_for_status()
        d = pd.DataFrame(r.json()['daily'])
        d.index = pd.to_datetime(d.pop('time'))
        return d
    raise RuntimeError('Open-Meteo не отвечает: ' + name)


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
    end = pd.Timestamp(end or levels['khabarovsk'].dropna().index.max()).normalize()
    start = pd.Timestamp(year=end.year - 1, month=9, day=1)
    days = pd.date_range(start, end, freq='D')
    df = pd.DataFrame(index=days)
    df.index.name = 'date'
    for g in GAUGES:
        df[f'level_{g}'], df[f'level_{g}_filled'] = clean_level(levels[g][start:end], g, days)
    era5 = era5 or {n: fetch_era5(n, start, end) for n in ERA5_POINTS}
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
    last = list(routing.values())[-1]
    for h in range(1, HORIZON + 1):
        r = next((r for r in routing.values() if h <= r['hmax']), None)
        PHI[:, h - 1] = (r or last)['phi']
        if r is None:
            continue
        k = 0
        for p in r['posts']:
            for d in (0, 1):
                U[:, h - 1] += r['a'][k] * dpost[p][t_idx + h - r['tau'][p] - d]
                k += 1
    return U, PHI


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
