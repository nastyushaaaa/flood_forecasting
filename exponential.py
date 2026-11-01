"""H(x) = a*exp(b*x); nonlinear LS in original water-level units."""
from common import fit_model


def fit(u, x, y):
    return fit_model('exponential', u, x, y)
