import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

data = pd.read_csv("amur_khabarovsk_clean_2002-2026.csv", parse_dates=["date"])
data = data.set_index("date")
print(data.shape)
print(data.isna().sum().sum())
print(data["level_khabarovsk"].describe())
lev = data["level_khabarovsk"]
X = data.copy()
X["lev_1"] = lev.shift(1)
X["lev_2"] = lev.shift(2)
X["lev_3"] = lev.shift(3)
X["lev_7"] = lev.shift(7)
X["lev_14"] = lev.shift(14)
X["diff_1"] = lev - lev.shift(1)
X["diff_7"] = lev - lev.shift(7)
blag = data["level_blagoveshchensk"]
poyar = data["level_poyarkovo"]
lenin = data["level_leninskoe"]
X["blag_diff_1"] = blag - blag.shift(1)
X["blag_diff_7"] = blag - blag.shift(7)
X["blag_7"] = blag.shift(7)
X["poyar_diff_1"] = poyar - poyar.shift(1)
X["poyar_diff_7"] = poyar - poyar.shift(7)
X["poyar_7"] = poyar.shift(7)
X["lenin_diff_1"] = lenin - lenin.shift(1)
X["lenin_diff_7"] = lenin - lenin.shift(7)
X["lenin_3"] = lenin.shift(3)




for col in ["local_water_input", "amur_water_input", "sungari_water_input", "ussuri_water_input"]:
    X[col + "_7"] = data[col].rolling(7).sum()
    X[col + "_14"] = data[col].rolling(14).sum()
    X[col + "_30"] = data[col].rolling(30).sum()
X["rain_7"] = data["precip"].rolling(7).sum()
X["temp_7"] = data["temp"].rolling(7).mean()
X["day"] = data.index.dayofyear
y_1 = lev.shift(-1) - lev
y_14 = lev.shift(-14) - lev


split = "2019-01-01"
levels = [300, 470, 550]


def check(real, pred):
    for l in levels:
        real_up = real >= l
        pred_up = pred >= l
        print(l, "см было дней", real_up.sum(), "угадали", (real_up & pred_up).sum(),
              "лишних тревог", (pred_up & ~real_up).sum())



d1 = X.copy()
d1["y"] = y_1
d1 = d1.dropna()
train = d1[d1.index < split]
test = d1[d1.index >= split]
model_1 = GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=4)
model_1.fit(train.drop(columns="y"), train["y"])
pred_1 = test["level_khabarovsk"] + model_1.predict(test.drop(columns="y"))
real_1 = test["level_khabarovsk"] + test["y"]
print("на 1 день")
print("ошибка модели:", mean_absolute_error(real_1, pred_1))
print("ошибка если сказать что уровень не изменится:", mean_absolute_error(real_1, test["level_khabarovsk"]))
check(real_1, pred_1)
d14 = X.copy()
d14["y"] = y_14
d14 = d14.dropna()
train = d14[d14.index < split]
test = d14[d14.index >= split]

model_14 = GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=4)
model_14.fit(train.drop(columns="y"), train["y"])

pred_14 = test["level_khabarovsk"] + model_14.predict(test.drop(columns="y"))
real_14 = test["level_khabarovsk"] + test["y"]
print("на 14 дней")
print("ошибка модели:", mean_absolute_error(real_14, pred_14))
print("ошибка если сказать что уровень не изменится:", mean_absolute_error(real_14, test["level_khabarovsk"]))
check(real_14, pred_14)

fig, ax = plt.subplots(2, 1, figsize=(14, 8))
ax[0].plot(real_1.index, real_1, label="реальный", color="black")
ax[0].plot(pred_1.index, pred_1, label="прогноз", color="blue")
ax[0].set_title("Хабаровск, прогноз на 1 день")
ax[1].plot(real_14.index, real_14, label="реальный", color="black")
ax[1].plot(pred_14.index, pred_14, label="прогноз", color="blue")
ax[1].set_title("Хабаровск, прогноз на 14 дней")
for a in ax:
    a.axhline(300, color="yellow", linestyle="--")
    a.axhline(470, color="orange", linestyle="--")
    a.axhline(550, color="red", linestyle="--")
    a.legend()
    a.grid()
plt.tight_layout()
plt.savefig("forecast.png")


def level_name(x):
    if x >= 550:
        return "опасное явление"
    elif x >= 470:
        return "неблагоприятное явление"
    elif x >= 300:
        return "повышенная готовность"
    else:
        return "норм"

last = X.dropna().iloc[[-1]]
last_date = last.index[0]
now = last["level_khabarovsk"].iloc[0]
f_1 = now + model_1.predict(last)[0]
f_14 = now + model_14.predict(last)[0]
print("последний день:", last_date.date(), "уровень", now)
print("завтра:", round(f_1), level_name(f_1))
print("через 14 дней:", round(f_14), level_name(f_14))