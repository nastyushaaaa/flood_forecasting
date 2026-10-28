"""H(u) = a0 + a1*u + a2*u**2 + a3*u**3."""
from common import fit_model


def fit(u, x, y):
    return fit_model('polynomial3', u, x, y)
