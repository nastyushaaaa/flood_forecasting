"""Прогнозы всех моделей для пар проверки (задача 2.3).

Список моделей передают снаружи; модуль работает только с абстракцией `predict.Model`.
"""
import logging
import time

import numpy as np
import pandas as pd

from model_comparison import config
from predict import Model

logger = logging.getLogger(__name__)


def predict_all(df: pd.DataFrame, pairs: pd.DataFrame, models: list[Model]) -> dict[str, np.ndarray]:
    """Обучает каждую модель до `config.TRAIN_END` и получает её прогнозы для всех пар.

    Args:
        df: общая таблица данных; индекс — даты.
        pairs: пары из `pairs.make_pairs` (колонки issue_date и horizon).
        models: модели для сравнения; любые наследники `predict.Model`.

    Returns:
        Словарь {название модели: прогнозы уровня, см, в порядке строк `pairs`}.
        Модель, которая упала с ошибкой, пропускается, остальные считаются дальше.
    """
    result = {}
    for model in models:
        started = time.time()
        logger.info('%s: обучение до %s', model.name, config.TRAIN_END)
        try:
            model.fit(df, train_end=config.TRAIN_END)
            forecasts = [model.predict(day, h) for day, h in zip(pairs['issue_date'], pairs['horizon'])]
        except (ValueError, KeyError, RuntimeError, ImportError, FileNotFoundError):
            # одна сломанная модель не должна останавливать сравнение остальных
            logger.exception('%s: модель пропущена', model.name)
            continue
        result[model.name] = np.array(forecasts)
        logger.info('%s: готово за %.0f с', model.name, time.time() - started)
    return result
