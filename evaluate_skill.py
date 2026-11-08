"""Comparable out-of-sample skill for five basic and five monthly trend models."""
import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import posixpath
import zipfile
import numpy as np
import pandas as pd
from scipy.stats import t as student_t
from common import fit_model,evaluate,jacobian
from seasonal_models import fit_monthly

KINDS=['polynomial2','polynomial3','power','logarithmic','exponential']
NAMES=['Полином 2','Полином 3','Степенная','Логарифмическая','Экспоненциальная']


def score(actual,predicted,initial):
    actual,predicted,initial=[np.asarray(a,dtype=float) for a in (actual,predicted,initial)]
    errors=actual-predicted
    delta=actual-initial
    sigma=float(np.std(delta,ddof=1))
    mse=float(np.mean(errors**2))
    denominator=float(np.sum((actual-actual.mean())**2))
    return dict(n=len(actual),mae=float(np.mean(np.abs(errors))),rmse=float(np.sqrt(mse)),
                nse=1-float(np.sum(errors**2))/denominator if denominator>0 else None,
                sigma_delta=sigma,ratio=float(np.sqrt(mse)/sigma) if sigma>0 else None,
                p=float(np.mean(np.abs(errors)<=0.674*sigma)),
                allowable_error=0.674*sigma)


def read_original_coefficients(path):
    if not path.exists():
        return {}
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    result={}
    with zipfile.ZipFile(path) as z:
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        for sh in ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets',ns):
            if sh.attrib['name'] not in NAMES:
                continue
            target=rels[sh.attrib['{'+ns['r']+'}id']]
            target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            xml=ET.fromstring(z.read(target));cells={c.attrib['r']:c for c in xml.findall('.//s:sheetData/s:row/s:c',ns)}
            kind=KINDS[NAMES.index(sh.attrib['name'])]
            p=3 if kind=='polynomial2' else 4 if kind=='polynomial3' else 2
            result[kind]=np.array([float(cells['B'+str(4+i)].findtext('s:v',namespaces=ns)) for i in range(p)])
    return result


