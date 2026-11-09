"""Time-only least-squares models; water levels stay in the source scale."""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize_scalar, least_squares

class BaseModel:
    def design(self, u, x): raise NotImplementedError
    def evaluate(self, coefficients, u, x): raise NotImplementedError
    def jacobian(self, coefficients, u, x): raise NotImplementedError

class PolynomialModel(BaseModel):
    def __init__(self, degree):
        self.degree = degree
    def design(self, u, x):
        return np.column_stack([np.asarray(u) ** k for k in range(self.degree + 1)])
    def evaluate(self, coefficients, u, x):
        return self.design(u, x) @ coefficients
    def jacobian(self, coefficients, u, x):
        return self.design(u, x)

class LogarithmicModel(BaseModel):
    def design(self, u, x):
        return np.column_stack([np.ones_like(x), np.log(x)])
    def evaluate(self, coefficients, u, x):
        return self.design(u, x) @ coefficients
    def jacobian(self, coefficients, u, x):
        return self.design(u, x)

class PowerModel(BaseModel):
    def evaluate(self, coefficients, u, x):
        a, b = coefficients
        return a * np.power(x, b)
    def jacobian(self, coefficients, u, x):
        a, b = coefficients
        z = np.log(x)
        phi = np.exp(b * z)
        return np.column_stack([phi, a * phi * z])

class ExponentialModel(BaseModel):
    def evaluate(self, coefficients, u, x):
        a, b = coefficients
        return a * np.exp(b * x)
    def jacobian(self, coefficients, u, x):
        a, b = coefficients
        phi = np.exp(b * x)
        return np.column_stack([phi, a * phi * x])

def get_model(kind):
    if kind == 'polynomial2': return PolynomialModel(2)
    if kind == 'polynomial3': return PolynomialModel(3)
    if kind == 'logarithmic': return LogarithmicModel()
    if kind == 'power': return PowerModel()
    if kind == 'exponential': return ExponentialModel()
    raise ValueError(f"Unknown model kind: {kind}")

@dataclass(frozen=True)
class Fit:
    model: BaseModel
    coefficients: np.ndarray
    n: int
    s: float
    inverse_information: np.ndarray

    def forecast(self, u, x):
        prediction = self.model.evaluate(self.coefficients, u, x)
        g = self.jacobian(self.coefficients, u, x)
        leverage = np.einsum('ij,jk,ik->i', g, self.inverse_information, g)
        se_mean = self.s * np.sqrt(np.maximum(leverage, 0))
        se_prediction = self.s * np.sqrt(1 + np.maximum(leverage, 0))
        return prediction, se_prediction, se_mean


def fit_model(kind, u, x, y):
    """OLS for linear-in-parameters forms; profiled nonlinear LS otherwise."""
    u, x, y = (np.asarray(v, dtype=float) for v in (u, x, y))
    if np.any(x <= 0) or not np.all(np.isfinite(y)):
        raise ValueError('x must be positive and y finite')
    model = get_model(kind)
    if kind in ('polynomial2', 'polynomial3', 'logarithmic'):
        coefficients = np.linalg.lstsq(model.design(u, x), y, rcond=None)[0]
    else:
        z = np.log(x) if kind == 'power' else x

        def profile(b, return_a=False):
            log_phi = b * z
            offset = float(np.max(log_phi))
            phi_scaled = np.exp(log_phi - offset)
            a_scaled = float(y @ phi_scaled / (phi_scaled @ phi_scaled))
            residual = y - a_scaled * phi_scaled
            return a_scaled * np.exp(-offset) if return_a else float(residual @ residual)

        # Explicit search bounds, checked below. Scaling prevents overflow.
        grid = np.linspace(-10.0, 10.0, 401)
        losses = np.array([profile(b) for b in grid])
        candidates = []
        for i in range(1, len(grid) - 1):
            if losses[i] <= losses[i-1] and losses[i] <= losses[i+1]:
                result = minimize_scalar(profile, bounds=(grid[i-1], grid[i+1]),
                                         method='bounded', options={'xatol': 1e-13})
                candidates.append((result.fun, result.x))
        if not candidates:
            raise RuntimeError('No interior minimum in b in [-10, 10]')
        _, b = min(candidates)
        if abs(b) > 9.99 or profile(b) >= min(losses[0], losses[-1]):
            raise RuntimeError('Expand nonlinear search bounds before using this fit')
        coefficients = np.array([profile(b, return_a=True), b])
        refined = least_squares(
            lambda c: model.evaluate(c, u, x) - y, coefficients,
            jac=lambda c: model.jacobian(c, u, x),
            bounds=([-np.inf, -10], [np.inf, 10]), x_scale='jac',
            ftol=1e-12, xtol=1e-12, gtol=1e-10, max_nfev=5000,
        )
        if refined.success and np.sum(refined.fun ** 2) <= profile(b) * (1 + 1e-12):
            coefficients = refined.x
    g = model.jacobian(coefficients, u, x)
    if np.linalg.matrix_rank(g) != len(coefficients):
        raise RuntimeError('Rank-deficient parameter information matrix')
    inverse = np.linalg.inv(g.T @ g)
    residual = y - model.evaluate(coefficients, u, x)
    s = float(np.sqrt((residual @ residual) / (len(y) - len(coefficients))))
    return Fit(model, coefficients, len(y), s, inverse)

# функции для обратной совместимости со старыми скриптами
def evaluate(kind, coefficients, u, x):
    return get_model(kind).evaluate(coefficients, u, x)

def jacobian(kind, coefficients, u, x):
    return get_model(kind).jacobian(coefficients, u, x)

def design(kind, u, x):
    return get_model(kind).design(u, x)