import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from prophet import Prophet

plt.rcParams.update({"axes.grid": True, "grid.alpha": 0.3})

FILE = "data/amur_khabarovsk_clean_2002-2026.csv"   # файл с данными
DATE_COL = "date" # дата
VALUE_COL = "level_khabarovsk" # уровень воды, см
HORIZON = 365 # на сколько суток вперёд прогнозируем
TEST_DAYS = 365 # сколько последних суток оставляем для проверки
CRITICAL = 470 # критическая отметка, см
MAPE_MIN_ABS = 50 # для MAPE берём только дни, где |уровень| не меньше этого, см
OUTPUT_DIR = "output" # папка для результатов

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, OUTPUT_DIR)
os.makedirs(OUT, exist_ok=True)

# переименование колонок для данных
# для Prophet нужно 2 колонки: ds (дата) и y (значение)
df = pd.read_csv(os.path.join(BASE, FILE), parse_dates=[DATE_COL])
d = df.rename(columns={DATE_COL: "ds", VALUE_COL: "y"})[["ds", "y"]].dropna()
print(f"Данные: {d['ds'].min().date()} … {d['ds'].max().date()}, строк: {len(d)}") #период данных

# проверка модели на последнем году
# обучение модели на всём, кроме последнего года, и сравниваем прогноз с тем, что было на самом деле
cut = d["ds"].max() - pd.Timedelta(days=TEST_DAYS) #день, разделяющий график №1
train, test = d[d["ds"] <= cut], d[d["ds"] > cut] #делим данные на 2 части

m_test = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
m_test.fit(train)
pred = m_test.predict(test[["ds"]])

y = test["y"].values
p = pred["yhat"].values
err = y - p #ошибка прогноза

mae = np.mean(np.abs(err))  # средняя абсолютная ошибка, см
rmse = np.sqrt(np.mean(err ** 2))  # среднеквадратичная ошибка, см
ok = np.abs(y) >= MAPE_MIN_ABS  # уровень около 0 дал бы деление на ноль
mape = np.mean(np.abs(err[ok] / y[ok])) * 100  # средняя абсолютная процентная ошибка, %
coverage = np.mean((y >= pred["yhat_lower"].values) & (y <= pred["yhat_upper"].values)) * 100  # попадание в интервал, %
mae_naive = np.mean(np.abs(y - train["y"].iloc[-1]))  # наивный прогноз «как сегодня»

print(f"MAE (средняя абсолютная ошибка) = {mae:.1f} см")
print(f"RMSE (среднеквадратичная ошибка) = {rmse:.1f} см")
print(f"MAPE (средняя абсолютная процентная ошибка) = {mape:.1f} % "f"(по {ok.sum()} из {len(y)} дней, где |уровень| >= {MAPE_MIN_ABS} см)")
print(f"Coverage (доля истинных значений, попавших в доверительный интервал прогноза) = {coverage:.1f} % "f"(ожидается около 80 %)")
print(f"Для сравнения, MAE наивного прогноза (как сегодня): {mae_naive:.1f} см")
pd.DataFrame({"Показатель": ["MAE (средняя абсолютная ошибка), см",
                             "RMSE (среднеквадратичная ошибка), см",
                             "MAPE (средняя абсолютная процентная ошибка), %",
                             "Coverage (доля значений в доверительном интервале), %",
                             "MAE наивного прогноза (как сегодня), см"],
              "Значение": [mae, rmse, mape, coverage, mae_naive]}).round(1).to_csv(
    os.path.join(OUT, "metrics.csv"), index=False, sep=";", encoding="utf-8-sig")

# сравнение факта и прогноза
plt.figure(figsize=(11, 4))
plt.plot(train["ds"].tail(TEST_DAYS), train["y"].tail(TEST_DAYS), color="gray", lw=0.8, label="обучающая часть")
plt.plot(test["ds"], test["y"], "k", label="факт")
plt.plot(test["ds"], pred["yhat"], label="прогноз Prophet")
plt.fill_between(test["ds"], pred["yhat_lower"], pred["yhat_upper"], alpha=0.2)
plt.title("Сравнение факта и прогноза")
plt.ylabel("Уровень, см")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUT, "1_proverka.png"), dpi=150)
plt.show()

# новая модель для прогноза на будущее
# обучение происходит на всех данных
m = Prophet(yearly_seasonality=True, weekly_seasonality=False, daily_seasonality=False)
m.fit(d)
future = m.make_future_dataframe(periods=HORIZON) # добавляет в таблицу будущие даты
fc = m.predict(future) # yhat — прогноз, yhat_lower/upper — интервал

# ищем пик и сравниваем с верхней границей интервала
fut = fc[fc["ds"] > d["ds"].max()]
peak = fut.loc[fut["yhat"].idxmax()]
print(f"Ожидаемый пик: {peak['ds'].date()}, {peak['yhat']:.0f} см")
print("Верхняя граница достигает критической отметки:", "да" if (fut["yhat_upper"] >= CRITICAL).any() else "нет")

# график прогноза
plt.figure(figsize=(11, 4))
last = d[d["ds"] >= d["ds"].max() - pd.Timedelta(days=3 * 365)]
plt.plot(last["ds"], last["y"], "k", lw=0.8, label="факт")
plt.plot(fut["ds"], fut["yhat"], label="прогноз")
plt.fill_between(fut["ds"], fut["yhat_lower"], fut["yhat_upper"], alpha=0.2, label="интервал 80%")
plt.axhline(CRITICAL, color="red", ls="--", label="критическая отметка")
plt.title(f"Прогноз уровня воды на {HORIZON} суток")
plt.ylabel("Уровень, см")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(OUT, "2_prognoz.png"), dpi=150)
plt.show()

# тренд и годовая сезонность
fig = m.plot_components(fc)
ax_trend, ax_year = fig.axes[0], fig.axes[1]
ax_trend.set_title("Многолетний тренд")
ax_trend.set_xlabel("Год")
ax_trend.set_ylabel("Тренд, см")
ax_year.set_title("Годовая сезонность")
ax_year.set_xlabel("Время года")
ax_year.set_ylabel("Вклад сезона, см")
fig.tight_layout()
plt.savefig(os.path.join(OUT, "3_komponenty.png"), dpi=150)
plt.show()

# таблица
out = fut[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
out[["yhat", "yhat_lower", "yhat_upper"]] = out[["yhat", "yhat_lower", "yhat_upper"]].round(1)
out.to_csv(os.path.join(OUT, "prognoz.csv"), index=False, sep=";", encoding="utf-8-sig")
print(f"Результаты сохранены в папку: {OUT}")
