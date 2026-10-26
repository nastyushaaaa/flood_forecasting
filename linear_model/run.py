# linear_model/run.py
import sys
from pathlib import Path
import pandas as pd

# Чтобы скрипт видел папку linear_model, даже если запускается из корня
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from linear_model.model import LinearFloodModel

def main():
    # Путь к вашему общему файлу данных (поднимись на уровень выше и зайди в data)
    data_path = Path(__file__).resolve().parents[1] / 'data' / 'amur_khabarovsk_clean_2002-2026.csv'
    
    df = pd.read_csv(data_path, parse_dates=['date']).set_index('date').sort_index()
    
    # Делим на train и test (например, тест с 2023 года)
    train = df[df.index < '2023-01-01']
    test = df[df.index >= '2023-01-01']
    
    print(f"Train: {train.index.min().date()} .. {train.index.max().date()} ({len(train)} дней)")
    print(f"Test:  {test.index.min().date()} .. {test.index.max().date()} ({len(test)} дней)")

    model = LinearFloodModel(target_col='level_khabarovsk', lags=14, alpha=1.0)
    model.fit(train)
    print(f"Модель обучена. Используется признаков: {len(model.feature_cols)}")

    # Считаем признаки для всего датасета (они используют только прошлое)
    X_all = model._build_features(df)
    
    # Собираем прогнозы для тестовой выборки
    records = []
    for date in test.index[:-14]:
        fc = model.forecast(df, date=date, X=X_all)
        for _, row in fc.iterrows():
            if row['date'] in test.index:
                records.append({
                    'date': row['date'], 
                    'horizon': row['horizon'],
                    'pred': row['level'],
                    'actual': test.loc[row['date'], 'level_khabarovsk'],
                })
    res = pd.DataFrame(records)

    # Считаем метрики
    mae = (res['pred'] - res['actual']).abs().mean()
    rmse = ((res['pred'] - res['actual'])**2).mean()**0.5
    print(f"\nОбщие метрики на тесте:\nMAE = {mae:.2f} см\nRMSE = {rmse:.2f} см")
    
    # Сохраняем прогнозы в свою папку
    out_path = Path(__file__).resolve().parent / 'predictions.csv'
    res.to_csv(out_path, index=False)
    print(f"Результаты сохранены в {out_path.name}")

    print(f"\nПример прогноза на 14 дней от {df.index[-1].date()}:")
    print(model.forecast(df, X=X_all).to_string(index=False))

if __name__ == '__main__':
    main()