"""Five trends with additive calendar-month effects of zero annual sum."""
from dataclasses import dataclass
import numpy as np
from common import ModelFitError, evaluate, get_trend, jacobian, search_b

def month_contrasts(month):
    month = np.asarray(month, dtype=int)
    return np.column_stack([(month == m).astype(float)-(month == 1) for m in range(2, 13)])

def check_month(month):
    month = np.asarray(month, dtype=int)
    wrong = (month < 1) | (month > 12)
    if np.any(wrong):
        raise ValueError(f'month должен быть от 1 до 12, получено: {np.unique(month[wrong])}')
    return month

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
        month = check_month(month)
        return evaluate(self.kind, self.coefficients, u, x)+self.month_effects[np.asarray(month, dtype=int)-1]


def fit_monthly(kind, u, x, month, y):
    trend = get_trend(kind)
    u, x, y = [np.asarray(v, dtype=float) for v in (u, x, y)]
    month = check_month(month)
    if np.any(x <= 0):
        raise ValueError(f'x должен быть > 0, минимальное значение: {x.min()}')
    d = month_contrasts(month)
    if trend.linear:
        matrix = np.column_stack([trend.design(u, x), d])
        parameters = np.linalg.lstsq(matrix, y, rcond=None)[0]
        nbase = matrix.shape[1]-11
        coefficients, gamma = parameters[:nbase], parameters[nbase:]
    else:
        z = np.log(x) if trend.use_log else x
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

        b = search_b(profile)
        coefficients,gamma=profile(b,parameters=True)
        nbase=2
    effects=np.r_[-gamma.sum(),gamma]
    fitted=evaluate(kind,coefficients,u,x)+effects[month-1]
    residual=y-fitted
    j=np.column_stack([jacobian(kind,coefficients,u,x),d])
    p=j.shape[1]
    if np.linalg.matrix_rank(j)!=p:
        raise ModelFitError(f'Сезонная модель {kind!r} не идентифицируема: матрица вырождена')
    s=float(np.sqrt(residual@residual/(len(y)-p)))
    covariance_reduced=s*s*np.linalg.inv(j.T@j)
    transform=np.zeros((nbase+12,p));transform[:nbase,:nbase]=np.eye(nbase)
    transform[nbase,nbase:]=-1;transform[nbase+1:,nbase:]=np.eye(11)
    covariance=transform@covariance_reduced@transform.T
    r2=float(1-residual@residual/np.sum((y-y.mean())**2))
    return SeasonalFit(kind,coefficients,effects,covariance,s,len(y),p,r2)
