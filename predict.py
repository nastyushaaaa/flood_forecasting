"""Обёртки над моделями: у всех моделей одинаковый вид predict(date, h).

predict(date, h) — прогноз уровня воды у Хабаровска (см) на день date + h суток,
сделанный в день date. Модель использует только данные до date включительно.

Пример:
    from predict import load_data, make_model

    df = load_data()
    model = make_model('linear').fit(df)
    model.predict('2026-07-20', 7)   # уровень на 27.07.2026 по прогнозу от 20.07.2026
"""
import sys
from pathlib import Path

import pandas as pd

from abc import ABC, abstractmethod

ROOT = Path(__file__).resolve().parent # корень репозитория
DATA_FILE = ROOT / 'data' / 'amur_khabarovsk_clean_2002-2026.csv' # единственный файл данных
TARGET = 'level_khabarovsk' # что прогнозируем
HORIZON = 14 # прогноз на 1-14 суток

# чтобы Python видел код моделей из папок команды
for folder in [ROOT, ROOT / 'amur_pg_lstm']:
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


class DataSource(ABC):
    @abstractmethod
    def load(self) -> pd.DataFrame:
        """Возвращает таблицу данных."""


class CsvDataSource(DataSource):
    def __init__(self, path: Path = DATA_FILE):
        self.path = path

    def load(self) -> pd.DataFrame:
        return pd.read_csv(self.path, parse_dates=['date']).set_index('date').sort_index()


def load_data():
    return CsvDataSource().load()


# шаблон
class Model(ABC):
    # шаблон: каждая модель обязана заполнить _fit (обучение) и _forecast_from (14 прогнозов от даты)
    name = 'модель'

    @abstractmethod
    def _fit(self, train):
        """Обучение на таблице train."""

    @abstractmethod
    def _forecast_from(self, date):
        """Список из 14 прогнозов уровня (см) от даты date."""

    def fit(self, df, train_end=None):
        # обучение на данных до train_end включительно
        self.df = df
        self.train_end = pd.Timestamp(train_end) if train_end else df.index[-1]
        self.cache = {}
        self._fit(df.loc[:self.train_end])
        return self

    def predict(self, date, h):
        # прогноз уровня (см) на день date + h, сделанный в день date
        date = pd.Timestamp(date)
        if date not in self.cache: # все 14 горизонтов считаем один раз на дату
            self.cache[date] = self._forecast_from(date)
        return float(self.cache[date][h - 1])

    def forecast(self, date):
        # таблица прогноза на 1-14 суток от даты date
        date = pd.Timestamp(date)
        return pd.DataFrame([{'model': self.name, 'horizon': h,
                              'date': (date + pd.Timedelta(days=h)).date(),
                              'level': round(self.predict(date, h), 1)} for h in range(1, HORIZON + 1)])


# инерционный прогноз (с чем будет сравниваться)
class NaiveModel(Model):
    name = 'Инерционный'

    def _fit(self, train):
        pass

    def _forecast_from(self, date):
        return [self.df.at[date, TARGET]] * HORIZON


# линейная модель
class LinearModel(Model):
    name = 'Линейная (Ridge)'

    def _fit(self, train):
        from linear_model.model import LinearFloodModel
        self.model = LinearFloodModel(target_col=TARGET, horizon=HORIZON).fit(train)
        self.X = self.model._build_features(self.df)

    def _forecast_from(self, date):
        return self.model.forecast(self.df, date=date, X=self.X)['level'].tolist()


# PG-LSTM
class PgLstmModel(Model):
    # берётся уже обученная сеть из amur_pg_lstm/model/ (обучена на данных до 2018 г.)
    name = 'PG-LSTM'

    def _fit(self, train):
        import pg_lstm
        self.lib = pg_lstm
        self.model, self.cfg = pg_lstm.load_model(ROOT / 'amur_pg_lstm' / 'model' / 'pg_lstm_khabarovsk.pt')

    def _forecast_from(self, date):
        return self.lib.forecast(self.df, self.model, self.cfg, date=date)['level'].tolist()


# prophet
class ProphetModel(Model):
    # сезонная кривая: прогноз зависит только от дня, на который он дан
    name = 'Prophet'

    def _fit(self, train):
        from prophet import Prophet
        data = train[TARGET].reset_index()
        data.columns = ['ds', 'y']
        self.model = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
        self.model.fit(data)

    def _forecast_from(self, date):
        days = pd.DataFrame({'ds': [date + pd.Timedelta(days=h) for h in range(1, HORIZON + 1)]})
        return self.model.predict(days)['yhat'].tolist()


