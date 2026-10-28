"""Five trends with additive calendar-month effects of zero annual sum."""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize_scalar
from common import design, evaluate, jacobian


def month_contrasts(month):
    month = np.asarray(month, dtype=int)
    return np.column_stack([(month == m).astype(float)-(month == 1) for m in range(2, 13)])


@dataclass
class SeasonalFit:
    kind: str
    coefficients: np.ndarray
    month_effects: np.ndarray
    covariance: np.ndarray
    s: float
    n: int
    p: int
    r_squared: float

    def predict(self, u, x, month):
        return evaluate(self.kind, self.coefficients, u, x)+self.month_effects[np.asarray(month, dtype=int)-1]


def fit_monthly(kind, u, x, month, y):
    u, x, y = [np.asarray(v, dtype=float) for v in (u, x, y)]
    month = np.asarray(month, dtype=int)
    d = month_contrasts(month)
    if kind in ('polynomial2', 'polynomial3', 'logarithmic'):
        matrix = np.column_stack([design(kind, u, x), d])
        parameters = np.linalg.lstsq(matrix, y, rcond=None)[0]
        nbase = matrix.shape[1]-11
        coefficients, gamma = parameters[:nbase], parameters[nbase:]
    else:
        z = np.log(x) if kind == 'power' else x
        inv_dd = np.linalg.inv(d.T@d)
        dy = d.T@y
        y_projected_sq = float(y@y-dy@inv_dd@dy)

        def profile(b, parameters=False):
            log_phi = b*z
            offset = float(log_phi.max())
            phi = np.exp(log_phi-offset)
            sums = np.bincount(month, weights=phi, minlength=13)
            dp = sums[2:13]-sums[1]
            denominator = float(phi@phi-dp@inv_dd@dp)
            numerator = float(phi@y-dp@inv_dd@dy)
            if denominator <= 0:
                return np.inf
            a_scaled = numerator/denominator
            if parameters:
                return np.array([a_scaled*np.exp(-offset), b]), inv_dd@(dy-a_scaled*dp)
            return y_projected_sq-numerator*numerator/denominator

        grid = np.linspace(-10, 10, 401)
        losses = np.array([profile(b) for b in grid])
        candidates = []
        for i in range(1, len(grid)-1):
            if losses[i] <= losses[i-1] and losses[i] <= losses[i+1]:
                result = minimize_scalar(profile, bounds=(grid[i-1],grid[i+1]), method='bounded', options={'xatol':1e-12})
                candidates.append((result.fun,result.x))
        if not candidates:
            raise RuntimeError('No interior nonlinear monthly minimum')
        loss, b = min(candidates)
        if abs(b)>9.99 or loss>=min(losses[0],losses[-1]):
            raise RuntimeError('Nonlinear monthly search reached boundary')
        coefficients,gamma=profile(b,parameters=True)
        nbase=2
    effects=np.r_[-gamma.sum(),gamma]
    fitted=evaluate(kind,coefficients,u,x)+effects[month-1]
    residual=y-fitted
    j=np.column_stack([jacobian(kind,coefficients,u,x),d])
    p=j.shape[1]
    if np.linalg.matrix_rank(j)!=p:
        raise RuntimeError('Monthly model is not identified')
    s=float(np.sqrt(residual@residual/(len(y)-p)))
    covariance_reduced=s*s*np.linalg.inv(j.T@j)
    transform=np.zeros((nbase+12,p));transform[:nbase,:nbase]=np.eye(nbase)
    transform[nbase,nbase:]=-1;transform[nbase+1:,nbase:]=np.eye(11)
    covariance=transform@covariance_reduced@transform.T
    r2=float(1-residual@residual/np.sum((y-y.mean())**2))
    return SeasonalFit(kind,coefficients,effects,covariance,s,len(y),p,r2)
