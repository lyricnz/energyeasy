import datetime
import itertools
import logging
import os

import matplotlib.pyplot as plt
import pandas as pd
import requests

MAIN_URL = 'https://energyeasy.ue.com.au/electricityView/index'
LOGIN_FORM = 'https://energyeasy.ue.com.au/login_security_check'
DATA_URL_FORMAT = 'https://energyeasy.ue.com.au/electricityView/period/%s/%d'  # period, offset

# categories within consumptionData
DATA_SETS = ['consumptionData', 'costData']
CATEGORIES = ['generation', 'offpeak', 'peak', 'shoulder']


class EnergyEasy:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.s = None

    def _login(self):
        """Login to the API and save the session in self.s"""
        self.s = requests.session()
        self.s.get(MAIN_URL)
        self.s.post(LOGIN_FORM, data={
            'login_email': self.username,
            'login_password': self.password,
            'submit': 'Login'
        })

    def get_data(self, period_type, offset) -> dict:
        """Return the data straight from the API for the given period-type and offset"""
        if self.s is None:
            self._login()
        return self.s.get(DATA_URL_FORMAT % (period_type, offset)).json()

    def get_data_as_df(self, period_type, offset) -> (pd.DataFrame, bool):
        """Fetch data from the API, and return as a Dataframe, along with boolean isPreviousPeriodDataAvailable"""
        data = self.get_data(period_type, offset)
        return self.data_to_dataframe(data['selectedPeriod']), data['isPreviousPeriodDataAvailable']

    @staticmethod
    def data_to_dataframe(period: dict) -> pd.DataFrame:
        """return a pd.Dataframe for the given period"""
        # determine what the period-start date and interval is so we can build the data index
        period_type = period['periodType']
        if period_type == 'day':
            period_start = datetime.datetime.strptime(period['subtitle'], '%A %d %B %Y')  # Sunday 24 July 2022
            period_delta = datetime.timedelta(hours=1)  # 24 hours of data
        elif period_type == 'week':
            period_start = datetime.datetime.strptime(period['subtitle'], '%A %d %B %Y')  # Sunday 24 July 2022
            period_delta = datetime.timedelta(days=1)  # 7 days of data
        elif period_type == 'month':
            period_start = datetime.datetime.strptime(period['subtitle'], '%B %Y')  # July 2022
            period_delta = datetime.timedelta(days=1)  # 28-31 days of data
        elif period_type == 'season':
            # subtitle is insufficient (contains 1-2 years only); need to use first category (month)
            date_str = f"{period['categories'][0]} {period['subtitle'].split('-')[0]}"
            period_start = datetime.datetime.strptime(date_str, '%b %Y')  # DEC 2019
            period_delta = pd.DateOffset(months=1)  # 3 months of data
        elif period_type == 'year':
            period_start = datetime.datetime.strptime(period['subtitle'], '%Y')  # 2022
            period_delta = pd.DateOffset(months=1)  # 12 months of data
        else:
            raise ValueError('Unsupported periodType %s' % period['periodType'])

        # build the index for the data series
        index = [period_start + period_delta * n for n in range(len(period['consumptionData']['peak']))]

        # build the data series for DATA_SETS * CATEGORIES
        data_series = {}
        for dataset in DATA_SETS:
            for cat in CATEGORIES:
                cat_values = [d['total'] for d in period[dataset][cat]]
                data_series[f'{dataset}_{cat}'] = pd.Series(cat_values, index)

        return pd.DataFrame(data_series)


def update_data(username, password, df_filename) -> pd.DataFrame:
    """Fetch and add all newer daily data to an existing pd.Dataframe and return"""
    if os.path.exists(df_filename):
        df = pd.read_pickle(df_filename)
        last_data = df.last_valid_index().to_pydatetime()
    else:
        df = pd.DataFrame()
        last_data = None

    ee = EnergyEasy(username, password)

    all_data = [df]
    for offset in itertools.count():
        period_df, has_more_data = ee.get_data_as_df('day', offset)
        all_data.append(period_df)

        first_datetime = period_df.first_valid_index().to_pydatetime()
        if last_data is not None and first_datetime < last_data:
            break  # run into the existing data
        if not has_more_data:
            break  # run out of data

    new_df: pd.DataFrame = pd.concat(all_data)
    new_df = new_df[~new_df.index.duplicated(keep='last')]
    new_df.sort_index(inplace=True)
    new_df.to_pickle(df_filename)
    return df


def show_chart(df: pd.DataFrame):
    """display a chart of the last few days"""
    df['total_cost'] = df['costData_peak'] + df['costData_shoulder'] + df['costData_offpeak']

    fig, ax = plt.subplots(figsize=(20, 5))
    df.plot(y='total_cost', kind='line', title='Power Cost per X', ax=ax).set_ylabel('cost per X ($)')
    # plt.plot(df['costData_peak'].rolling(7).mean(), label='Weekly average')
    # plt.plot(df['costData_peak'].rolling(30).mean(), label='Monthly average')
    plt.legend(frameon=False)
    not_zero = df.query('costData_peak != 0')
    # set axis limits more tightly than default
    # ax.set_xlim(not_zero.index[0], not_zero.index[-1])
    ax.set_xlim(datetime.datetime.now() - datetime.timedelta(days=10), not_zero.index[-1])
    ax.set_ylim(0)

    plt.show()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('matplotlib.font_manager').setLevel(logging.INFO)
    logging.getLogger("requests.packages.urllib3.connectionpool").setLevel(logging.INFO)

    ee_user = os.environ['USERNAME']
    ee_password = os.environ['PASSWORD']

    all_df = update_data(ee_user, ee_password, 'energyeasy_day.pkl')
    all_df.to_excel('energyeasy.xlsx')
    show_chart(all_df)
