"""Quadratic time trend with twelve zero-sum calendar-month effects."""
from seasonal_models import fit_monthly


def fit(u,x,month,y):
    return fit_monthly('polynomial2',u,x,month,y)
