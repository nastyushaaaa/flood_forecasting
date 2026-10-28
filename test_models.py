"""Numerical checks independent of the historical river-level fit."""
import unittest
import numpy as np
from common import fit_model, evaluate


class NumericalModelsTest(unittest.TestCase):
    def test_recovers_known_functions(self):
        x = np.linspace(0.1, 8.0, 300)
        u = np.linspace(-1, 1, 300)
        cases = {'polynomial2': [10, -20, 3], 'polynomial3': [-8, 20, 2, -4],
                 'power': [12, 0.7], 'logarithmic': [-5, 8], 'exponential': [10, 0.12]}
        for kind, coefficients in cases.items():
            with self.subTest(model=kind):
                y = evaluate(kind, np.array(coefficients), u, x)
                fit = fit_model(kind, u, x, y)
                np.testing.assert_allclose(fit.coefficients, coefficients, rtol=1e-6, atol=1e-6)

    def test_residual_and_prediction_standard_errors(self):
        x = np.linspace(0.1, 8, 300)
        u = np.linspace(-1, 1, 300)
        y = 10 + 2*u - u**2 + 0.4*np.sin(np.arange(300))
        fit = fit_model('polynomial2', u, x, y)
        residual = y-fit.predict(u,x)
        self.assertAlmostEqual(fit.s, np.sqrt(np.sum(residual**2)/(len(y)-3)), places=12)
        _, se_pred, se_mean = fit.forecast(np.array([1.1]), np.array([8.5]))
        self.assertAlmostEqual(se_pred[0]**2, fit.s**2+se_mean[0]**2, places=12)
        self.assertGreater(se_pred[0], se_mean[0])

    def test_negative_levels_not_dropped(self):
        x = np.linspace(0.1, 8, 100)
        u = np.linspace(-1, 1, 100)
        for kind in ['power', 'exponential']:
            coefficients = np.array([-3, 0.2])
            y = evaluate(kind, coefficients, u, x)
            fit = fit_model(kind, u, x, y)
            self.assertEqual(fit.n, 100)
            np.testing.assert_allclose(fit.coefficients, coefficients, rtol=1e-6, atol=1e-6)


if __name__ == '__main__':
    unittest.main()
