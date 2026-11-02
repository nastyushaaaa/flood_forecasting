"""Готовит данные сайта — JSON-файлы в frontend/mock.

Пока бэкенд не отдаёт данные, сайт читает эти файлы. Формат файлов = формат будущего API
(frontend/README.md, раздел «Контракт API»), поэтому потом меняется только адрес запроса.

Откуда данные:
- общий датасет data/amur_khabarovsk_clean_2002-2026.csv — уровни 4 постов Амура и погода бассейна по 01.08.2026;
- выгрузки allrivers.info из ветки data (data/<река>/<пост>.csv) — уровни постов по октябрь 2026. Файлы читаются
  прямо из ветки через git, копировать их не нужно (нужен git fetch);
- погода ERA5 и NASA POWER из amur_pg_lstm/data/raw/ — по ней датасет продлевается до последнего замера
  той же сборкой, что в amur_pg_lstm (pg_lstm.prepare_inputs). Модели при этом обучаются только по 01.08.2026;
- модели — из predict.py (код моделей не меняется), ошибки моделей — из model_comparison/results/metrics.csv.

Что получается:
- stations.json — уровни всех постов на самую свежую дату в данных;
- forecast_<пост>.json — факт и прогноз всех моделей на 14 суток от последнего замера в Хабаровске;
- backtest_khabarovsk.json — проверка: прогноз за 14 суток до последнего замера и что было на самом деле;
- seasonal_<пост>.json — сезонный прогноз на год от последнего замера.

Запуск из корня репозитория (бустинг обучается ~10 минут, потом берётся из results/make_mock_cache/):
    git fetch origin data
    python frontend/tools/make_mock.py
"""
import hashlib
import json
import pickle
import subprocess
import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]          # корень репозитория
OUT_DIR = ROOT / 'frontend' / 'mock'
CACHE_DIR = ROOT / 'results' / 'make_mock_cache'    # results/ не попадает в git
METRICS_FILE = ROOT / 'model_comparison' / 'results' / 'metrics.csv'
ALLRIVERS_REF = 'origin/data'                       # ветка с выгрузками allrivers
RAW_DIR = ROOT / 'amur_pg_lstm' / 'data' / 'raw'    # сырые ERA5 и NASA POWER, из них собран общий датасет
NASA_COLUMNS = {'T2M': 'temp', 'PRECTOTCORR': 'precip', 'PS': 'pressure', 'WS2M': 'wind', 'RH2M': 'humidity'}
HOURS_PER_DAY = 24  # в датасете осадки NASA в мм/ч, в выгрузке — мм/сут (проверено на всех днях 2002–2026)
sys.path.insert(0, str(ROOT))
from predict import DATA_FILE, HORIZON, load_data, make_model  # noqa: E402  (модели лежат в корне)

HISTORY_DAYS = 60          # сколько суток факта на графике перед прогнозом
SEASON_DAYS = 365          # горизонт сезонного прогноза, сут
STALE_DAYS = 7             # замер старше этого, сут — у поста статус «нет данных»
CLIMATE_MIN_YEARS = 10     # меньше лет наблюдений — климатическую норму не считаем
CLIMATE_SMOOTH_DAYS = 15   # окно сглаживания нормы, сут
Z_80 = 1.2816              # коридор 10–90 % = ±1,28σ
SEASONAL_TREND = 'trend_monthly_polynomial3'         # лучший из трендов по MAE в metrics.csv
EMPIRICAL_INTERVAL = 'Коридор 80 % по ошибкам проверки 2025–26'