def assess(input_path,output,original_book=None):
    output.mkdir(parents=True,exist_ok=True)
    raw=pd.read_csv(input_path,parse_dates=['date']).sort_values('date').reset_index(drop=True)
    if raw.date.duplicated().any() or not (raw.date.diff().dropna()==pd.Timedelta(days=1)).all():
        raise ValueError('Expected unique, consecutive daily dates')
    if not raw.level_khabarovsk_filled.isin([0,1]).all():
        raise ValueError('Invalid filled flag')
    origin,last=raw.date.iloc[0],raw.date.iloc[-1]
    test_dates=pd.date_range(last-pd.Timedelta(days=364),last,freq='D')
    indexed=raw.set_index('date')
    source=raw[raw.date.ge(test_dates[0]-pd.Timedelta(days=30))]
    observed=raw[raw.level_khabarovsk_filled.eq(0)]
    origin_serial=int((origin-pd.Timestamp('1899-12-30')).days)

    def coordinates(dates,cutoff):
        dt=pd.DatetimeIndex(dates)
        t=(dt-origin).days.to_numpy(dtype=float)+1
        return 2*(t-1)/(cutoff-origin).days-1,t/1000.0,dt.month.to_numpy()

    def train(cutoff,kind,seasonal):
        frame=observed[observed.date.le(cutoff)]
        u,x,m=coordinates(frame.date,cutoff)
        y=frame.level_khabarovsk.to_numpy()
        if seasonal:
            f=fit_monthly(kind,u,x,m,y)
            return dict(coefficients=f.coefficients,month_effects=f.month_effects,covariance=f.covariance,
                        s=f.s,n=f.n,p=f.p,r2=f.r_squared)
        f=fit_model(kind,u,x,y)
        residual=y-f.predict(u,x)
        return dict(coefficients=f.coefficients,month_effects=np.zeros(12),covariance=f.s**2*f.inverse_information,
                    s=f.s,n=f.n,p=len(f.coefficients),r2=float(1-residual@residual/np.sum((y-y.mean())**2)))

    def predict(f,kind,dates,cutoff):
        u,x,m=coordinates(dates,cutoff)
        return evaluate(kind,f['coefficients'],u,x)+f['month_effects'][m-1]

    # Model version changes on the first day of each month. Each version uses only
    # observations through the preceding month-end, strictly before every issue date.
    cutoffs=sorted({(d-pd.Timedelta(days=h)).replace(day=1)-pd.Timedelta(days=1)
                    for d in test_dates for h in range(1,31)})
    folds={family:{kind:{} for kind in KINDS} for family in ['baseline','monthly']}
    for cutoff in cutoffs:
        for kind in KINDS:
            for family in ['baseline','monthly']:
                folds[family][kind][cutoff.strftime('%Y-%m-%d')]=train(cutoff,kind,family=='monthly')
        print('Fitted through',cutoff.strftime('%Y-%m-%d'),flush=True)
    original=read_original_coefficients(original_book) if original_book else {}
    full={family:{} for family in ['baseline','monthly']}
    forecasts=[]
    future=pd.date_range(last+pd.Timedelta(days=1),periods=90,freq='D')
    for family in full:
        for kind in KINDS:
            f=train(last,kind,family=='monthly')
            if family=='baseline' and kind in original:
                f['coefficients']=original[kind]
                u,x,m=coordinates(observed.date,last);y=observed.level_khabarovsk.to_numpy()
                residual=y-evaluate(kind,f['coefficients'],u,x)
                f['s']=float(np.sqrt(residual@residual/(f['n']-f['p'])))
                j=jacobian(kind,f['coefficients'],u,x)
                f['covariance']=f['s']**2*np.linalg.inv(j.T@j)
                f['r2']=float(1-residual@residual/np.sum((y-y.mean())**2))
            full[family][kind]=f
            point=predict(f,kind,future,last)
            u,x,m=coordinates(future,last)
            g=jacobian(kind,f['coefficients'],u,x)
            nbase=len(f['coefficients'])
            if family=='monthly':
                expanded=np.zeros((len(future),nbase+12));expanded[:,:nbase]=g
                expanded[np.arange(len(future)),nbase+m-1]=1;g=expanded
            variance=np.einsum('ij,jk,ik->i',g,f['covariance'],g)
            if np.min(variance)<-1e-7:raise RuntimeError('Negative prediction variance')
            se=np.sqrt(f['s']**2+np.maximum(variance,0));se_mean=np.sqrt(np.maximum(variance,0))
            critical=float(student_t.ppf(.975,f['n']-f['p']));f['critical_95']=critical
            for i,date in enumerate(future):
                forecasts.append(dict(family=family,model=kind,date=date.strftime('%Y-%m-%d'),horizon_day=i+1,
                                      forecast=float(point[i]),standard_error_prediction=float(se[i]),
                                      standard_error_mean=float(se_mean[i]),lower_95=float(point[i]-critical*se[i]),
                                      upper_95=float(point[i]+critical*se[i]),unit='cm'))
    metrics=[];validation=[]
    for h in range(1,31):
        initial_dates=test_dates-pd.Timedelta(days=h)
        cut_by_date=pd.DatetimeIndex([d.replace(day=1)-pd.Timedelta(days=1) for d in initial_dates])
        actual=indexed.loc[test_dates,'level_khabarovsk'].to_numpy()
        initial=indexed.loc[initial_dates,'level_khabarovsk'].to_numpy()
        eligible=(indexed.loc[test_dates,'level_khabarovsk_filled'].to_numpy()==0)&(indexed.loc[initial_dates,'level_khabarovsk_filled'].to_numpy()==0)
        for family in full:
            for kind in KINDS:
                prediction=np.empty(len(test_dates))
                for cutoff in cutoffs:
                    mask=cut_by_date==cutoff
                    if not np.any(mask):continue
                    assert np.all(initial_dates[mask]>cutoff)
                    f=folds[family][kind][cutoff.strftime('%Y-%m-%d')]
                    prediction[mask]=predict(f,kind,test_dates[mask],cutoff)
                metrics.append(dict(family=family,model=kind,horizon=h,**score(actual[eligible],prediction[eligible],initial[eligible])))
                for i,date in enumerate(test_dates):
                    validation.append(dict(family=family,model=kind,horizon=h,date=date.strftime('%Y-%m-%d'),
                                           issue_date=initial_dates[i].strftime('%Y-%m-%d'),
                                           training_cutoff=cut_by_date[i].strftime('%Y-%m-%d'),actual=float(actual[i]),
                                           initial=float(initial[i]),prediction=float(prediction[i]),eligible=int(eligible[i])))
    metric_frame=pd.DataFrame(metrics);metric_frame['p_percent']=100*metric_frame['p'];metric_frame.to_csv(output/'metrics_by_lead.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(validation).to_csv(output/'rolling_validation.csv',index=False,encoding='utf-8-sig')
    for family in full:
        pd.DataFrame([r for r in forecasts if r['family']==family and r['horizon_day']<=30]).to_csv(output/(family+'_daily_forecast.csv'),index=False,encoding='utf-8-sig')

    def encode(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,np.generic):return v.item()
        raise TypeError(type(v))
    payload=dict(metadata=dict(source=input_path.name,sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),origin=origin.strftime('%Y-%m-%d'),origin_serial=origin_serial,last=last.strftime('%Y-%m-%d'),
                               span=(last-origin).days,test_start=test_dates[0].strftime('%Y-%m-%d'),test_end=last.strftime('%Y-%m-%d'),
                               evaluation_days=365,forecast_horizon=30,forecast_max=90,unit='cm',unit_source='user',
                               refit='monthly, trained through previous month-end before issue date',
                               sigma_delta='sample standard deviation of observed H(target)-H(issue), eligible verification pairs, each lead separately'),
                 full=full,folds=folds,cutoffs=[c.strftime('%Y-%m-%d') for c in cutoffs],
                 source_rows=[[d.strftime('%Y-%m-%d'),float(y),int(f)] for d,y,f in source[['date','level_khabarovsk','level_khabarovsk_filled']].itertuples(index=False,name=None)],
                 test_dates=[d.strftime('%Y-%m-%d') for d in test_dates],metrics=metrics,forecasts=forecasts)
    (output/'assessment.json').write_text(json.dumps(payload,default=encode,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(metric_frame[metric_frame.horizon.eq(1)].to_string(index=False))
    return payload


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    root=Path(__file__).parent
    parser.add_argument('--input',type=Path,default=root/'data/amur_khabarovsk_clean_2002-2026.csv')
    parser.add_argument('--output',type=Path,default=root/'results')
    parser.add_argument('--original-book',type=Path,default=None)
    args=parser.parse_args();assess(args.input,args.output,args.original_book)
