## Проект: Мониторинг и прогнозирование климатических рисков
Краткое описание проекта: автоматизированный мониторинг уровней воды на крупных реках России и прогнозирование паводковой опасности для объектов кредитных организаций

## Клонирование репозитория:
```bash
   git clone https://github.com/nastyushaaaa/flood_forecasting.git
```

## Прогноз уровня воды в Хабаровске

Пять временных функций и пять отдельных вариантов с сезонностью по месяцам. Показатели MAE, RMSE, NSE, S/σΔ и P% рассчитаны отдельно для заблаговременности 1–30 суток.

```bash
python -m pip install -r requirements-models.txt
python evaluate_skill.py
```

- [Исходные модели, Excel](amur_five_models.xlsx).
- [Модели с месячной сезонностью, Excel](amur_monthly_models.xlsx).
- [Показатели по заблаговременности](results/metrics_by_lead.csv).
- [Базовый посуточный прогноз](results/baseline_daily_forecast.csv).
- [Сезонный посуточный прогноз](results/monthly_daily_forecast.csv).
- [Методика и порядок запуска](FORECASTING.md).