# Пороги (watch = готовность, flood = выход на пойму, danger = опасный) — условные, как в прототипе!
STATIONS = [
    dict(id='khabarovsk', name='Хабаровск', river='Амур', okrug='ДФО', lat=48.48, lon=135.07,
         thresholds=dict(watch=300, flood=470, danger=550), column='level_khabarovsk', allrivers='amur/habarovsk.csv'),
    dict(id='blagoveshchensk', name='Благовещенск', river='Амур', okrug='ДФО', lat=50.26, lon=127.53,
         thresholds=dict(watch=450, flood=600, danger=700), column='level_blagoveshchensk',
         allrivers='amur/blagoveshensk.csv'),
    dict(id='poyarkovo', name='Поярково', river='Амур', okrug='ДФО', lat=49.62, lon=128.68,
         thresholds=dict(watch=500, flood=650, danger=750), column='level_poyarkovo', allrivers='amur/poyarkovo.csv'),
    dict(id='leninskoe', name='Ленинское', river='Амур', okrug='ДФО', lat=47.93, lon=132.62,
         thresholds=dict(watch=650, flood=760, danger=850), column='level_leninskoe', allrivers='amur/leninskoe.csv'),
    dict(id='lensk', name='Ленск', river='Лена', okrug='ДФО', lat=60.72, lon=114.93,
         thresholds=dict(watch=1100, flood=1250, danger=1350), allrivers='lena/lensk.csv'),
    dict(id='yakutsk', name='Якутск', river='Лена', okrug='ДФО', lat=62.03, lon=129.73,
         thresholds=dict(watch=800, flood=900, danger=1000), allrivers='lena/yakutsk.csv'),
    dict(id='barnaul', name='Барнаул', river='Обь', okrug='СФО', lat=53.35, lon=83.78,
         thresholds=dict(watch=420, flood=450, danger=472), allrivers='ob/barnaul.csv'),
    dict(id='kemerovo', name='Кемерово', river='Томь', okrug='СФО', lat=55.36, lon=86.09,
         thresholds=dict(watch=600, flood=700, danger=800), allrivers='tom/kemerovo.csv'),
    dict(id='novokuznetsk', name='Новокузнецк', river='Томь', okrug='СФО', lat=53.76, lon=87.12,
         thresholds=dict(watch=450, flood=550, danger=650), allrivers='tom/novokuzneck.csv'),
    dict(id='krasnodar', name='Краснодар', river='Кубань', okrug='ЮФО', lat=45.04, lon=38.98,
         thresholds=dict(watch=0, flood=30, danger=50), allrivers='kuban/krasnodar.csv'),
    # в выгрузках allrivers поста нет — остаётся из прототипа со статусом «нет данных»
    dict(id='sochi', name='Сочи', river='Сочи', okrug='ЮФО', lat=43.59, lon=39.72,
         thresholds=dict(watch=150, flood=200, danger=250)),
]

MODEL_NOTES = {
    'naive': 'точка отсчёта: уровень останется таким же, как в день прогноза',
    'prophet': 'сезонная кривая: не знает текущего уровня, прогноз зависит только от дня года',
    'trend': 'кубический тренд с поправкой на месяц года, текущего уровня не знает',
    'pg_lstm': 'нейросеть с физикой паводковой волны, по уровням 4 постов и погоде бассейна (обучена до 2018 г.)',
    'gpb': 'градиентный бустинг по уровням постов, водоотдаче и осадкам бассейна, своя модель на каждые сутки',
    'linear': 'Ridge-регрессия по уровням 4 постов за 14 суток и погоде бассейна',
}


def save(name, data):
    """Записывает словарь в frontend/mock/<name>.json."""
    path = OUT_DIR / f'{name}.json'
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('записан', path.relative_to(ROOT))


def day(d):
    return pd.Timestamp(d).strftime('%Y-%m-%d')


def series_to_list(s):
    """pd.Series с датами в индексе -> [{"date": "2026-08-01", "level": 405.0}, ...]."""
    return [{'date': day(d), 'level': round(float(v), 1)} for d, v in s.dropna().items()]


