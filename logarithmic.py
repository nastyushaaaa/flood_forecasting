"""H(x) = a + b*ln(x)."""
from common import fit_model


def fit(u, x, y):
    return fit_model('logarithmic', u, x, y)
