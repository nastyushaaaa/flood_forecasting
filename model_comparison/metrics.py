"""Метрики качества прогноза в одном месте (задача 2.1).

Все уровни и ошибки в сантиметрах над нулём поста.
"""
import numpy as np
import pandas as pd

from model_comparison.config import ALLOWED_ERROR_SHARE


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Средняя абсолютная ошибка, см: на сколько в среднем промахнулись."""
    return float(np.mean(np.abs(np.asarray(actual) - np.asarray(predicted))))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """S (RMSE), см: как MAE, но крупные промахи весят сильнее."""
    error = np.asarray(actual) - np.asarray(predicted)
    return float(np.sqrt(np.mean(error ** 2)))


def nse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Коэффициент Нэша–Сатклиффа: 1 — идеально, 0 — не лучше, чем всегда называть средний уровень."""
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    spread = np.sum((actual - actual.mean()) ** 2)
    if spread == 0:
        return float('nan')
    return float(1 - np.sum((actual - predicted) ** 2) / spread)


def sigma_delta(level: pd.Series, horizons: list[int], measured: pd.Series) -> dict[int, float]:
    """σΔ: насколько обычно меняется уровень за h суток.

    Args:
        level: уровень воды, см; индекс — даты подряд по суткам. Передаём только обучающий период.
        horizons: горизонты, сут.
        measured: True там, где уровень измерен, а не восстановлен; индекс тот же, что у `level`.

    Returns:
        Словарь {горизонт, сут: σΔ, см}.
    """
    result = {}
    for h in horizons:
        change = level.shift(-h) - level
        both_measured = measured & measured.shift(-h, fill_value=False)
        result[h] = float(change[both_measured].std(ddof=1))
    return result


def score(actual: np.ndarray, predicted: np.ndarray, sigma: float) -> dict[str, float]:
    """Все метрики для набора прогнозов одного горизонта.

    Args:
        actual: фактические уровни, см.
        predicted: прогнозы, см; в том же порядке, что `actual`.
        sigma: σΔ для этого горизонта, см.

    Returns:
        Словарь: n (число прогнозов), mae и rmse (см), nse, s_sigma (S/σΔ: ≤ 0,5 хорошо, ≤ 0,8 удовлетворительно),
        p_percent (доля прогнозов с ошибкой не больше 0,674·σΔ, %).
    """
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    s = rmse(actual, predicted)
    return {
        'n': len(actual),
        'mae': mae(actual, predicted),
        'rmse': s,
        'nse': nse(actual, predicted),
        's_sigma': s / sigma if sigma > 0 else float('nan'),
        'p_percent': float(np.mean(np.abs(actual - predicted) <= ALLOWED_ERROR_SHARE * sigma) * 100),
    }


def score_table(predictions: pd.DataFrame, sigmas: dict[int, float], by: list[str]) -> pd.DataFrame:
    """Метрики для каждой группы прогнозов.

    Args:
        predictions: таблица с колонками horizon, actual, pred (см) и колонками из `by`.
        sigmas: σΔ по горизонтам, см.
        by: колонки группировки, обязательно с 'horizon', например ['model', 'horizon'].

    Returns:
        Таблица: колонки из `by` и метрики из `score`, по строке на группу.
    """
    rows = []
    for keys, group in predictions.groupby(by):
        row = dict(zip(by, keys))
        row.update(score(group['actual'], group['pred'], sigmas[int(row['horizon'])]))
        rows.append(row)
    return pd.DataFrame(rows)
