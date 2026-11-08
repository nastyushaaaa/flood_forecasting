"""Проверка инверсии зависимостей: сравнение моделей работает с любыми моделями и любым источником данных.

Подставляем «поддельные» модель и источник данных — без CSV-файла и без настоящих моделей.
"""
import unittest

import numpy as np
import pandas as pd

from model_comparison import config
from model_comparison.models import predict_all
from predict import TARGET, DataSource, Model


class FakeDataSource(DataSource):
    """Источник данных в памяти: уровень всегда 100 см."""

    def load(self) -> pd.DataFrame:
        days = pd.date_range('2025-07-01', '2025-08-31', freq='D')
        return pd.DataFrame({TARGET: 100.0, TARGET + '_filled': 0}, index=days)


class ConstantModel(Model):
    """Модель, которая всегда прогнозирует 50 см."""
    name = 'Константа'

    def _fit(self, train):
        pass

    def _forecast_from(self, date):
        return [50.0] * 14


class DependencyInversionTest(unittest.TestCase):
    def test_predict_all_accepts_any_model(self):
        df = FakeDataSource().load()
        pairs = pd.DataFrame({'issue_date': [pd.Timestamp(config.TEST_START)], 'horizon': [3]})
        result = predict_all(df, pairs, models=[ConstantModel()])
        np.testing.assert_allclose(result['Константа'], [50.0])

    def test_model_without_methods_cannot_be_created(self):
        class BrokenModel(Model):
            pass
        with self.assertRaises(TypeError):
            BrokenModel()


if __name__ == '__main__':
    unittest.main()
