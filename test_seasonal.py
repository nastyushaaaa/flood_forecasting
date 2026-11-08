import unittest
import numpy as np
import pandas as pd
from seasonal_models import fit_monthly
from common import evaluate
from evaluate_skill import score


class SeasonalChecks(unittest.TestCase):
    def test_metrics_known_example(self):
        r=score([1,3],[1,1],[0,0])
        self.assertAlmostEqual(r['mae'],1)
        self.assertAlmostEqual(r['rmse'],np.sqrt(2))
        self.assertAlmostEqual(r['nse'],-1)
        self.assertAlmostEqual(r['ratio'],1)
        self.assertAlmostEqual(r['p'],.5)

    def test_monthly_functions_recovery(self):
        dates=pd.date_range('2000-01-01',periods=1096)
        month=dates.month.to_numpy();u=np.linspace(-1,1,len(dates));x=np.linspace(.1,3,len(dates))
        effects=np.arange(12,dtype=float)-5.5
        cases={'polynomial2':[40,5,3],'polynomial3':[40,5,3,2],'logarithmic':[30,7],
               'power':[30,.8],'exponential':[30,.15]}
        for kind,coefficients in cases.items():
            with self.subTest(kind=kind):
                y=evaluate(kind,np.array(coefficients),u,x)+effects[month-1]
                f=fit_monthly(kind,u,x,month,y)
                np.testing.assert_allclose(f.predict(u,x,month),y,atol=1e-5)
                self.assertAlmostEqual(f.month_effects.sum(),0,places=9)
                np.testing.assert_allclose(f.coefficients,coefficients,atol=1e-5)


if __name__=='__main__':unittest.main()
