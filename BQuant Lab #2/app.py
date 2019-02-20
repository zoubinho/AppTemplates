import numpy as np
import ipywidgets
import logging

from bqplot import OrdinalScale, ColorScale, GridHeatMap, Tooltip, Axis, ColorAxis, Figure
from bqwidgets import TickerAutoComplete
from model import DataModel
from logwidget import LogWidget, LogWidgetAdapter, LogWidgetHandler

# Widget to display the logs
_log_widget = LogWidget(
    layout={'border': '1px solid dimgray', 'margin': '10px'})

# Handler to sink the logs to the widget
_handler = LogWidgetHandler(_log_widget)
_formatter = logging.Formatter('%(asctime)s - %(message)s', '%H:%M:%S')
_handler.setFormatter(_formatter)

# Define app logger and add widget handler
_logger = logging.getLogger('HeatmapApp')
_logger.addHandler(_handler)
_logger.setLevel(logging.DEBUG)


class HeatmapApp(object):
    def __init__(self):
        self.widgets = dict()

    def show(self):
        """Construct and return the user interface.
        This is the entry method of the app.
        Returns : Instance of ipywidgets
        """
        ui = self._build_ui()
        _logger.info('Select your universe and click on Run to start.')

        return ui

    
    def _build_ui(self):
        """Build main frame of the user interface."""
        # universe picker definition
        self.widgets['universe_select'] = TickerAutoComplete(description='Select universe:', 
                                                             yellow_keys=['Index'], value='BWORLD Index',
                                                             style={'description_width':'initial'})


        # period dropdown selector
        self.widgets['period_select'] = ipywidgets.Dropdown(description='Period:', 
                                                            #options=['2010-01-01','2014-01-01'])  # for fixed income request
                                                            options=['1m','3m','6m','12m']) # for equity request

        # App title definition
        self.widgets['app_title'] = ipywidgets.HTML('<h1>Heatmap</h1>')

        # Button definition
        self.button_run = ipywidgets.Button(description='Run', button_style='info', icon='fa-play')
        self.button_run.on_click(self._refresh_data)

        # creation of the control box with the header
        self.widgets['header'] = ipywidgets.VBox([self.widgets['app_title'],
                                                  ipywidgets.HBox([self.widgets['universe_select'], 
                                                                   self.widgets['period_select'],
                                                                   self.button_run]),
                                                 ])

        # definition of the box holding the data output (heatmap)
        self.widgets['main_box'] = ipywidgets.Box(layout={'min_height':'100px'})
        
         # Main UI Box
        main_box = ipywidgets.VBox([self.widgets['header'], self.widgets['main_box']], layout={'overflow_x':'hidden'})
        ui = ipywidgets.VBox([main_box, _log_widget.get_widget()])

        return ui


    def _refresh_data(self, *args, **kwargs):
        """Called upon button Run is clicked."""
        # disable the selectable objects while running
        self.button_run.disabled = True

        # clear any content in the output
        self.widgets['main_box'].children=[]

        # Retrieve user input to calibrate the Model
        # inputs for model: universe, period, asset
        universe = self.widgets['universe_select'].value
        date = self.widgets['period_select'].value
        asset_class = 'Equity'

        # query = '''
        #             let(#amt=sum(group(amt_outstanding(currency='USD'),[year(announce_date()), month(announce_date()),cntry_of_risk()]))/1000000;) 
        #             get(#amt) 
        #             for( filter(members('{idx}'), announce_date() >= '{date}') ) 
        #         '''.format(idx=universe, date=date)

        query = '''
                    let(#ret1m = (product(dropna(1.0+day_to_day_total_return(start=-{date},end=0d)))-1)*100;
                        #ret1m_idx = value(#ret1m,['{idx}']);
                        #rel_ret1m = #ret1m - #ret1m_idx;
                        #avg_rel_ret = avg(group(#rel_ret1m,[country_full_name(),gics_sector_name()]));)
                    get(#avg_rel_ret)
                    for( members('{idx}'))
                '''.format(idx=universe, date=date)

        # for better display in logger
        _logger.info('Loading the data Model... ({})'.format(asset_class))
        self._model = DataModel(query, asset_class=asset_class)
        self._model.run()
        
        _logger.info('Refreshing data and chart...')
        # calling method that fetch the arranged data and display it
        self._build_matrix()

        _logger.info('Done.')
        
        # re-enable the selectable objects
        self.button_run.disabled = False
        



