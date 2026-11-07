"""H(x) = a*x**b; nonlinear LS in original water-level units."""
from common import fit_model


def fit(u, x, y):
    return fit_model('power', u, x, y)
