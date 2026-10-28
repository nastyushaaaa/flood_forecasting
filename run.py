"""Reproduce all five fits and daily CSV forecasts. No weather predictors."""
import argparse
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
import pandas as pd
import scipy
from scipy.stats import t as student_t
import polynomial2, polynomial3, power, logarithmic, exponential

MODELS = [polynomial2, polynomial3, power, logarithmic, exponential]


def run(csv_path, output, horizon=30, test_days=30):
    output.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(csv_path, parse_dates=['date']).sort_values('date').reset_index(drop=True)
    columns = ['date', 'level_khabarovsk', 'level_khabarovsk_filled']
    if not set(columns).issubset(raw.columns):
        raise ValueError('Missing required source columns')
    if raw.date.duplicated().any() or raw[columns].isna().any().any():
        raise ValueError('Duplicate dates or missing model inputs')
    if not raw.level_khabarovsk_filled.isin([0, 1]).all():
        raise ValueError('Filled flag must be 0 or 1')
    if not (raw.date.diff().dropna() == pd.Timedelta(days=1)).all():
        raise ValueError('Source must contain one row for every calendar day')
    origin, last = raw.date.iloc[0], raw.date.iloc[-1]
    span = (last - origin).days
    cutoff = last - pd.Timedelta(days=test_days)
    observed = raw[raw.level_khabarovsk_filled.eq(0)].copy()
    train = observed[observed.date.le(cutoff)]
    test = observed[observed.date.gt(cutoff)]
    if len(train) <= 4 or len(test) < 2:
        raise ValueError('Insufficient training/test observations')

    def time_values(dates, scale_span=span):
        day = (pd.DatetimeIndex(dates) - origin).days.to_numpy(dtype=float) + 1
        return 2 * (day - 1) / scale_span - 1, day / 1000.0

    u, x = time_values(observed.date)
    # Training-only scaling avoids using the held-out period in calibration.
    train_span = (cutoff - origin).days
    ut, xt = time_values(train.date, train_span)
    uv, xv = time_values(test.date, train_span)
    future_dates = pd.date_range(last + pd.Timedelta(days=1), periods=horizon, freq='D')
    uf, xf = time_values(future_dates)
    baseline = float(train.level_khabarovsk.iloc[-1])
    forecasts, validation, metrics, fits = [], [], [], {}
    y = observed.level_khabarovsk.to_numpy()
    ytrain = train.level_khabarovsk.to_numpy()
    ytest = test.level_khabarovsk.to_numpy()
    for module in MODELS:
        kind = module.__name__
        full = module.fit(u, x, y)
        held = module.fit(ut, xt, ytrain)
        point, se, se_mean = full.forecast(uf, xf)
        critical = float(student_t.ppf(0.975, full.n - len(full.coefficients)))
        prediction_test = held.predict(uv, xv)
        errors = ytest - prediction_test
        fit_residual = y - full.predict(u, x)
        residual_by_date = pd.Series(fit_residual, index=observed.date)
        consecutive = pd.DataFrame({'e': residual_by_date, 'lag': residual_by_date.shift(freq='D')}).dropna()
        lag1 = float(consecutive.e.corr(consecutive.lag))
        metric = dict(model=kind, n=full.n, parameters=len(full.coefficients),
                      residual_standard_error=full.s,
                      test_mae=float(np.mean(np.abs(errors))),
                      test_rmse=float(np.sqrt(np.mean(errors ** 2))),
                      test_bias=float(np.mean(errors)), residual_lag1_correlation=lag1,
                      r_squared=float(1-np.sum(fit_residual**2)/np.sum((y-y.mean())**2)))
        metrics.append(metric)
        for i, date in enumerate(future_dates):
            forecasts.append(dict(date=date.strftime('%Y-%m-%d'), model=kind, horizon_day=i+1,
                                  forecast=float(point[i]), standard_error_prediction=float(se[i]),
                                  standard_error_mean=float(se_mean[i]),
                                  lower_95=float(point[i]-critical*se[i]),
                                  upper_95=float(point[i]+critical*se[i]),
                                  as_of_date=last.strftime('%Y-%m-%d'), unit='source_csv_unit'))
        for date, actual, pred in zip(test.date, ytest, prediction_test):
            validation.append(dict(date=date.strftime('%Y-%m-%d'), model=kind,
                                   actual=float(actual), prediction=float(pred), error=float(actual-pred)))
        fits[kind] = dict(coefficients=full.coefficients.tolist(), n=full.n, s=full.s,
                          inverse_information=full.inverse_information.tolist(), critical_95=critical,
                          test_coefficients=held.coefficients.tolist(), test_s=held.s,
                          test_n=held.n, test_span=train_span)
    baseline_error = ytest - baseline
    baseline_metrics = dict(last_training_level=baseline,
                            mae=float(np.mean(np.abs(baseline_error))),
                            rmse=float(np.sqrt(np.mean(baseline_error**2))))
    metadata = dict(source=csv_path.name, sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                    origin=origin.strftime('%Y-%m-%d'), last=last.strftime('%Y-%m-%d'),
                    cutoff=cutoff.strftime('%Y-%m-%d'), span=span, horizon=horizon,
                    test_days=test_days, raw_rows=len(raw), excluded_filled=int(raw.level_khabarovsk_filled.sum()),
                    test_n=len(test), baseline=baseline_metrics,
                    versions=dict(python=platform.python_version(), numpy=np.__version__,
                                  pandas=pd.__version__, scipy=scipy.__version__))
    pd.DataFrame(forecasts).to_csv(output/'daily_forecast.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(metrics).to_csv(output/'model_metrics.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(validation).to_csv(output/'validation.csv', index=False, encoding='utf-8-sig')
    payload = dict(metadata=metadata, fits=fits, metrics=metrics,
                   source_rows=[[d.strftime('%Y-%m-%d'), float(h), int(f)]
                                for d,h,f in raw[columns].itertuples(index=False, name=None)],
                   forecasts=forecasts, validation=validation)
    (output/'calibration.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(pd.DataFrame(metrics).to_string(index=False))
    print('Baseline:', baseline_metrics)
    print('Source last date:', metadata['last'], 'forecast days:', horizon)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=Path(__file__).parent/'data/amur_khabarovsk_clean_2002-2026.csv')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent/'results')
    parser.add_argument('--horizon', type=int, default=30)
    parser.add_argument('--test-days', type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.horizon <= 365 or not 7 <= args.test_days <= 365:
        parser.error('horizon must be 1..365 and test-days 7..365')
    run(args.input, args.output, args.horizon, args.test_days)