# --------  end main UI              ---------- 
# --------  start graphic (heatmap)  ----------   
    def on_matrix_hover(self, caller, event):
        try:
            x = event.get('data', {})['row']
            y = event.get('data', {})['column']
            c = self.data.loc[x][y]

            if np.isnan(c):
                self.matrix_tooltip.children = [
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">No data for </span><span>{}</span></p>'.format(x))
                ]
            else:
                self.matrix_tooltip.children = [
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">{} </span><span>{}</span></p>'.format(self.data.index.name, x)),
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">{} </span><span>{}</span></p>'.format(self.data.columns.name, y)),
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">{} </span><span>{:.1f}%</span></p>'.format('Return', c))
                ]

        except Exception as e:
            self.matrix_tooltip.children = [ipywidgets.HTML('<p style="font-weight:italic; color:dimgrey;">No data fetched.</p>')]


    def _build_matrix(self):

        # retrieve the data to be displayed
        #data = self._model.build_2dim_dataset(self._model.data, x='Month', y='Year', v='Amount Out', calc_type='sum')
        self.data = self._model.build_2dim_dataset(self._model.data, x='Sector', y='Country', v='1m return', calc_type='median')

        # get the heatmap object 
        self.widgets['heatmap'] = self._build_heatmap(self.data)
        
        # set the heatmap widgets as the child of the main-box element
        self.widgets['main_box'].children = [self.widgets['heatmap']]

        # Adjust the height of the box hosting the heatmap (~15px/name)
        self.widgets['main_box'].layout.height = '{}px'.format(len(self.data)*15) if len(self.data)*15 > 400 else '400px'


    def _build_heatmap(self, df):
        # create the matrix 
        x_sc, y_sc, col_sc = OrdinalScale(), OrdinalScale(reverse=True), ColorScale(scheme='RdYlGr')
        
        # define a tooltip
        self.matrix_tooltip = ipywidgets.VBox(layout={'width':'180px','height':'100px'})

        # building the marks for inflow and outflow
        grid_map = GridHeatMap(row=df.index, column=df.columns, color=df, 
                               scales={'column': x_sc, 'row': y_sc, 'color': col_sc},
                               tooltip=self.matrix_tooltip, interactions={'hover':'tooltip'},
                               stroke='transparent', null_color='transparent',
                               selected_style={'opacity': 1.0}, unselected_style={'opacity': 0.4})

        ax_x, ax_y = Axis(scale=x_sc, grid_lines='none', label=df.columns.name, tick_rotate=-25, tick_style={'text-anchor': 'end'}), \
                     Axis(scale=y_sc, grid_lines='none', label=df.index.name, orientation='vertical')

        # generating the figures inflow and outflow
        grid_ui = Figure(marks=[grid_map], axes=[ax_x, ax_y], padding_y=0.0, 
                         title='{} distribution'.format(self.widgets['universe_select'].value),
                         fig_margin={'bottom': 90, 'left': 150, 'right': 10, 'top': 60},
                         layout={'width':'100%', 'height':'100%'})

        # set the callback for the hovering effect
        grid_map.on_hover(self.on_matrix_hover)

        # define the output object to get displayed
        return ipywidgets.VBox([grid_ui], 
                                layout={'width':'99%', 'min_height':'100%', 'overflow_x':'hidden'})


    
# --------  end graphic (heatmap)  ----------  

######################################################################################
