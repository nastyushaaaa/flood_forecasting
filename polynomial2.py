"""H(u) = a0 + a1*u + a2*u**2."""
from common import fit_model


def fit(u, x, y):
    return fit_model('polynomial2', u, x, y)
