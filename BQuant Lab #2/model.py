import pandas as pd
import logging

import bql

_logger = logging.getLogger('HeatmapApp')

class DataModel(object):
    """Model for requesting data and calculate price impacts."""

    # BQL Service instance shared across FactorModel instances.
    __shared_bq__ = None
    
    def __init__(self, query=None, asset_class=None, bq=None):
        """Initialize the model.
        Parameters
        ----------
        bq: bql.Service
            Instance of bql Service. It would lazily create BQL service instance only when requesting for data.
            If an instance is provided through bq parameter, this instance would be used.

        """
        self._query = query
        self._asset_class = asset_class
        self._bq = bq
        
    def _init_bql(self):
        """Loads self._bq from class-level shared BQL instance if no instance is available yet.
        Class-level shared BQL instance would be initialized if needed.
        """
        if self._bq is None:
            if DataModel.__shared_bq__ is None:
                _logger.info('Launching BQL service...')
                DataModel.__shared_bq__ = bql.Service()

            self._bq = DataModel.__shared_bq__
            
        
    def run(self):
        """Run the model"""

        # Initiate BQL service.
        self._init_bql()

        # fetch data from queries
        _logger.info('Fetching {} market data...'.format(self._asset_class))
        
        # download raw data
        raw_data = self._get_data(self._query)
        
        # render the data in `self.data`
        self.data = self._yield_raw_df(raw_data, self._asset_class)
            
    
    def _get_data(self, query):
        """
        Retrieve data model based on the universe and the BQL items
        Inputs:
        - query (str): BQL query string to be requested.
        """
        try:
            # add mode=cached for queries involvind asset class universe screening
            query = '{} with(mode=cached)'.format(query)

            # request the query string
            r = self._bq.execute(query)

            # store the whole dataset in data
            data = self._combine_dfs(r)

        except Exception as e:
            _logger.error('Error while fetching data ({})'.format(e))
            data = pd.DataFrame()

        return data


    def _combine_dfs(self, response):
        """
        Concatenate in a DataFrame all the response (per column item) from BQL
        Inputs:
        - response (DataFrame): dataframe that contains the Bloomberg data
        retrieved via BQL without some dropped items
        """
        data = []
        drop_items = ['REVISION_DATE','AS_OF_DATE','PERIOD_END_DATE','CURRENCY','Partial Errors']
        for r in response:
            df = r.df().drop(drop_items, axis='columns', errors='ignore')
            data.append(df)
        return pd.concat(data, axis=1).reset_index()
        
        
    def _yield_raw_df(self, df, asset_class):
        """
        Retrieve data model based on the universe and the BQL items
        Inputs:
        - df (DataFrame): dataframe that contains the Bloomberg data
        retrieved via BQL.
        - asset_class (str): asset class string working as a switch 
        to handle the data manipulation after retrieval.
        """
        if asset_class == 'Fixed Income':
            # trim the index and build additional columns used for pivoting tables
            col_mapping = {'YEAR(ANNOUNCE_DATE())':'Year',
                           'MONTH(ANNOUNCE_DATE())':'Month',
                           '#amt':'Amount Out',
                           'CNTRY_OF_RISK()':'Country'}
            df.rename(columns=col_mapping, inplace=True)

            # create the Year, Month and Announce Date columns:
            df['Year'] = df['Year'].astype('str').apply(lambda x: x.split('.')[0])
            df['Month'] = df['Month'].astype('str').apply(lambda x: '{:02d}'.format(int(x.split('.')[0])))
            df['Announce Date'] = df.apply(lambda x: '{}-{:02d}'.format(x['Year'],int(x['Month'])), axis=1)


        elif asset_class == 'Equity':
            # rename the columns to a more readable content
            col_mapping = {'COUNTRY_FULL_NAME()':'Country',
                           'GICS_SECTOR_NAME()':'Sector',
                           '#avg_rel_ret':'1m return'}
            df.rename(columns=col_mapping, inplace=True)

        else:
            _logger.error('Not Implemented')

        # mask NullGroup
        maskNullGroup = df.apply(lambda x: 'NullGroup' not in x.ID.split(':'), axis=1)
        df = df[maskNullGroup]
        df = df[df['Country'] != 'NA']

        return df
    
    
    def build_2dim_dataset(self, df, x='Month', y='Year', v='Amount Out', calc_type='sum'):
        '''
        Summary: returns a table in 2-dim with data transformed and 
        aggregated by x and by y.
        Inputs:
            - df (DataFrame): dataframe that contains the BQL data cleaned 
            - x (str): columns on which to pivot the table to represent the x-axis
            - y (str): columns on which to pivot the table to represent the y-axis
            - calc_type (str): sum or median can be referred to aggregate the data
        '''

        # create the final dataframe
        output = df.pivot_table(index=y, columns=x, values=v, aggfunc=calc_type)

        return output
    