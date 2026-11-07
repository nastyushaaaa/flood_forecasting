"""PG-LSTM — физически-информированная LSTM для прогноза уровня Амура у Хабаровска на 14 суток.

Файл создаётся блокнотом PG_LSTM_Хабаровск.ipynb (ячейка %%writefile) — правки вносите там.
Здесь признаки, сама сеть и прогноз. Очистка уровней, погода ERA5, модель снега и
маршрутизация волны — в preprocessing.py (имена реэкспортируются отсюда, старый код работает).
"""
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from preprocessing import (  # noqa: F401  (реэкспорт для блокнота и predict.py)
    DDF, ERA5_POINTS, ERA5_VARS, EXPERT_BAD, GAUGES, GROUPS, HORIZON, SPIKE_T, T_MELT, UPSTREAM, VALID_RANGE,
    basin_weather, clean_level, fetch_era5, find_bad, prepare_inputs, routing_forecast, routing_terms,
    snow_model,
)

WINDOW, SCALE = 60, 50.0


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
