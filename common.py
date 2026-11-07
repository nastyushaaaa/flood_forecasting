"""Time-only least-squares models; water levels stay in the source scale."""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize_scalar, least_squares


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
    if kind in ('polynomial2', 'polynomial3'):
        degree = 2 if kind == 'polynomial2' else 3
        return np.column_stack([np.asarray(u) ** k for k in range(degree + 1)])
    if kind == 'logarithmic':
        return np.column_stack([np.ones_like(x), np.log(x)])
    raise ValueError(kind)


def evaluate(kind, coefficients, u, x):
    if kind in ('polynomial2', 'polynomial3', 'logarithmic'):
        return design(kind, u, x) @ coefficients
    a, b = coefficients
    if kind == 'power':
        return a * np.power(x, b)
    if kind == 'exponential':
        return a * np.exp(b * x)
    raise ValueError(kind)


def jacobian(kind, coefficients, u, x):
    if kind in ('polynomial2', 'polynomial3', 'logarithmic'):
        return design(kind, u, x)
    a, b = coefficients
    z = np.log(x) if kind == 'power' else x
    phi = np.exp(b * z)
    return np.column_stack([phi, a * phi * z])


def fit_model(kind, u, x, y):
    """OLS for linear-in-parameters forms; profiled nonlinear LS otherwise."""
    u, x, y = (np.asarray(v, dtype=float) for v in (u, x, y))
    if np.any(x <= 0) or not np.all(np.isfinite(y)):
        raise ValueError('x must be positive and y finite')
    if kind in ('polynomial2', 'polynomial3', 'logarithmic'):
        coefficients = np.linalg.lstsq(design(kind, u, x), y, rcond=None)[0]
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
            lambda c: evaluate(kind, c, u, x) - y, coefficients,
            jac=lambda c: jacobian(kind, c, u, x),
            bounds=([-np.inf, -10], [np.inf, 10]), x_scale='jac',
            ftol=1e-12, xtol=1e-12, gtol=1e-10, max_nfev=5000,
        )
        if refined.success and np.sum(refined.fun ** 2) <= profile(b) * (1 + 1e-12):
            coefficients = refined.x
    g = jacobian(kind, coefficients, u, x)
    if np.linalg.matrix_rank(g) != len(coefficients):
        raise RuntimeError('Rank-deficient parameter information matrix')
    inverse = np.linalg.inv(g.T @ g)
    residual = y - evaluate(kind, coefficients, u, x)
    s = float(np.sqrt((residual @ residual) / (len(y) - len(coefficients))))
    return Fit(kind, coefficients, len(y), s, inverse)
