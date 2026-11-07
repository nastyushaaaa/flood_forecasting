import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Чтобы скрипт видел папку linear_model, даже если запускается из корня
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from linear_model.model import LinearFloodModel


# ---------- вспомогательные функции ----------

def sigma_delta_by_horizon(series: pd.Series, horizons) -> dict:
    """
    σΔ — СКО фактического приращения уровня за время прогноза h.
    Считается по историческим (train) данным: Δ_h(t) = level(t+h) - level(t).
    Возвращает {h: sigma}.
    """
    out = {}
    for h in horizons:
        deltas = series.shift(-h) - series
        out[h] = float(deltas.std(ddof=1))
    return out


def nash_sutcliffe(obs: np.ndarray, sim: np.ndarray) -> float:
    denom = np.sum((obs - obs.mean()) ** 2)
    if denom == 0:
        return float('nan')
    return 1.0 - np.sum((obs - sim) ** 2) / denom


# ---------- графики ----------

def plot_results(res, per_h, df, model, X_all, target, horizon, out_dir):
    # 1) Обзорная фигура: факт vs прогноз (h=1), scatter, гистограмма ошибок, метрики по h
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))

    # Факт vs прогноз на горизонте 1 день
    ax = axes[0, 0]
    h1 = res[res['horizon'] == 1].sort_values('date')
    ax.plot(h1['date'], h1['actual'], label='Факт', color='black', lw=1.2)
    ax.plot(h1['date'], h1['pred'], label='Прогноз (h=1)', color='tab:red', lw=0.9, alpha=0.85)
    ax.set_title('Факт vs Прогноз (горизонт 1 день)')
    ax.set_ylabel('Уровень, см')
    ax.legend()
    ax.grid(alpha=0.3)

    # Scatter
    ax = axes[0, 1]
    ax.scatter(res['actual'], res['pred'], s=6, alpha=0.35, color='tab:blue')
    lo = float(min(res['actual'].min(), res['pred'].min()))
    hi = float(max(res['actual'].max(), res['pred'].max()))
    ax.plot([lo, hi], [lo, hi], 'k--', lw=1, label='y = x')
    ax.set_xlabel('Факт, см')
    ax.set_ylabel('Прогноз, см')
    ax.set_title('Диаграмма рассеяния')
    ax.legend()
    ax.grid(alpha=0.3)

    # Распределение ошибок
    ax = axes[1, 0]
    ax.hist(res['error'], bins=60, color='tab:green', alpha=0.75, edgecolor='black', linewidth=0.3)
    ax.axvline(0, color='k', linestyle='--', lw=1)
    ax.set_xlabel('Ошибка (прогноз − факт), см')
    ax.set_ylabel('Частота')
    ax.set_title('Распределение ошибок')
    ax.grid(alpha=0.3)

    # Метрики по горизонтам
    ax = axes[1, 1]
    ax.plot(per_h['h'], per_h['mae'], 'o-', label='MAE', color='tab:orange')
    ax.plot(per_h['h'], per_h['rmse'], 's-', label='S (RMSE)', color='tab:red')
    ax.set_xlabel('Горизонт прогноза, дней')
    ax.set_ylabel('Ошибка, см')
    ax.set_title('Метрики по горизонтам')
    ax.grid(alpha=0.3)
    ax.legend(loc='upper left')
    ax2 = ax.twinx()
    ax2.plot(per_h['h'], per_h['s_sigma'], '^--', label='S/σΔ', color='tab:purple', alpha=0.75)
    ax2.axhline(0.5, color='green', linestyle=':', lw=1)
    ax2.axhline(0.8, color='orange', linestyle=':', lw=1)
    ax2.set_ylabel('S/σΔ')
    ax2.legend(loc='upper right')

    fig.tight_layout()
    p1 = out_dir / 'metrics_overview.png'
    fig.savefig(p1, dpi=130)
    plt.close(fig)
    print(f'Сохранён график: {p1.name}')

    # 2) Финальный прогноз на horizon дней вперёд с доверительным интервалом
    fc = model.forecast(df, X=X_all)
    history = df[target].iloc[-60:]

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(history.index, history.values, label='История (60 дней)', color='black', lw=1.2)
    ax.plot(fc['date'], fc['level'], 'o-', label='Прогноз', color='tab:red', lw=1.3)
    ax.fill_between(fc['date'], fc['level_low'], fc['level_high'],
                    alpha=0.25, color='tab:red', label='80% интервал (q10–q90)')
    ax.axvline(history.index[-1], color='gray', linestyle='--', lw=1)
    ax.set_title(f'Прогноз на {horizon} дней от {df.index[-1].date()}')
    ax.set_ylabel('Уровень, см')
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p2 = out_dir / 'final_forecast.png'
    fig.savefig(p2, dpi=130)
    plt.close(fig)
    print(f'Сохранён график: {p2.name}')

    # 3) Критерии Росгидромета: S/σΔ и P% по горизонтам
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))

    ax = axes[0]
    colors = ['green' if v <= 0.5 else 'orange' if v <= 0.8 else 'red'
              for v in per_h['s_sigma']]
    ax.bar(per_h['h'], per_h['s_sigma'], color=colors)
    ax.axhline(0.5, color='green', linestyle='--', lw=1, label='≤0.5 — хорошо')
    ax.axhline(0.8, color='orange', linestyle='--', lw=1, label='≤0.8 — удовлетворительно')
    ax.set_xlabel('Горизонт, дней')
    ax.set_ylabel('S/σΔ')
    ax.set_title('Критерий Росгидромета: S/σΔ')
    ax.legend()
    ax.grid(alpha=0.3, axis='y')

    ax = axes[1]
    ax.bar(per_h['h'], per_h['p'], color='tab:blue')
    ax.set_xlabel('Горизонт, дней')
    ax.set_ylabel('P, %')
    ax.set_title('Оправдываемость P% (|err| ≤ 0.674·σΔ)')
    ax.set_ylim(0, 100)
    ax.grid(alpha=0.3, axis='y')

    fig.tight_layout()
    p3 = out_dir / 'roshydromet_criteria.png'
    fig.savefig(p3, dpi=130)
    plt.close(fig)
    print(f'Сохранён график: {p3.name}')