def band_points(dates, levels, lows, highs, with_horizon=True):
    """Точки прогноза с коридором: [{"date", "horizon", "level", "level_low", "level_high"}, ...]."""
    points = []
    for h, (d, level, low, high) in enumerate(zip(dates, levels, lows, highs), start=1):
        point = {'date': day(d), 'level': round(float(level), 1),
                 'level_low': round(float(low), 1), 'level_high': round(float(high), 1)}
        if with_horizon:
            point['horizon'] = h
        points.append(point)
    return points


# --- 1. Уровни постов -----------------------------------------------------------------------
def read_allrivers(relative_path):
    """Выгрузка allrivers из ветки data -> ряд уровней (индекс — дата, см). Нет ветки — пустой ряд."""
    result = subprocess.run(['git', 'show', f'{ALLRIVERS_REF}:data/{relative_path}'], cwd=ROOT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f'ВНИМАНИЕ: нет {ALLRIVERS_REF}:data/{relative_path} (сделайте git fetch origin data)')
        return pd.Series(dtype=float)
    table = pd.read_csv(StringIO(result.stdout), parse_dates=['date'])
    return table.set_index('date')['level_cm'].astype(float).sort_index()


def level_series(station):
    """Измеренные уровни поста: общий датасет (без восстановленных дней), дальше — allrivers."""
    parts = []
    if 'column' in station:
        measured = clean[clean[station['column'] + '_filled'] == 0]
        parts.append(measured[station['column']])
    if 'allrivers' in station:
        extra = read_allrivers(station['allrivers'])
        if parts:
            extra = extra[extra.index > parts[0].index[-1]]
        parts.append(extra)
    if not parts:
        return pd.Series(dtype=float)
    series = pd.concat(parts)
    return series[~series.index.duplicated(keep='last')].dropna()


def extend_dataset(series, end):
    """Продлевает общий датасет до даты end той же сборкой, что в amur_pg_lstm (pg_lstm.prepare_inputs):
    уровни 4 постов (общий датасет + allrivers) и погода ERA5 и NASA POWER из amur_pg_lstm/data/raw/.

    Returns:
        Таблица с теми же колонками, что общий датасет, по дату end включительно.

    Raises:
        ValueError: в сырых данных нет погоды до даты end.
    """
    import pg_lstm   # модуль модели лежит в amur_pg_lstm, путь к нему добавляет predict.py
    era5 = {n: pd.read_csv(RAW_DIR / f'era5_{n}.csv', parse_dates=['time'], index_col='time')
            for n in pg_lstm.ERA5_POINTS}
    rows = pg_lstm.prepare_inputs({g: series[g] for g in pg_lstm.GAUGES}, end=end, era5=era5)
    nasa = pd.read_csv(RAW_DIR / 'nasa_power_khabarovsk.csv', parse_dates=['date'], index_col='date')
    nasa = nasa.rename(columns=NASA_COLUMNS)
    nasa['precip'] = (nasa['precip'] / HOURS_PER_DAY).round(2)
    rows = rows.join(nasa)[clean.columns].loc[clean.index[-1] + pd.Timedelta(days=1):]
    if rows.isna().any().any():
        raise ValueError(f'В {RAW_DIR} нет погоды до {end.date()}: обновите выгрузки ERA5 и NASA POWER')
    return pd.concat([clean, rows])


