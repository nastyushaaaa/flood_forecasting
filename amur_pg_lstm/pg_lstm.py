"""PG-LSTM — физически-информированная LSTM для прогноза уровня Амура у Хабаровска на 14 суток.

Файл создаётся блокнотом PG_LSTM_Хабаровск.ipynb (ячейка %%writefile) — правки вносите там.
Здесь всё, что нужно для работы обученной модели вне блокнота: очистка уровней, погода ERA5
по бассейну, модель снега, физическая модель маршрутизации волны, признаки, сама сеть и прогноз.
"""
import time

import numpy as np
import pandas as pd
import requests
import torch
import torch.nn as nn

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
WINDOW, HORIZON, SCALE = 60, 14, 50.0

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


# --- признаки и модель ------------------------------------------------------
def build_features(clean):
    """Признаки для LSTM (до масштабирования)."""
    f = pd.DataFrame(index=clean.index)
    for g in GAUGES:
        f[f'lvl_{g}'] = clean[f'level_{g}']
    f['dlvl_khabarovsk'] = clean['level_khabarovsk'].diff().fillna(0)
    for p in UPSTREAM:
        f[f'flag_{p}'] = clean[f'level_{p}_filled']
    for g in GROUPS:
        for v in ['temp', 'water_input', 'swe']:
            f[f'{g}_{v}'] = clean[f'{g}_{v}']
    doy = clean.index.dayofyear.values
    f['sin_doy'] = np.sin(2 * np.pi * doy / 365.25)
    f['cos_doy'] = np.cos(2 * np.pi * doy / 365.25)
    return f


class PGLSTM(nn.Module):
    """LSTM по окну истории → 14 приращений уровня (в долях SCALE см).
    physics_input=True: на вход головы подаётся и прогноз физической модели, а выход сети — поправка к нему:
    Ĥ = H_t + SCALE·(физ. прогноз + поправка). При False — обычная LSTM без физики."""

    def __init__(self, n_features, hidden=64, layers=2, dropout=0.2, physics_input=True, horizon=HORIZON):
        super().__init__()
        self.physics_input = physics_input
        self.lstm = nn.LSTM(n_features, hidden, layers, batch_first=True, dropout=dropout)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(hidden + (horizon if physics_input else 0), horizon)

    def forward(self, x, phys=None):
        out, _ = self.lstm(x)
        z = self.drop(out[:, -1])
        if not self.physics_input:
            return self.head(z)
        return phys + self.head(torch.cat([z, phys], dim=1))


class Ensemble(nn.Module):
    """Среднее нескольких PGLSTM, обученных с разными сидами (снижает разброс прогноза)."""

    def __init__(self, models):
        super().__init__()
        self.models = nn.ModuleList(models)

    def forward(self, x, phys=None):
        return torch.stack([m(x, phys) for m in self.models]).mean(0)


def save_model(path, models, cfg):
    torch.save({'state_dicts': [m.state_dict() for m in models], 'cfg': cfg}, path)


def load_model(path):
    """Загружает ансамбль из файла .pt. Возвращает (модель, конфигурация)."""
    ck = torch.load(path, map_location='cpu', weights_only=False)
    cfg = ck['cfg']
    nets = []
    for sd in ck['state_dicts']:
        m = PGLSTM(len(cfg['features']), **cfg['arch'])
        m.load_state_dict(sd)
        nets.append(m)
    model = Ensemble(nets)
    model.eval()
    return model, cfg


def forecast(clean, model, cfg, date=None):
    """Прогноз уровня у Хабаровска на 1…14 сут от даты `date` (по умолчанию — последняя в таблице).
    Возвращает date, horizon, level, level_low, level_high (80%-интервал по ошибкам на валидации), см."""
    f = build_features(clean)[cfg['features']]
    x = ((f - pd.Series(cfg['mean'])) / pd.Series(cfg['std'])).values.astype(np.float32)
    t = len(f) - 1 if date is None else f.index.get_loc(pd.Timestamp(date))
    if t + 1 < WINDOW:
        raise ValueError(f'нужно минимум {WINDOW} суток истории')
    phys = torch.tensor(routing_forecast(clean, cfg['routing'], [t]) / SCALE, dtype=torch.float32)
    with torch.no_grad():
        d = model(torch.tensor(x[None, t - WINDOW + 1:t + 1]), phys)[0].numpy() * SCALE
    h0, t0 = float(clean['level_khabarovsk'].iloc[t]), f.index[t]
    lo, hi = np.array(cfg['err_q10']), np.array(cfg['err_q90'])
    return pd.DataFrame({'date': [t0 + pd.Timedelta(days=h) for h in range(1, HORIZON + 1)],
                         'horizon': np.arange(1, HORIZON + 1),
                         'level': np.round(h0 + d, 1),
                         'level_low': np.round(h0 + d + lo, 1),
                         'level_high': np.round(h0 + d + hi, 1)})
