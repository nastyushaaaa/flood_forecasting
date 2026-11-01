"""Прогноз уровня воды у Хабаровска на 1–14 суток.

Запуск из корня репозитория:
    python run.py --model all # все модели
    python run.py --model linear # одна модель
    python run.py --model linear,pg_lstm # несколько моделей
    python run.py --model all --date 2026-07-20 # прогноз от выбранной даты
"""
import argparse
from pathlib import Path

import pandas as pd

from predict import MODELS, load_data, make_model

# читаем, что попросили в командной строке
parser = argparse.ArgumentParser(description='Прогноз уровня воды на 1–14 суток')
parser.add_argument('--model', default='all', help='all или имена через запятую: ' + ', '.join(MODELS))
parser.add_argument('--date', default=None, help='дата прогноза ГГГГ-ММ-ДД (по умолчанию — последняя в данных)')
args = parser.parse_args()

keys = list(MODELS) if args.model == 'all' else args.model.split(',')

# данные и дата прогноза
df = load_data()
date = pd.Timestamp(args.date) if args.date else df.index[-1]
print(f'Прогноз от {date.date()}, уровень в этот день: {df.at[date, "level_khabarovsk"]:.0f} см')

# каждая модель: обучаем на данных до даты прогноза и берём прогноз на 1-14 суток
tables = []
for key in keys:
    model = make_model(key)
    print('→', model.name)
    model.fit(df, train_end=date)
    tables.append(model.forecast(date))

# таблица: строки - дни, столбцы - модели
result = pd.concat(tables)
wide = result.pivot(index=['horizon', 'date'], columns='model', values='level')
print(wide.to_string())

# сохраняем в results/forecast_<дата>.csv
Path('results').mkdir(exist_ok=True)
path = Path('results') / f'forecast_{date.date()}.csv'
result.to_csv(path, index=False, encoding='utf-8-sig')
print('Сохранено:', path)