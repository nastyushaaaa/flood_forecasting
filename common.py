"""Time-only least-squares models; water levels stay in the source scale."""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize_scalar, least_squares
from typing import Callable

B_MIN, B_MAX, GRID_POINTS = -10.0, 10.0, 401
B_XATOL = 1e-13

class ModelFitError(RuntimeError):
    """Численный метод не нашёл решения для этих данных"""
def _polynomial2_design(u, x):
    u = np.asarray(u)
    return np.column_stack([u ** 0, u, u ** 2])


def _polynomial3_design(u, x):
    u = np.asarray(u)
    return np.column_stack([u ** 0, u, u ** 2, u ** 3])


def _logarithmic_design(u, x):
    return np.column_stack([np.ones_like(x), np.log(x)])


def _power_evaluate(coefficients, u, x):
    a, b = coefficients
    return a * np.power(x, b)


def _exponential_evaluate(coefficients, u, x):
    a, b = coefficients
    return a * np.exp(b * x)

@dataclass(frozen=True)
class Trend:
    name: str
    linear: bool # True: линейный МНК, False: нелинейный
    design: Callable = None # линейные: (u, x) - матрица плана
    formula: Callable = None # нелинейные: (coefficients, u, x) - H
    use_log: bool = False # нелинейные: z=log(x) - степенная или z=x

    def evaluate(self, coefficients, u, x):
        if self.linear:
            return self.design(u, x) @ coefficients
        return self.formula(coefficients, u, x)

    def jacobian(self, coefficients, u, x):
        if self.linear:
            return self.design(u, x)
        a, b = coefficients
        z = np.log(x) if self.use_log else x
        phi = np.exp(b * z)
        return np.column_stack([phi, a * phi * z])

TRENDS = {t.name: t for t in (
    Trend('polynomial2', linear=True, design=_polynomial2_design),
    Trend('polynomial3', linear=True, design=_polynomial3_design),
    Trend('logarithmic', linear=True, design=_logarithmic_design),
    Trend('power', linear=False, formula=_power_evaluate, use_log=True),
    Trend('exponential', linear=False, formula=_exponential_evaluate),
)}


def get_trend(kind):
    try:
        return TRENDS[kind]
    except KeyError:
        raise ValueError(f'Неизвестный вид модели {kind!r}, доступны: {sorted(TRENDS)}') from None

@dataclass
class Fit:
    kind: str
    coefficients: np.ndarray
    n: int
    s: float
    inverse_information: np.ndarray

    def predict(self, u, x):
        return evaluate(self.kind, self.coefficients, u, x)

    def forecast(self, u, x):
        prediction = self.predict(u, x)
        g = jacobian(self.kind, self.coefficients, u, x)
        leverage = np.einsum('ij,jk,ik->i', g, self.inverse_information, g)
        se_mean = self.s * np.sqrt(np.maximum(leverage, 0))
        se_prediction = self.s * np.sqrt(1 + np.maximum(leverage, 0))
        return prediction, se_prediction, se_mean


def design(kind, u, x):
    trend = get_trend(kind)
    if not trend.linear:
        raise ValueError(f'У нелинейной модели {kind!r} нет матрицы плана')
    return trend.design (u, x)


def evaluate(kind, coefficients, u, x):
    return get_trend(kind).evaluate(coefficients, u, x)


def jacobian(kind, coefficients, u, x):
    return get_trend(kind).jacobian(coefficients, u, x)

def search_b(loss):
    grid = np.linspace(B_MIN, B_MAX, GRID_POINTS)
    losses = np.array([loss(b) for b in grid])
    candidates = []
    for i in range(1, len(grid) - 1):
        is_local_min = losses[i] <= losses[i - 1] and losses[i] <= losses[i + 1]
        if np.isfinite(losses[i]) and is_local_min:
            result = minimize_scalar(loss, bounds=(grid[i - 1], grid[i + 1]),
                                     method='bounded', options={'xatol': B_XATOL})
            candidates.append((result.fun, result.x))
    if not candidates:
        raise ModelFitError(f'Нет внутреннего минимума по b в [{B_MIN}, {B_MAX}]')
    best_loss, b = min(candidates)
    if abs(b) > B_MAX - 0.01 or best_loss >= min(losses[0], losses[-1]):
        raise ModelFitError(f'Минимум по b = {b:.4f} на границе поиска [{B_MIN}, {B_MAX}], расширьте границы')
    return b

def fit_model(kind, u, x, y):
    """OLS for linear-in-parameters forms; profiled nonlinear LS otherwise."""
    trend = get_trend(kind)
    u, x, y = (np.asarray(v, dtype=float) for v in (u, x, y))
    if np.any(x <= 0):
        raise ValueError(f'x должен быть > 0, минимальное значение: {x.min()}')
    if not np.all(np.isfinite(y)):
        raise ValueError(f'y содержит {np.sum(~np.isfinite(y))} значений NaN/inf')
    if trend.linear:
        coefficients = np.linalg.lstsq(design(kind, u, x), y, rcond=None)[0]
    else:
        z = np.log(x) if trend.use_log else x

        def profile(b, return_a=False):
            log_phi = b * z
            offset = float(np.max(log_phi))
            phi_scaled = np.exp(log_phi - offset)
            a_scaled = float(y @ phi_scaled / (phi_scaled @ phi_scaled))
            residual = y - a_scaled * phi_scaled
            return a_scaled * np.exp(-offset) if return_a else float(residual @ residual)

        b = search_b(profile)
        coefficients = np.array([profile(b, return_a=True), b])
        refined = least_squares(
            lambda c: evaluate(kind, c, u, x) - y, coefficients,
            jac=lambda c: jacobian(kind, c, u, x),
            bounds=([-np.inf, B_MIN], [np.inf, B_MAX]), x_scale='jac',
            ftol=1e-12, xtol=1e-12, gtol=1e-10, max_nfev=5000,
        )
        if refined.success and np.sum(refined.fun ** 2) <= profile(b) * (1 + 1e-12):
            coefficients = refined.x
    g = jacobian(kind, coefficients, u, x)
    if np.linalg.matrix_rank(g) != len(coefficients):
        raise ModelFitError(f'Матрица информации модели {kind!r} вырождена')
    inverse = np.linalg.inv(g.T @ g)
    residual = y - evaluate(kind, coefficients, u, x)
    s = float(np.sqrt((residual @ residual) / (len(y) - len(coefficients))))
    return Fit(kind, coefficients, len(y), s, inverse)
