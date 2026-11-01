"""Общий интерфейс моделей прогноза уровня воды.

Сервер и скрипты оценки работают с моделью только через эти методы, поэтому любую модель
(линейную, GPB, Prophet, PG-LSTM) можно подставить без изменения вызывающего кода.
"""
from abc import ABC, abstractmethod

import pandas as pd


class FloodModel(ABC):
    """Модель, которая обучается на истории и прогнозирует уровень на `horizon` суток вперёд."""

    @abstractmethod
    def fit(self, clean: pd.DataFrame) -> 'FloodModel':
        """Обучает модель.

        Args:
            clean: суточный ряд, индекс или колонка `date`, уровни в см над нулём поста.

        Returns:
            Эта же модель, чтобы можно было писать `model.fit(df).forecast(df)`.
        """

    @abstractmethod
    def forecast(self, clean: pd.DataFrame, date=None) -> pd.DataFrame:
        """Прогноз от даты `date` (по умолчанию от последнего дня ряда).

        Args:
            clean: суточный ряд в том же формате, что и для `fit`.
            date: дата выпуска прогноза; None — последний день ряда.

        Returns:
            Таблица с колонками date, horizon, level, level_low, level_high; уровни в см.
        """
