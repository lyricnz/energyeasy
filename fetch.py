import datetime
import logging
import os

import matplotlib.pyplot as plt
import pandas as pd
import requests

MAIN_URL = 'https://energyeasy.ue.com.au/electricityView/index'
LOGIN_FORM = 'https://energyeasy.ue.com.au/login_security_check'

# categories within consumptionData
DATA_SETS = ['consumptionData', 'costData']
CATEGORIES = ['generation', 'offpeak', 'peak', 'shoulder']


def fetch_all_data(username, password) -> list[dict]:
    """Fetch all the historical data for energy consumption and return as a list of dicts"""
    # get main page, start session
    s = requests.session()
    s.get(MAIN_URL)

    # login
    s.post(LOGIN_FORM, data={
        'login_email': username,
        'login_password': password,
        'submit': 'Login'
    })

    # get multiple months of data. technically could step=2 and use selectedPeriod + comparisonPeriod
    results = []
    for offset in range(100):
        data = s.get(f'https://energyeasy.ue.com.au/electricityView/period/month/{offset}').json()
        results.append(data)

        if not data['isPreviousPeriodDataAvailable']:
            break

    return results


def make_dataframe(period: dict) -> pd.DataFrame:
    """given an energyeasy datastructure for a given period, return a dataframe for the data within"""
    if period['periodType'] != 'month':
        raise ValueError('Only support month data for now')

    # build the index for time-series
    period_start = datetime.datetime.strptime(period['subtitle'], '%B %Y')
    index = [period_start + datetime.timedelta(days=n) for n in range(len(period['consumptionData']['peak']))]

    # build the data series for DATA_SETS * CATEGORIES
    data_series = {}
    for dataset in DATA_SETS:
        for cat in CATEGORIES:
            cat_values = [d['total'] for d in period[dataset][cat]]
            data_series[f'{dataset}_{cat}'] = pd.Series(cat_values, index)

    # return the dataframe
    return pd.DataFrame(data_series)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.INFO)

    all_results = fetch_all_data(os.environ['USERNAME'], os.environ['PASSWORD'])

    # convert data to a dataframe, sort, and save
    dataframes = [make_dataframe(data['selectedPeriod']) for data in all_results]
    df = pd.concat(dataframes)
    df.sort_index(inplace=True)
    df.to_pickle('energyeasy.pkl')

    # save data to excel
    df.to_excel('energyeasy.xlsx')

    # display a graph
    df.plot(y='costData_peak', kind='line', title='Power Cost per Day').set_ylabel('$')
    plt.show()
