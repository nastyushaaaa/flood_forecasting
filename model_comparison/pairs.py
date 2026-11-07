"""Пары для проверки: одни и те же для всех моделей (задачи 2.2 и 2.3).

Пара — это день выпуска прогноза, горизонт h и день, на который дан прогноз.
"""
import pandas as pd

from model_comparison import config
from predict import TARGET


def make_pairs(df: pd.DataFrame) -> pd.DataFrame:
    """Все пары периода проверки.

    Для каждого дня проверки и каждого горизонта h прогноз выпускается за h суток до этого дня.
    Пары, где уровень в день выпуска или в проверяемый день восстановлен, а не измерен, не берём.

    Args:
        df: общая таблица данных (`predict.load_data()`); индекс — даты.

    Returns:
        Таблица с колонками issue_date, horizon (сут), target_date, initial и actual (уровни, см).
    """
    filled = df[TARGET + '_filled']
    rows = []
    for target_date in pd.date_range(config.TEST_START, config.TEST_END, freq='D'):
        for h in config.HORIZONS:
            issue_date = target_date - pd.Timedelta(days=h)
            if filled.get(target_date, 1) == 0 and filled.get(issue_date, 1) == 0:
                rows.append({
                    'issue_date': issue_date,
                    'horizon': h,
                    'target_date': target_date,
                    'initial': float(df.at[issue_date, TARGET]),
                    'actual': float(df.at[target_date, TARGET]),
                })
    return pd.DataFrame(rows)
