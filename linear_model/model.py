import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer # медиана вместо пропуска
from sklearn.linear_model import Ridge # линейная регрессия (без переобучения)
from sklearn.pipeline import Pipeline # конвейер - объединение шагов
from sklearn.preprocessing import StandardScaler # нормализация


class LinearFloodModel:
    """Линейная baseline-модель (Ridge) на 14 суток."""

    def __init__(self, target_col='level_khabarovsk', lags=14, alpha=1.0, horizon=14, drop_filled=True):
        self.target_col = target_col
        self.lags = lags
        self.alpha = alpha
        self.horizon = horizon
        self.drop_filled = drop_filled
        
        self.models = []
        self.feature_cols = None
        self.err_q10 = None #перцентили
        self.err_q90 = None

    def _prepare_df(self, clean):
        df = clean.copy()
        if 'date' in df.columns:
            df = df.set_index('date')
        return df.sort_index() # сортируем по дате

    # подготовка признаков
    def _build_features(self, df):
        # все числовые колонки, кроме _filled
        num_cols = [c for c in df.select_dtypes(include='number').columns if not c.endswith('_filled')]
        X = pd.DataFrame(index=df.index)
        
        # заполняем пустую таблицу со сдвигом на lag
        for c in num_cols:
            for lag in range(1, self.lags + 1):
                X[f'{c}_lag{lag}'] = df[c].shift(lag)
                
        # считаем сезоны по дням
        doy = df.index.dayofyear
        X['sin_doy'] = np.sin(2 * np.pi * doy / 365.25)
        X['cos_doy'] = np.cos(2 * np.pi * doy / 365.25)
        
        return X.dropna(axis=1, how='all') # возвращаем таблицу без полностью пустых столбцов

    def fit(self, clean):
        df = self._prepare_df(clean)
        X = self._build_features(df)
        self.feature_cols = X.columns.tolist()

        # только дни с реальными данными
        if self.drop_filled and f'{self.target_col}_filled' in df.columns:
            valid_start = df[f'{self.target_col}_filled'].eq(0)
        else:
            valid_start = pd.Series(True, index=df.index)

        self.models, residuals = [], []
        
        # обучение
        for h in range(1, self.horizon + 1):
            y = df[self.target_col].shift(-h) - df[self.target_col] # приращение уровня со сдвигом вверх по таблице
            mask = y.notna() & X.notna().all(axis=1) & valid_start # фильтр на строки
            
            if self.drop_filled and f'{self.target_col}_filled' in df.columns:
                mask &= df[f'{self.target_col}_filled'].shift(-h).fillna(1).eq(0) # прогноз на реальный день
                
            X_tr, y_tr = X[mask], y[mask]
            if len(X_tr) < 50:
                raise ValueError(f'Мало данных для горизонта {h}: {len(X_tr)}')
                
            pipe = Pipeline([
                ('imputer', SimpleImputer(strategy='median')),
                ('scaler', StandardScaler()),
                ('ridge', Ridge(alpha=self.alpha)),
            ])
            pipe.fit(X_tr, y_tr) # запуск обучения
            self.models.append(pipe)
            residuals.append(y_tr - pipe.predict(X_tr)) # считаем ошибку модели

        # работа с ошибками
        self.err_q10 = np.array([np.percentile(r, 10) for r in residuals])
        self.err_q90 = np.array([np.percentile(r, 90) for r in residuals])
        return self

    # прогноз
    def forecast(self, clean, date=None, X=None):
        """Возвращает DataFrame с прогнозом (date, horizon, level, level_low, level_high)."""
        df = self._prepare_df(clean)
        if X is None:
            X = self._build_features(df)
            
        t = len(df) - 1 if date is None else df.index.get_loc(pd.Timestamp(date)) # индекс сегодня/последего дня
        x_t = X.iloc[[t]].reindex(columns=self.feature_cols)
        
        if x_t.isna().all(axis=1).any():
            raise ValueError('Недостаточно истории для признаков на эту дату')

        # прогон по 14-ти моделям
        d = np.array([m.predict(x_t)[0] for m in self.models]) # дельта
        h0 = df[self.target_col].iloc[t] # текущий уровень воды
        
        levels = h0 + d
        low, high = levels + self.err_q10, levels + self.err_q90 # вилка прогноза
        
        dates = [df.index[t] + pd.Timedelta(days=h) for h in range(1, self.horizon + 1)]
        
        return pd.DataFrame({
            'date': dates,
            'horizon': np.arange(1, self.horizon + 1),
            'level': np.round(levels, 1),
            'level_low': np.round(low, 1),
            'level_high': np.round(high, 1),
        })