# ---------- основной сценарий ----------

def main():
    data_path = Path(__file__).resolve().parents[1] / 'data' / 'amur_khabarovsk_clean_2002-2026.csv'
    df = pd.read_csv(data_path, parse_dates=['date']).set_index('date').sort_index()

    target = 'level_khabarovsk'
    horizon = 14

    # Делим на train / test (тест с 2023 года)
    train = df[df.index < '2023-01-01']
    test = df[df.index >= '2023-01-01']

    print(f'Train: {train.index.min().date()} .. {train.index.max().date()} ({len(train)} дней)')
    print(f'Test:  {test.index.min().date()} .. {test.index.max().date()} ({len(test)} дней)')

    # Обучаем
    model = LinearFloodModel(target_col=target, lags=14, alpha=1.0, horizon=horizon)
    model.fit(train)
    print(f'Модель обучена. Используется признаков: {len(model.feature_cols)}')

    # Считаем признаки на всём датасете (они используют только прошлое)
    X_all = model._build_features(df)

    # Собираем прогнозы для тестовой выборки
    records = []
    for date in test.index[:-horizon]:
        fc = model.forecast(df, date=date, X=X_all)
        for _, row in fc.iterrows():
            if row['date'] in test.index:
                records.append({
                    'date': row['date'],
                    'horizon': int(row['horizon']),
                    'pred': float(row['level']),
                    'actual': float(test.loc[row['date'], target]),
                })
    res = pd.DataFrame(records)

    # ---- σΔ по горизонтам (по train, чтобы не подсматривать в тест) ----
    sigmas = sigma_delta_by_horizon(train[target], range(1, horizon + 1))
    res['sigma_delta'] = res['horizon'].map(sigmas)

    # ---- Ошибки ----
    res['error'] = res['pred'] - res['actual']
    res['abs_error'] = res['error'].abs()
    res['allowable'] = 0.674 * res['sigma_delta']

    # ---------- ОБЩИЕ МЕТРИКИ ----------
    mae = float(res['abs_error'].mean())
    rmse = float(np.sqrt((res['error'] ** 2).mean()))

    obs_all = res['actual'].values
    sim_all = res['pred'].values
    nse = nash_sutcliffe(obs_all, sim_all)

    # S/σΔ: делим общий RMSE на среднее σΔ по всем горизонтам (взвешенное по кол-ву прогнозов)
    mean_sigma = float(res['sigma_delta'].mean())
    s_sigma = rmse / mean_sigma if mean_sigma > 0 else float('nan')

    # P%: доля прогнозов, у которых |err| ≤ 0.674·σΔ
    p_ok = float((res['abs_error'] <= res['allowable']).mean() * 100.0)

    line = '=' * 60
    print(f'\n{line}')
    print(f'МЕТРИКИ КАЧЕСТВА ПРОГНОЗА на тесте ({len(res)} прогнозов)')
    print(f'{line}')
    print(f'MAE        = {mae:6.2f} см')
    print(f'S (RMSE)   = {rmse:6.2f} см')
    print(f'NSE        = {nse:6.3f}')
    print(f'S/σΔ       = {s_sigma:6.3f}')
    print(f'P%         = {p_ok:5.1f} %')
    print(f'{line}')

    # ---------- МЕТРИКИ ПО ГОРИЗОНТАМ ----------
    print('\nМетрики по горизонтам (дней вперёд):')
    print(f"{'h':>3} {'MAE':>8} {'S(RMSE)':>9} {'NSE':>8} {'S/σΔ':>8} {'P%':>7}")
    per_h_rows = []
    for h, grp in res.groupby('horizon'):
        m = float(grp['abs_error'].mean())
        s = float(np.sqrt((grp['error'] ** 2).mean()))
        sd = sigmas[int(h)]
        p = float((grp['abs_error'] <= 0.674 * sd).mean() * 100.0)
        obs_h = grp['actual'].values
        sim_h = grp['pred'].values
        nse_h = nash_sutcliffe(obs_h, sim_h)
        per_h_rows.append({'h': int(h), 'mae': m, 'rmse': s, 'nse': nse_h,
                           's_sigma': s / sd if sd > 0 else float('nan'), 'p': p})
        print(f'{int(h):>3} {m:>8.2f} {s:>9.2f} {nse_h:>8.3f} '
              f'{(s / sd if sd > 0 else float("nan")):>8.3f} {p:>6.1f}%')
    per_h = pd.DataFrame(per_h_rows)

    # ---------- СОХРАНЯЕМ ----------
    out_dir = Path(__file__).resolve().parent
    res.to_csv(out_dir / 'predictions.csv', index=False)
    per_h.to_csv(out_dir / 'metrics_by_horizon.csv', index=False)
    print(f'\nРезультаты сохранены в:')
    print(f'  • {out_dir / "predictions.csv"}')
    print(f'  • {out_dir / "metrics_by_horizon.csv"}')

    # ---------- ГРАФИКИ ----------
    plot_results(res, per_h, df, model, X_all, target, horizon, out_dir)

    # ---------- Демонстрационный прогноз с последней даты ----------
    print(f'\nПрогноз на {horizon} дней от {df.index[-1].date()}:')
    print(model.forecast(df, X=X_all).to_string(index=False))


if __name__ == '__main__':
    main()