## Проект: Мониторинг и прогнозирование климатических рисков
Краткое описание проекта: автоматизированный мониторинг уровней воды на крупных реках России и прогнозирование паводковой опасности для объектов кредитных организаций

## Клонирование репозитория:
```bash
   git clone https://github.com/nastyushaaaa/flood_forecasting.git
```

## Прогноз уровня воды в Хабаровске

Пять временных моделей: полиномы 2-й и 3-й степени, степенная, логарифмическая и экспоненциальная функции.

```bash
python -m pip install -r requirements-models.txt
python run.py
```

- Расчётная книга: [amur_five_models.xlsx](amur_five_models.xlsx).
- Посуточный прогноз: [results/daily_forecast.csv](results/daily_forecast.csv).
- Описание моделей и загрузки: [FORECASTING.md](FORECASTING.md).