# градиентный бустинг
def gpb_features(data):
    lev = data['level_khabarovsk']
    X = data.copy()
    for k in [1, 2, 3, 7, 14]:
        X[f'lev_{k}'] = lev.shift(k)
    X['diff_1'] = lev - lev.shift(1)
    X['diff_7'] = lev - lev.shift(7)
    for name, col in [('blag', 'level_blagoveshchensk'), ('poyar', 'level_poyarkovo'), ('lenin', 'level_leninskoe')]:
        X[f'{name}_diff_1'] = data[col] - data[col].shift(1)
        X[f'{name}_diff_7'] = data[col] - data[col].shift(7)
    X['blag_7'] = data['level_blagoveshchensk'].shift(7)
    X['poyar_7'] = data['level_poyarkovo'].shift(7)
    X['lenin_3'] = data['level_leninskoe'].shift(3)
    for col in ['local_water_input', 'amur_water_input', 'sungari_water_input', 'ussuri_water_input']:
        for w in [7, 14, 30]:
            X[f'{col}_{w}'] = data[col].rolling(w).sum()
    X['rain_7'] = data['precip'].rolling(7).sum()
    X['temp_7'] = data['temp'].rolling(7).mean()
    X['day'] = data.index.dayofyear
    return X


class GpbModel(Model):
    #обучение модели на 1-14 днях
    name = 'Бустинг (GPB)'

    def _fit(self, train):
        from sklearn.ensemble import GradientBoostingRegressor
        self.X = gpb_features(self.df)
        lev = train[TARGET]
        self.models = []
        for h in range(1, HORIZON + 1):
            data = self.X.loc[train.index].assign(y=lev.shift(-h) - lev).dropna()
            model = GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=4, random_state=0)
            self.models.append(model.fit(data.drop(columns='y'), data['y']))

    def _forecast_from(self, date):
        x = self.X.loc[[date]]
        return [self.df.at[date, TARGET] + m.predict(x)[0] for m in self.models]


# статистические тренды (common.py, seasonal_models.py)
TREND_KINDS = ['polynomial2', 'polynomial3', 'power', 'logarithmic', 'exponential']


class TrendModel(Model):
    # кривая «уровень от времени»; monthly=True - плюс поправка на месяц года

    def __init__(self, kind, monthly=False):
        self.kind, self.monthly = kind, monthly
        self.name = f"Тренд{'+месяц' if monthly else ''}: {kind}"

    def _coords(self, days):
        days = pd.DatetimeIndex(days)
        t = (days - self.origin).days.to_numpy(float) + 1
        return 2 * (t - 1) / (self.train_end - self.origin).days - 1, t / 1000.0, days.month.to_numpy()

    def _fit(self, train):
        from common import fit_model
        from seasonal_models import fit_monthly
        self.origin = self.df.index[0]
        real = train[train[TARGET + '_filled'] == 0] # только измеренные дни
        u, x, m = self._coords(real.index)
        y = real[TARGET].to_numpy()
        self.result = fit_monthly(self.kind, u, x, m, y) if self.monthly else fit_model(self.kind, u, x, y)

    def _forecast_from(self, date):
        from common import evaluate
        u, x, m = self._coords([date + pd.Timedelta(days=h) for h in range(1, HORIZON + 1)])
        if self.monthly:
            return list(self.result.predict(u, x, m))
        return list(evaluate(self.kind, self.result.coefficients, u, x))


# список всех моделей
MODELS = {
    'naive': NaiveModel,
    'linear': LinearModel,
    'pg_lstm': PgLstmModel,
    'prophet': ProphetModel,
    'gpb': GpbModel,
}
for kind in TREND_KINDS:
    MODELS[f'trend_{kind}'] = lambda k=kind: TrendModel(k)
    MODELS[f'trend_monthly_{kind}'] = lambda k=kind: TrendModel(k, monthly=True)


def make_model(key):
    # создаёт модель по короткому имени, например make_model('pg_lstm')
    if key not in MODELS:
        raise ValueError(f'Нет модели {key!r}. Есть: {", ".join(MODELS)}')
    return MODELS[key]()
