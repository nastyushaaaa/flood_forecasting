"""Прогнозы всех моделей для пар проверки (задача 2.3).

Модели берутся из `predict.py`: у каждой одинаковый вид `model.predict(date, h)`.
"""
import logging
import time

import numpy as np
import pandas as pd

from model_comparison import config
from predict import MODELS, make_model

logger = logging.getLogger(__name__)


def predict_all(df: pd.DataFrame, pairs: pd.DataFrame) -> dict[str, np.ndarray]:
    """Обучает каждую модель до `config.TRAIN_END` и получает её прогнозы для всех пар.

    Args:
        df: общая таблица данных; индекс — даты.
        pairs: пары из `pairs.make_pairs` (колонки issue_date и horizon).

    Returns:
        Словарь {название модели: прогнозы уровня, см, в порядке строк `pairs`}.
        Модель, которая упала с ошибкой, пропускается, остальные считаются дальше.
    """
    result = {}
    for key in MODELS:
        model = make_model(key)
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
