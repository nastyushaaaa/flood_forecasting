"""Сравнение всех моделей: метрики, фазы, график, лучшая модель (задачи 2.3–2.8).

Запуск из корня репозитория:
    python -m model_comparison.run_all

Результаты сохраняются в model_comparison/results/.
"""
import logging
import os
import warnings
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from model_comparison import config
from model_comparison.metrics import score_table, sigma_delta
from model_comparison.models import predict_all
from model_comparison.pairs import make_pairs
from model_comparison.phases import phase_of
from predict import MODELS, TARGET, CsvDataSource, DataSource, Model, make_model

logger = logging.getLogger(__name__)

# Цвета основных моделей на графике; статистические тренды рисуются серым
MAIN_COLORS = {
    'Инерционный': '#7f7f7f',
    'Линейная (Ridge)': '#1f77b4',
    'PG-LSTM': '#d62728',
    'Prophet': '#2ca02c',
    'Бустинг (GPB)': '#9467bd',
}
TREND_COLOR = '#bbbbbb'


def _collect_predictions(df: pd.DataFrame, pairs: pd.DataFrame, models: list[Model]) -> pd.DataFrame:
    """Одна длинная таблица: каждая пара для каждой модели, с ошибкой и фазой."""
    tables = []
    for name, values in predict_all(df, pairs, models).items():
        part = pairs.copy()
        part.insert(0, 'model', name)
        part['pred'] = values
        tables.append(part)
    predictions = pd.concat(tables, ignore_index=True)
    predictions['error'] = predictions['pred'] - predictions['actual']
    predictions['phase'] = phase_of(predictions['target_date'])
    return predictions


def plot_mae(metrics: pd.DataFrame, path: Path) -> None:
    """График MAE по горизонтам для всех моделей (задача 2.7)."""
    fig, ax = plt.subplots(figsize=(13, 6))
    for name, group in metrics.groupby('model'):
        if name in MAIN_COLORS:
            ax.plot(group['horizon'], group['mae'], 'o-', lw=2, color=MAIN_COLORS[name], label=name)
        else:
            ax.plot(group['horizon'], group['mae'], '-', lw=0.8, color=TREND_COLOR)
    ax.plot([], [], '-', lw=0.8, color=TREND_COLOR, label='Статистические тренды (10 шт.)')
    ax.set_xlabel('Горизонт прогноза, сут')
    ax.set_ylabel('MAE, см')
    ax.set_title(f'Ошибка прогноза по горизонтам ({config.TEST_START} … {config.TEST_END})')
    ax.set_xticks(config.HORIZONS)
    ax.grid(alpha=0.3)
    ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def best_models(metrics: pd.DataFrame, by_phase: pd.DataFrame) -> pd.DataFrame:
    """Модель с наименьшей MAE на каждом горизонте: за весь год и в каждой фазе (задача 2.8)."""
    both = pd.concat([metrics.assign(phase='весь год'), by_phase], ignore_index=True)
    best = both.loc[both.groupby(['phase', 'horizon'])['mae'].idxmin()]
    return best.sort_values(['phase', 'horizon']).reset_index(drop=True)


def main(data_source: DataSource, models: list[Model]) -> None:
    """Считает прогнозы всех моделей и сохраняет таблицы и график в `config.RESULTS_DIR`."""
    out = config.RESULTS_DIR
    out.mkdir(parents=True, exist_ok=True)

    # 2.2: данные и общие пары для всех моделей
    df = data_source.load()
    pairs = make_pairs(df)
    logger.info('Период проверки %s … %s, пар: %d', config.TEST_START, config.TEST_END, len(pairs))

    # 2.3 и 2.5: прогнозы всех моделей с фазой для каждого дня
    predictions = _collect_predictions(df, pairs, models)
    predictions.to_csv(out / 'predictions.csv', index=False, encoding='utf-8-sig')

    # σΔ по обучающему периоду, чтобы не подглядывать в проверку
    train = df.loc[:config.TRAIN_END]
    sigmas = sigma_delta(train[TARGET], config.HORIZONS, train[TARGET + '_filled'].eq(0))

    # 2.4: метрики всех моделей в одном CSV
    metrics = score_table(predictions, sigmas, by=['model', 'horizon'])
    metrics.to_csv(out / 'metrics.csv', index=False, encoding='utf-8-sig')

    # 2.6: метрики по фазам
    by_phase = score_table(predictions, sigmas, by=['phase', 'model', 'horizon'])
    by_phase.to_csv(out / 'metrics_by_phase.csv', index=False, encoding='utf-8-sig')

    # 2.7: график
    plot_mae(metrics, out / 'mae_by_horizon.png')

    # 2.8: лучшая модель на каждом горизонте
    best = best_models(metrics, by_phase)
    best.to_csv(out / 'best_by_horizon.csv', index=False, encoding='utf-8-sig')

    # итоговая таблица для CLI (print здесь разрешён, STYLEGUIDE п. 4.1)
    print('\nЛучшая модель на каждом горизонте (весь год):')
    print(best[best['phase'] == 'весь год'][['horizon', 'model', 'mae', 's_sigma', 'p_percent']]
          .round(2).to_string(index=False))
    print(f'\nРезультаты: {out}')


if __name__ == '__main__':
    logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'),
                        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s')
    # график рисуем в файл, без окон
    matplotlib.use('Agg')
    # PerformanceWarning из кода линейной модели не влияет на результат
    warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)
    logging.getLogger('cmdstanpy').setLevel(logging.WARNING)
    # точка сборки: только здесь выбираются конкретный источник данных и конкретные модели
    main(data_source=CsvDataSource(), models=[make_model(key) for key in MODELS])
