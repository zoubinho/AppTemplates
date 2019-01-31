import pandas as pd
import numpy as np
import logging
from collections import OrderedDict
import functools

import bql

_logger = logging.getLogger('PortfolioMonitorDemo')

class PortfolioMonitorModel(object):
    """Model for requesting data and calculate price impacts."""

    # BQL Service instance shared across FactorModel instances.
    __shared_bq__ = None    # Definition of label for data retrieval from BQL
    
    def __init__(self, universe_type, universe_value, asset, fields, bq=None):
        """Initialize the model.
        Parameters
        ----------
        universe_type: str
            universe type [Index, Portfolio, List of ticker]
        universe_value: str 
            universe value that user has input
        bq: bql.Service
            Instance of bql Service. It would lazily create BQL service instance only when requesting for data.
            If an instance is provided through bq parameter, this instance would be used.

        """
        self._univ_type = universe_type
        self._univ_value = universe_value
        self._asset = asset
        self._user_fields = fields
        self._bq = bq
        config_file = pd.read_excel('config.xlsx', sheetname='controls')
        self._float_fields_only = config_file[config_file.value_type == 'numerical'].field_name.tolist()
        
    def _init_bql(self):
        """Loads self._bq from class-level shared BQL instance if no instance is available yet.
        Class-level shared BQL instance would be initialized if needed.
        """
        if self._bq is None:
            if PortfolioMonitorModel.__shared_bq__ is None:
                _logger.info('Launching BQL service...')
                PortfolioMonitorModel.__shared_bq__ = bql.Service()

            self._bq = PortfolioMonitorModel.__shared_bq__
            
        
    def run(self):
        """Run the model"""
        # Initiate BQL service lazily.
        self._init_bql()
        
        # Define universe based on user inputs
        univ = self._build_univ()
        
        # build factors items for this model (returns a dict)
        factor_items = self._build_factors(user_selection=self._user_fields)

        # get the top factors scores
        _logger.info('Fetching market data...')
        raw_data = self._get_data(univ, factor_items)
        self._options_list = list(factor_items.keys())

        self._data = raw_data
        _logger.info('Cleaning data...')

        # load the excel file for mapping data (nicer display)
        try:
            country_map = pd.read_excel('mapping.xlsx', sheetname='Countries', index_col='Code')
            self._data['Country'] = self._data.apply(lambda x: country_map.loc[x['Country']]['Name'], axis=1)

            rating_map = pd.read_excel('mapping.xlsx', sheetname='Ratings', index_col='Bloomberg')
            self._data['intRating'] = self._data.apply(lambda x:rating_map.loc[x['Bloomberg']]['Score'], axis=1)
            #self._data['Credit type'] = self._data.apply(lambda x:rating_map.loc[x['Bloomberg']]['Credit type'], axis=1)
            #self._data['Credit description'] = self._data.apply(lambda x:rating_map.loc[x['Bloomberg']]['Credit description'], axis=1)
            _logger.info('Mapping table loaded')
        except:
            _logger.warn('Mapping table not loaded. Going on')

        
    
    def get_model_data(self):
        return self._data

    def get_query_string(self):
        return self._debug_query.to_string()

    def get_fields_list(self):
        return self._options_list

    def set_data_as_matrix(self, x, y):
        '''
        Summary: returns a table in 2-dim with data transformed and 
        aggregated by bucket_type and by maturity.
        Inputs:
            - data (pd.DataFrame): initial dataframe. This df needs to 
            possess 2 mandatory columns: `x` (in numerical value) and 
            the `y` (int or str) eg. if Sector is mentioned, it needs to
            have it). Name is also mandatory.
            - x (int): type of numerical value used to bucket the data
            - y (str): type of bucket used to aggregated data on 
                        (eg. Sector, or Country).
        '''
            
        # function that generates the buckets of maturity
        def _get_bin_hedges(d_):
            # get the bins 
            bins_ = pd.qcut(d_, 10, precision=6, retbins=True)[1:][0].round(1)
            bins_ = np.insert(bins_, 0, 0)

            bins = []
            for i, b in enumerate(bins_):
                if i < len(bins_) - 1:
                    bins.append((bins_[i],bins_[i+1]))

            return bins
        
        try:
            # retrieve unique list of items for y-axis
            bucket_list = sorted(self._data[y].unique())

            # retrieve the bins used in x-axis
            bins_ = _get_bin_hedges(self._data[x])
            
            # create the final dataframe
            df_matrix_x_y = pd.DataFrame(index=bucket_list,columns=bins_)
            
            # parse each bucket and assign each bins data
            for s in bucket_list:
                section_data = self._data[self._data[y] == s]
                for b in bins_:
                    selected_subset = section_data[x].between(b[0],b[1])
                    df_matrix_x_y[b].loc[s] = section_data[selected_subset][y].count()
            
            df_matrix_x_y.replace(0, np.nan, inplace=True)

            return df_matrix_x_y
            
        except Exception as e:
            _logger.error('Error in clustering data for {} (missing data points) - {}'.format(y, e))
            return pd.DataFrame(index=bucket_list)

    
    def _build_univ(self):
        """
        Construct the universe based on a list of exchange codes.
        Returns the bql univ item object. 
        """
        if self._univ_type == 'Portfolio' or self._univ_type == 'Index':
            if self._univ_value:
                return self._bq.univ.members(self._univ_value)
            else:
                _logger.error('Error in selecting {} value... Check inputs again'.format(self._univ_type))


        elif self._univ_type == 'List':
            if self._univ_value:
                # Drop any line containing garbage character
                tickers = [c.strip() for c in self._univ_value.splitlines() if c.isprintable()]
                # bug-fix DRQS 113960117: need to input only 8-char tickers
                tickers = ['{} {}'.format(t.split(' ')[0][:-1], t.split(' ')[1]) for t in tickers if len(t)>1]
                return self._bq.univ.list(tickers)
            else:
                _logger.error('Error in selecting {} values... Check inputs again'.format(self._univ_type))

        else:
            _logger.error('What has been requested has not been implemented')


    def _build_factors(self, user_selection):
        """
        Construct the factors for a portfolio monitor
        """
        if self._asset == 'Fixed Income':
            factors_list = OrderedDict([
                ('Name'           , self._bq.data.name()),
                ('Country'        , self._bq.data.cntry_of_risk()),  
                ('Industry'       , self._bq.data.bics_level_1_sector_name()),
                ('Payment rank'   , self._bq.data.payment_rank()),
                ('Maturity'       , self._bq.data.maturity()),
                ('Year to mat'    , self._bq.func.round(self._bq.data.maturity() - self._bq.func.today(), 6) / 365.25 ),
                ('Bloomberg'      , self._bq.data.bb_composite()),
                ('Yield to Worst' , self._bq.data.yield_(yield_type='YTW', fill='prev')),
                ('Z-Spread'       , self._bq.data.spread(spread_type='Z',fill='prev')),
                ('Discount Margin', self._bq.data.disc_margin()),
                ('Z-Score'        , self._bq.data.spread(spread_type='Z',fill='prev',start='-6m',end='0d').zscore().last()),
            ])

        else:
            factors_list = dict()
            _logger.error('Not implemented.')

        try:
            final_factors_list = OrderedDict([(k,v) for k,v in factors_list.items() if k in user_selection])
        except:
            final_factors_list = factors_list

        return final_factors_list
    

    def _get_data(self, universe, bql_factors):
        """
        Retrieve data model based on the universe and the BQL items
        Inputs:
        - universe (bqlItem object): bql universe item object to request
        factor data on. Eg. bq.univ.members() or bq.univ.equitiesuniv() or list()
        - bql_factors (dict): bql data item object to request
        data on. eg. bq.data.pe_ratio() or bq.data.px_last().std()
        """
        # request data to BQL
        try:
            self._debug_query = bql.Request(universe, bql_factors)
            r = self._bq.execute(bql.Request(universe, bql_factors))

            # store the whole dataset in data
            data = pd.DataFrame()
            # capture each dataset from the response
            # by using the keys of the bql_factors
            for k in bql_factors.keys():
                temp = r.get(k).df()[k]
                
                # transform the series type to float when applicable
                if k in set(self._float_fields_only):
                    temp.dropna().astype('float64')

                data = pd.concat([data, temp], join='outer', axis=1)


        except Exception as e:
            _logger.error('Error while fetching data ({})'.format(e))
            data = pd.DataFrame()

        return data
    
    def _get_history(self, ids, field_name, history_period='-1y'):
        # get the field in bql_item
        bql_item = self._build_factors(user_selection=field_name)
        try:
            r = self._bq.execute(bql.Request(ids, bql_item, with_params={'start':history_period}))

            # store the whole dataset in data
            data = r.single().df()

            # pivot the data for better display
            data = data.reset_index().pivot_table(index='DATE', columns='ID', values=field_name)


        except Exception as e:
            _logger.error('Error while fetching timeseries ({})'.format(e))
            data = pd.DataFrame()

        return data

   