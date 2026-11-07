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


## Что где лежит

| Папка или файл | Что это |
|---|---|
| `data/amur_khabarovsk_clean_2002-2026.csv` | **Единственный файл данных проекта**: уровни 4 постов и погода по бассейну, по суткам с 2002 года |
| `predict.py` | Обёртки над всеми моделями: одинаковый вид `model.predict(дата, h)` |
| `run.py` | Прогноз одной или всеми моделями |
| `linear_model/` | Линейная модель (Ridge) |
| `amur_pg_lstm/` | PG-LSTM: нейросеть с физикой, блокнот, обученная модель, исходные выгрузки |
| `prophet_model/` | Prophet: сезонный прогноз на год |
| `alex_gpb/` | Градиентный бустинг |
| `common.py`, `seasonal_models.py`, `evaluate_skill.py` и др. | Статистические модели тренда (10 штук), подробности в [FORECASTING.md](FORECASTING.md) |
| `parse_all_rivers.py` | Парсер уровней воды с allrivers.info |
| `main.py`, `hourly_forecast.py` | Веб-сервис: почасовой прогноз погоды Open-Meteo |

## Установка

Нужен Python 3.10–3.13.

```bash
git clone https://github.com/nastyushaaaa/flood_forecasting.git
cd flood_forecasting

python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium      # нужно только для парсера allrivers.info
```

## Прогноз: `run.py`

Все команды запускаются из корня репозитория.

```bash
python run.py --help                                  # подсказка и список моделей
python run.py --model all                             # все модели, прогноз от последней даты в данных
python run.py --model pg_lstm                         # одна модель
python run.py --model linear,gpb --date 2026-07-20    # несколько моделей, прогноз от выбранной даты
```

На экран выводится таблица «горизонт × модель», и она же сохраняется в `results/forecast_<дата>.csv`. Бустинг обучается несколько минут, остальные модели быстрее.

| Имя для `--model` | Модель |
|---|---|
| `naive` | Инерционный прогноз «уровень не изменится», точка отсчёта |
| `linear` | Линейная модель (Ridge) |
| `pg_lstm` | PG-LSTM |
| `prophet` | Prophet |
| `gpb` | Градиентный бустинг |
| `trend_<вид>`, `trend_monthly_<вид>` | Статистические тренды: `polynomial2`, `polynomial3`, `power`, `logarithmic`, `exponential` |