# --- 2. Модели ------------------------------------------------------------------------------
def file_digest(*paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def fit(key, df, train_end):
    """Обучает модель из predict.py на данных по train_end; прогнозировать она может по всей таблице df.
    Бустинг (~10 минут) сохраняется на диск."""
    cache = CACHE_DIR / f'{key}_{file_digest(DATA_FILE, ROOT / "predict.py")}_{df.index[-1]:%Y%m%d}.pkl'
    if key == 'gpb' and cache.exists():
        print('бустинг загружен из', cache.relative_to(ROOT))
        return pickle.loads(cache.read_bytes())
    print('обучается', key, '…' + (' около 10 минут' if key == 'gpb' else ''))
    model = make_model(key).fit(df, train_end=train_end)
    if key == 'gpb':
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(pickle.dumps(model))
    return model


def skill(name):
    """Ошибки модели на проверке model_comparison: [{"horizon", "mae", "rmse"}, ...]."""
    rows = metrics[metrics['model'] == name].sort_values('horizon')
    return [{'horizon': int(r.horizon), 'mae': round(float(r.mae), 1), 'rmse': round(float(r.rmse), 1)}
            for r in rows.itertuples()]


def model_entry(key, name, today, levels, low=None, high=None, interval=EMPIRICAL_INTERVAL):
    """Прогноз одной модели на 1–14 суток. Без своего коридора — ±1,28·RMSE с проверки на каждом горизонте."""
    dates = [today + pd.Timedelta(days=h) for h in range(1, HORIZON + 1)]
    levels = np.asarray(levels, dtype=float)
    if low is None:
        rmse = metrics[metrics['model'] == name].set_index('horizon')['rmse'].reindex(range(1, HORIZON + 1))
        low, high = levels - Z_80 * rmse.to_numpy(), levels + Z_80 * rmse.to_numpy()
    return {'key': key, 'model': name, 'model_note': MODEL_NOTES[key], 'interval_label': interval,
            'forecast': band_points(dates, levels, low, high), 'skill': skill(name)}


def short_term(today):
    """Прогнозы всех моделей на 1–14 суток от даты today (данные моделям — только по today включительно)."""
    pg = models['pg_lstm']
    table = pg.lib.forecast(pg.df, pg.model, pg.cfg, date=today)      # у PG-LSTM коридор свой
    entries = [model_entry('pg_lstm', 'PG-LSTM', today, table['level'], table['level_low'], table['level_high'],
                           'Коридор 80 % по ошибкам на валидации')]
    for key in ['gpb', 'linear', 'prophet', 'naive']:
        m = models[key]
        entries.append(model_entry(key, m.name, today, [m.predict(today, h) for h in range(1, HORIZON + 1)]))
    return entries


def curve(model, today, days):
    """Уровень по модели без текущего уровня (Prophet, тренд) на days суток вперёд.
    predict(дата, h) у них зависит только от дня, на который дан прогноз, поэтому идём шагами по 14 суток."""
    return [model.predict(today + pd.Timedelta(days=start), h)
            for start in range(0, days, HORIZON) for h in range(1, HORIZON + 1)][:days]


# --- 3. Сезонный ход ------------------------------------------------------------------------
def climate(series, today, days):
    """Климатическая норма: медиана и 10/90 % уровня по прошлым годам для каждого дня года."""
    past = series[series.index.year < today.year]
    years = past.index.year.unique()
    if len(years) < CLIMATE_MIN_YEARS:
        return None
    by_day = past.groupby(past.index.dayofyear)
    norm = pd.DataFrame({'level': by_day.median(), 'low': by_day.quantile(0.1), 'high': by_day.quantile(0.9)})
    norm = norm.rolling(CLIMATE_SMOOTH_DAYS, center=True, min_periods=1).mean()
    rows = norm.reindex([min(d.dayofyear, 365) for d in days]).ffill()
    return {'key': 'climate', 'model': 'Климатическая норма',
            'model_note': f'медиана уровня по годам {years.min()}–{years.max()}, коридор 10–90 %',
            'interval_label': 'Обычный разброс 10–90 %',
            'seasonal': band_points(days, rows['level'], rows['low'], rows['high'], with_horizon=False)}


if __name__ == '__main__':
    clean = load_data()
    train_end = clean.index[-1]                      # модели обучаются только по последний день общего датасета
    metrics = pd.read_csv(METRICS_FILE, encoding='utf-8-sig')
    series = {st['id']: level_series(st) for st in STATIONS}
    snapshot = max(s.index[-1] for s in series.values() if len(s))   # самый свежий замер в данных
    today = series['khabarovsk'].index[-1]           # дата прогноза: последний замер в Хабаровске
    extended = extend_dataset(series, today)
    print(f'обучение по {train_end.date()}, прогноз от {today.date()}, самый свежий замер {snapshot.date()}')

    # 1. Посты и уровни на самую свежую дату
    stations = []
    for st in STATIONS:
        s = series[st['id']].loc[:snapshot]
        measured_at = s.index[-1] if len(s) else None
        fresh = measured_at is not None and (snapshot - measured_at).days <= STALE_DAYS
        stations.append({k: st[k] for k in ('id', 'name', 'river', 'okrug', 'lat', 'lon', 'thresholds')}
                        | {'level': round(float(s.iloc[-1]), 1) if fresh else None,
                           'measured_at': day(measured_at) if measured_at is not None else None})
    save('stations', {'updated_at': f'{day(snapshot)}T08:00:00+03:00', 'next_update_at': None,
                      'available_from': day(min(s.index[0] for s in series.values() if len(s))),
                      'available_to': day(snapshot), 'stations': stations})

    models = {key: fit(key, extended, train_end)
              for key in ['naive', 'prophet', SEASONAL_TREND, 'pg_lstm', 'linear', 'gpb']}

    for st in STATIONS:
        s = series[st['id']]
        if s.empty:
            continue
        last = s.index[-1]
        days = pd.date_range(last + pd.Timedelta(days=1), periods=SEASON_DAYS)

        # 2. Прогноз на 14 суток от последнего замера (модели обучены только для Хабаровска)
        is_main = st['id'] == 'khabarovsk'
        save(f'forecast_{st["id"]}', {
            'station_id': st['id'], 'today': day(last),
            'history': series_to_list(s.loc[last - pd.Timedelta(days=HISTORY_DAYS):last]), 'actual': [],
            'models': short_term(last) if is_main else [], 'pending': [],
            'note': None if is_main else 'Модели проекта обучены только для поста Хабаровск, здесь показан только факт.',
        })

        # 3. Сезонный ход на год от последнего замера
        seasonal = []
        if is_main:
            prophet = models['prophet'].model.predict(pd.DataFrame({'ds': days}))
            seasonal.append({'key': 'prophet', 'model': 'Prophet', 'model_note': MODEL_NOTES['prophet'],
                             'interval_label': 'Интервал Prophet 80 %',
                             'seasonal': band_points(days, prophet['yhat'], prophet['yhat_lower'],
                                                     prophet['yhat_upper'], with_horizon=False)})
            trend = np.array(curve(models[SEASONAL_TREND], last, SEASON_DAYS))
            spread = Z_80 * models[SEASONAL_TREND].result.s     # разброс остатков обучения
            seasonal.append({'key': 'trend', 'model': 'Тренд + месяц', 'model_note': MODEL_NOTES['trend'],
                             'interval_label': 'Коридор 80 % по остаткам обучения',
                             'seasonal': band_points(days, trend, trend - spread, trend + spread, with_horizon=False)})
        norm = climate(s, last, days)
        if norm:
            seasonal.append(norm)
        if seasonal:
            save(f'seasonal_{st["id"]}', {'station_id': st['id'], 'today': day(last),
                                          'fact': series_to_list(s.loc[f'{last.year}-01-01':]),
                                          'models': seasonal, 'pending': []})

    # 4. Проверка: прогноз за 14 суток до последнего замера и что было на самом деле.
    # Модели обучены по 01.08.2026, поэтому эти две недели они не видели
    s = series['khabarovsk']
    check = today - pd.Timedelta(days=HORIZON)
    save('backtest_khabarovsk', {
        'station_id': 'khabarovsk', 'today': day(check),
        'history': series_to_list(s.loc[check - pd.Timedelta(days=HISTORY_DAYS):check]),
        'actual': series_to_list(s.loc[check + pd.Timedelta(days=1):today]),
        'models': short_term(check), 'pending': [], 'note': None,
    })
