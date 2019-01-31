import pandas as pd
import numpy as np
import bqviz
import ipywidgets
import logging
import bqport

from bqplot import LinearScale, OrdinalScale, ColorScale, DateScale, GridHeatMap, Scatter, Tooltip, Lines, Bars, Axis, ColorAxis, Figure
from bqplot.interacts import BrushSelector, IndexSelector

from bqwidgets import DataGrid, TickerAutoComplete
from IPython.display import display
from model import PortfolioMonitorModel
from logwidget import LogWidget, LogWidgetAdapter, LogWidgetHandler
from collections import OrderedDict
import datetime


# Widget to display the logs
_log_widget = LogWidget(
    layout={'border': '1px solid dimgray', 'margin': '10px'})

# Handler to sink the logs to the widget
_handler = LogWidgetHandler(_log_widget)
_formatter = logging.Formatter('%(asctime)s - %(message)s', '%H:%M:%S')
_handler.setFormatter(_formatter)

# Define app logger and add widget handler
_logger = logging.getLogger('PortfolioMonitorDemo')
_logger.addHandler(_handler)
_logger.setLevel(logging.DEBUG)


class PortfolioMonitorDemo(object):
    def __init__(self):
        self._load_default_settings()

    def _load_default_settings(self):
        config_file = pd.read_excel('config.xlsx', sheetname='controls')

        columns = ['field_name','control_name','value_type','default']
        # build one dataframe per tab config
        self.app_config       = config_file[config_file.tab == 'app'][columns]
        self.matrix_config    = config_file[config_file.tab == 'matrix'][columns]
        self.datatable_config = config_file[config_file.tab == 'datatable'][columns]
        self.model_config     = config_file[config_file.tab == 'model'][columns]

        self._activate_custom_list = self.app_config[self.app_config.control_name == 'custom-list']['default'].values[0]
        self._activate_settings_tab = self.app_config[self.app_config.control_name == 'settings-tab']['default'].values[0]

        _logger.info('Default settings loaded.')


    def show(self):
        """Construct and return the user interface.
        This is the entry method of the app.
        Returns : Instance of ipywidgets
        """
        ui = self._build_ui()
        _logger.info('Select your universe and click on Run to start.')

        self._main_tab.selected_index = 0

        return ui


    def _run(self, *args, **kwargs):
        """Called upon button Run is clicked."""
        # disable the selectable objects while running
        self._button_run.disabled = True

        # clear any content in the tabs
        self._tab1_box.children = []
        self._tab2_box.children = []

        # Retrieve user input to calibrate the Model
        # inputs for model: universe_type, universe_value, asset
        universe_type = self.univ_picker._dropdown_type.value
        universe_value = self.univ_picker._dropdown_port.value if universe_type == 'Portfolio' \
                            else self.univ_picker._ac_index.value if universe_type == 'Index'  \
                            else self.univ_picker._txt_custom.value if universe_type == 'List' else None
        # loading the current config (fields only)
        fields_selected = self._read_from_settings()
        unique_fields_selected = list(set(fields_selected))

        # load and run the Model with the user inputs
        if not universe_value:
            _logger.error('Universe seems undefined. Please retry.')
            self._button_run.disabled = False
            return 0
        # for better display in logger
        display_value_in_logger = '{} bonds'.format(len(universe_value.split('\n'))) if universe_type == 'List' else universe_value
        _logger.info('Loading the data Model... ({}: {})'.format(universe_type, display_value_in_logger))
        self._model = PortfolioMonitorModel(universe_type, universe_value, 'Fixed Income', unique_fields_selected)
        self._model.run()
        
        # checking if some necessary fields are retrieved
        # before proceeding to the display of tables
        mandatory_fields = self.matrix_tab_scatter_x
        if not self._model.get_model_data().columns.isin(mandatory_fields).any():
            _logger.warn('Some fields are missing and need to be defined first.')
        else:
            _logger.info('Brushing up tables and charts (1)...')
            self._build_matrix()
            _logger.info('Brushing up tables and charts (2)...')
            self._build_tables()
            _logger.info('Brushing up tables and charts (3)...')
            self._build_model_portfolio()
            _logger.info('Job done.')
        
        # re-enable the selectable objects
        self._button_run.disabled = False
        self._main_tab.selected_index = 0
        
    
    def _build_ui(self):
        """Build main frame of the user interface."""
        side_layout = ipywidgets.Layout(min_width='200px', margin='10px', overflow_x='hidden')
        
        # label for App name and dropdown
        label_dropdown = ipywidgets.HTML('<h1>Credit Portfolio Monitor</h1><br/>Select a universe:')
        
        # Define the universe UI
        self.univ_picker = self.UniversePicker(layout={'overflow_x':'hidden'})

        # Button Run
        self._button_run = ipywidgets.Button(
            description='Run', button_style='info', icon='fa-play', layout=side_layout)
        self._button_run.on_click(self._run)
        
        # Tabs for figures and tables
        self._main_tab = ipywidgets.Tab(layout={'margin': '10px'})
        main_layout = ipywidgets.Layout(flex_flow='row wrap', min_width='800px')
        # define first tab (matrix aggregated result)
        self._tab1_box = ipywidgets.Box(layout=main_layout)
        # define second tab (table data)
        self._tab2_box = ipywidgets.Box(layout=main_layout)
        # define third tab (relative valuation)
        self._tab3_box = ipywidgets.Box(layout=main_layout)
        tab_children = [self._tab1_box, self._tab2_box, self._tab3_box]
        tab_titles = ['Matrix','Data table','Model Portfolio']

        if self._activate_custom_list:
            # define fourth tab (settings)
            self._tab4_box = ipywidgets.Box(layout=main_layout)
        
            # define the settings for running inclusion/exclusion list:
            self._tab4_box.children = self._custom_list_tab()

            tab_children.append(self._tab4_box)
            tab_titles.append('Custom List')

        if self._activate_settings_tab:
            # define fourth tab (settings)
            self._tab5_box = ipywidgets.Box(layout=main_layout)
        
            # define the settings for running inclusion/exclusion list:
            self._tab5_box.children = self._construct_settings_tab()

            tab_children.append(self._tab5_box)
            tab_titles.append('Settings')

        # create the tab titles dynamically
        self._main_tab.children = tab_children
        for k,v in enumerate(tab_titles):
            self._main_tab.set_title(k, v)
        
         # Main UI Box
        side_box = ipywidgets.VBox([label_dropdown, self.univ_picker.show(), 
                                    self._button_run], layout=side_layout)
        main_box = ipywidgets.HBox([side_box, self._main_tab], layout={'overflow_x':'hidden'})
        ui = ipywidgets.VBox([main_box, _log_widget.get_widget()])

        return ui


######################################################################################
######################################################################################

    def _construct_settings_tab(self):
        # settings for tab1: Matrix
        s1_label = ipywidgets.HTML('<h2>Matrix tab settings</h2>')

        # get the config from the default config file loaded
        s1_x_label = ipywidgets.HTML('<p>Horizontal option for the matrix. \
                                        Needs to be a numerical value as it will perform analytics on it.</p>')
        s1_select_x_config = self.matrix_config[self.matrix_config['control_name'] == 'drop_x']
        s1_select_x_config_default = s1_select_x_config[s1_select_x_config.default == 'y']
        self.s1_select_x = ipywidgets.SelectMultiple(options=list(s1_select_x_config.field_name),
                                                     value=list(s1_select_x_config_default.field_name))

        s1_y_label = ipywidgets.HTML('<p>Vertical option ofr the matrix. Text inputs are usually better for visuals.</p>')
        s1_select_y_config = self.matrix_config[self.matrix_config['control_name'] == 'drop_y']
        s1_select_y_config_default = s1_select_y_config[s1_select_y_config.default == 'y']
        self.s1_select_y = ipywidgets.SelectMultiple(options=list(s1_select_y_config.field_name),
                                                     value=list(s1_select_y_config_default.field_name))

        s1_output = ipywidgets.VBox([
                    s1_label,
                    ipywidgets.HBox([
                        ipywidgets.VBox([s1_x_label, self.s1_select_x], layout={'width':'320px'}),
                        ipywidgets.VBox([s1_y_label, self.s1_select_y], layout={'width':'320px'}),
                    ])
            ])

        # settings for tab2. Datatable
        s2_label = ipywidgets.HTML('<h2>Data table tab settings</h2><p>Dropdowns control the items \
                                    you want to see in the filters (top-part).</p>')

        # get the config from the default config file loaded
        s2_filter_a_config = self.datatable_config[self.datatable_config['control_name'] == 'filter_a']
        s2_filter_a_config_default = s2_filter_a_config[s2_filter_a_config.default == 'y']
        self.s2_filter_a = ipywidgets.Dropdown(options=list(s2_filter_a_config.field_name),
                                                value=list(s2_filter_a_config_default.field_name)[0],
                                                disabled=True) # just in case user sets more than one by default..

        s2_filter_b_config = self.datatable_config[self.datatable_config['control_name'] == 'filter_b']
        s2_filter_b_config_default = s2_filter_b_config[s2_filter_b_config.default == 'y']
        self.s2_filter_b = ipywidgets.Dropdown(options=list(s2_filter_b_config.field_name),
                                                value=list(s2_filter_b_config_default.field_name)[0],
                                                disabled=True) # just in case user sets more than one by default..

        s2_label_bis = ipywidgets.HTML('<p>Multi-selectors control the items that define the \
                                            scatter plot in x- and y-axis and the color scale (bottom-part).</p>')

        s2_select_x_config = self.datatable_config[self.datatable_config['control_name'] == 'drop_x']
        s2_select_x_config_default = s2_select_x_config[s2_select_x_config.default == 'y']
        self.s2_select_x = ipywidgets.SelectMultiple(options=list(s2_select_x_config.field_name),
                                                     value=list(s2_select_x_config_default.field_name),
                                                     layout={'width':'200px'})

        s2_select_y_config = self.datatable_config[self.datatable_config['control_name'] == 'drop_y']
        s2_select_y_config_default = s2_select_y_config[s2_select_y_config.default == 'y']
        self.s2_select_y = ipywidgets.SelectMultiple(options=list(s2_select_y_config.field_name),
                                                     value=list(s2_select_y_config_default.field_name),
                                                     layout={'width':'200px'})

        s2_select_z_config = self.datatable_config[self.datatable_config['control_name'] == 'drop_z']
        s2_select_z_config_default = s2_select_z_config[s2_select_z_config.default == 'y']
        self.s2_select_z = ipywidgets.SelectMultiple(options=list(s2_select_z_config.field_name),
                                                     value=list(s2_select_z_config_default.field_name),
                                                     layout={'width':'200px'})

        s2_output = ipywidgets.VBox([
                    s2_label,
                    ipywidgets.HBox([self.s2_filter_a, self.s2_filter_b]),
                    s2_label_bis,
                    ipywidgets.HBox([self.s2_select_x, self.s2_select_y, self.s2_select_z]),
            ])


        # settings for tab3. Model portfolio
        s3_label = ipywidgets.HTML('<h2>Model portfolio tab settings</h2><p>Multi-selector controls the items \
                                    you want to see in the model portfolio table (top-part).</p>')

        s3_headers_config = self.model_config[self.model_config['control_name'] == 'header']
        s3_headers_config_default = s3_headers_config[s3_headers_config.default == 'y']
        self.s3_headers = ipywidgets.SelectMultiple(options=list(s3_headers_config.field_name),
                                                     value=list(s3_headers_config_default.field_name))

        s3_label_bis = ipywidgets.HTML('<p>Multi-selectors control the items that define the x-axis and\
                                            the group-by for the bar chart (bottom-part).</p>')

        s3_select_x_config = self.model_config[self.model_config['control_name'] == 'drop_x']
        s3_select_x_config_default = s3_select_x_config[s3_select_x_config.default == 'y']
        self.s3_select_x = ipywidgets.SelectMultiple(options=list(s3_select_x_config.field_name),
                                                     value=list(s3_select_x_config_default.field_name))

        s3_output = ipywidgets.VBox([
                    s3_label,
                    self.s3_headers,
                    s3_label_bis,
                    self.s3_select_x,
            ])
        # define an accordion for  all the options
        accordion = ipywidgets.Accordion(children=[s1_output, s2_output, s3_output])
        accordion.set_title(0, 'Matrix controls')
        accordion.set_title(1, 'Data table controls')
        accordion.set_title(2, 'Model portfolio controls')

        # button to save (foe the current session only) the state of each settings
        save_btn = ipywidgets.Button(description='Save settings', button_style='info', icon='save')
        save_btn.on_click(self._save_settings)
        self.save_status = ipywidgets.HTML(value='')

        return [ipywidgets.VBox([accordion, ipywidgets.HBox([save_btn,self.save_status]) ])]


    def _save_settings(self, caller):
        s = self._read_from_settings()
        self.save_status.value = 'Saved.'


    def _read_from_settings(self):
        # for first tab
        self.matrix_tab_scatter_x = self.s1_select_x.value
        self.matrix_tab_scatter_y = self.s1_select_y.value
        # for second tab
        self.table_tab_filter_a = self.s2_filter_a.value
        self.table_tab_filter_b = self.s2_filter_b.value
        self.table_tab_select_x = self.s2_select_x.value
        self.table_tab_select_y = self.s2_select_y.value
        self.table_tab_select_z = self.s2_select_z.value
        # for third tab
        self.model_tab_header   = self.s3_headers.value
        self.model_tab_select_x = self.s3_select_x.value
        # return list of unique values
        return list(self.matrix_tab_scatter_x) + list(self.matrix_tab_scatter_y) + \
                [self.table_tab_filter_a] + [self.table_tab_filter_b] + \
                list(self.table_tab_select_x) + list(self.table_tab_select_y) + list(self.table_tab_select_z) + \
                list(self.model_tab_header) + list(self.model_tab_select_x)


######################################################################################
######################################################################################

    def _custom_list_tab(self):
        # define the label
        label_text_1 = ipywidgets.HTML('<h4>Potential securities</h4>')
        label_text_2 = ipywidgets.HTML('<h4>Exclusion list</h4>')
        label_instructions = ipywidgets.HTML('<p>This section allows user to set 2 ticker lists, one being the exclusion of the other.  \
                                              <br/>Aim is to automate some usecases where user needs to exclude a list of tickers from another universe.</p>\
                                              <p>Copy/paste or drag&drop the list of tickers into the text sections.</p>')

        # define the text area object
        self._list_1_section = ipywidgets.Textarea(placeholder='Place one ticker per line', rows=20)
        self._list_2_section = ipywidgets.Textarea(placeholder='Place one ticker per line', rows=20)
        try:
            self._list_1_section.value = self.app_config[self.app_config['field_name'] == 'list1']['default'].values[0].replace('\\n','\n')
            self._list_2_section.value = self.app_config[self.app_config['field_name'] == 'list2']['default'].values[0].replace('\\n','\n')
        except:
            pass

        # counters display
        self._count_text_1 = ipywidgets.HTML('')
        self._count_text_2 = ipywidgets.HTML('')

        # set the button up!
        button_valide_universe = ipywidgets.Button(description='Load custom universe', button_style='info')
        button_valide_universe.on_click(self._run_from_settings_tab)

        output = ipywidgets.VBox([
                    label_instructions,
                    ipywidgets.HBox([
                            ipywidgets.VBox([label_text_1, self._list_1_section, self._count_text_1]),
                            ipywidgets.VBox([label_text_2, self._list_2_section, self._count_text_2]),], layout={'margin':'30px'}),
                    button_valide_universe
            ])
        return [output]


    def _run_from_settings_tab(self, caller):
        # Drop any line containing garbage character
        tickers_1 = [c.strip() for c in self._list_1_section.value.splitlines() if c.isprintable()]
        tickers_2 = [c.strip() for c in self._list_2_section.value.splitlines() if c.isprintable()]

        #trim the ticker with the blank space in it eventually
        final_list = [item for item in tickers_1 if item not in tickers_2]
        final_list = [' '.join([e for e in x.split(' ') if e]) for x in final_list]

        # set the universe picker object with the custom values
        self.univ_picker._dropdown_type.value = 'List'
        self.univ_picker._txt_custom.value = '\n'.join(final_list)
        self.univ_picker._txt_custom.rows = len(final_list) if len(final_list) < 12 else 12
        
        # display info to user
        self._count_text_1.value = 'Total: {} securities<br/>Loading data on {} securities.'.format(len(tickers_1), len(final_list))
        self._count_text_2.value = 'Total: {} securities'.format(len(tickers_2))

        # run the model with custom list first then back to first tab (Matrix)         
        self._run()
        self._main_tab.selected_index = 0


# --------  end main UI  ----------
######################################################################################
####################   Methods for Tabs display       ################################
######################################################################################   
# --------  TAB # 1  ----------
    def on_matrix_hover(self, caller, event):
        try:
            x = event.get('data', {})['row']
            y = event.get('data', {})['column']
            t = [float(i) for i in tuple(y.split('-'))] 
            c = self._df_matrix.loc[x][(t[0],t[1])]
            
            if np.isnan(c):
                self._matrix_tooltip.children = [
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">No data for </span><span>{}</span></p>'.format(x))
                ]
            else:
                self._matrix_tooltip.children = [
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">{} </span><span>{}</span></p>'.format(self._drop_y.value, x)),
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">Maturity </span><span>{}</span></p>'.format(y)),
                    ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">Num bonds </span><span>{:.0f}</span></p>'.format(c))
                ]

        except Exception as e:
            self._matrix_tooltip.children = [ipywidgets.HTML('<p style="font-weight:italic; color:dimgrey;">No data fetched.</p>')]


    def on_matrix_click(self, caller, event):
        category_filter = self._drop_y.value
        row = event.get('data', {})['row']

        # function of the category apply the `row` filter to country/sector
        if category_filter == 'Country':
            self._country_select.value = (row,)
        elif category_filter == 'Industry':
            self._sector_select.value = (row,)

        # display the second tab upon the click
        self._main_tab.selected_index = 1


    def _update_matrix_ui(self):
        '''
        Summary: function called to ensure display of the chart
                 is applied according to user dropdowns input.
                 This needs to cover the chart title, the axis
                 name and the height of the chart.
        '''
        # update the axis name
        self._matrix_ui.axes[0].label = self._drop_x.value

        # update the title
        self._matrix_ui.title = 'Distribution by {} bucket'.format(self._drop_x.value)
        
        # update the height of the chart
        self._tab1_box.children[0].layout.height = '{}px'.format(len(self._df_matrix.index)*25)


    def _update_matrix_change(self, caller):
        '''
        Summary: callback triggered as soon as one of the dropdown value is changed.
        '''
        self._df_matrix = self._model.set_data_as_matrix(self._drop_x.value, self._drop_y.value)
        self._grid_map.row = self._df_matrix.index
        self._grid_map.column = ['{}-{}'.format(c[0],c[1]) for c in self._df_matrix.columns]
        self._grid_map.color = self._df_matrix

        self._update_matrix_ui()


    def _build_matrix(self):
        # create 2 dropdowns for the matrix selection
        self._drop_x = ipywidgets.Dropdown(options=self.matrix_tab_scatter_x)
        self._drop_x.observe(self._update_matrix_change, 'value')
        self._drop_y = ipywidgets.Dropdown(options=self.matrix_tab_scatter_y)
        self._drop_y.observe(self._update_matrix_change, 'value')

        drop_header = ipywidgets.HBox([self._drop_x, self._drop_y], layout={'margin':'10px','overflow_y':'hidden'})

        self._df_matrix = self._model.set_data_as_matrix(self._drop_x.value, self._drop_y.value)

        # create the matrix tooltip
        self._matrix_tooltip = ipywidgets.VBox(layout={'width':'180px','height':'100%'})

        # create the matrix 
        x_sc, y_sc, col_sc = OrdinalScale(), OrdinalScale(reverse=True), ColorScale(scheme='Oranges')
        column_names = ['{}-{}'.format(c[0],c[1]) for c in self._df_matrix.columns]
        self._grid_map = GridHeatMap(row=self._df_matrix.index, column=column_names, color=self._df_matrix, 
                               scales={'column': x_sc, 'row': y_sc, 'color': col_sc},
                               stroke='transparent', null_color='transparent',
                               interactions={'hover':'tooltip'}, tooltip=self._matrix_tooltip,
                               selected_style={'opacity': 1.0}, unselected_style={'opacity': 0.4})

        ax_x, ax_y = Axis(scale=x_sc, grid_lines='none'), \
                     Axis(scale=y_sc, grid_lines='none', orientation='vertical')

        self._matrix_ui = Figure(marks=[self._grid_map], axes=[ax_x, ax_y], padding_y=0.0, 
                           title='',
                           fig_margin={'bottom': 35, 'left': 150, 'right': 10, 'top': 60},
                           layout={'width':'100%', 'height':'100%'})
        
        self._matrix_ui.marks[0].on_hover(self.on_matrix_hover)
        self._matrix_ui.marks[0].on_element_click(self.on_matrix_click)

        
        # define the output object to get displayed
        output = ipywidgets.VBox([drop_header, self._matrix_ui], layout={'width':'99%', 'min_height':'400px', 'overflow_x':'hidden'})
        
        self._tab1_box.children = [output]
        self._update_matrix_ui()
    

# --------  end TAB # 1  ----------------------------------------------------------------
# -----------   TAB # 2  ----------------------------------------------------------------
    def _build_tables(self):
        """Build datagrid as a table based on factor model"""
        self._bool_no_scatter = False # boolean used to display only error message once if missing scatter chart
        
        # access the model data and reshape it nicely for display
        df_all = self._model.get_model_data().reset_index().round(1)
        df_all['Country'] = df_all['Country'].str.title()
        
        # store this in model variable as need to access it from callbacks
        self._df_all = df_all
        self._subset_data = df_all

        definition = [
            {'headerName': 'Securities',
             'children':    [{'headerName': 'Name', 'field': 'Name', 'width': 120}] +
                            [{'headerName': 'Country', 'field': 'Country', 'width': 115}] +
                            [{'headerName': 'Industry', 'field': 'Industry', 'width': 135} ],
             'pinned': 'center'
            },
            {'headerName': 'Characteristics',
                'children': [{'headerName': f, 'field': f, 'width': 70} for f in self._df_all.columns if f not in ['index','Name','Industry','Country']]
            }
        ]

        # build the filters on top
        top_filters = self._build_filters_for_table()

        # datagrid object to get displayed
        self._data_grid = DataGrid(data=self._df_all.fillna('-').round(1), column_defs=definition, 
                                    layout=ipywidgets.Layout(width='800px', height='480px'))
        self._data_grid.observe(self._hightlight_scatter, 'selected_row_indices')

        # text label on top of the table
        self._screen_box = ipywidgets.HTML('<h2>Results for selection ({} results)</h2>'.format(len(self._data_grid.data)))

        # text tooltip to let the user know about scroll
        tips = ipywidgets.HTML(value='''<i><font color="gray"><p>Mouse scroll available. 
                                        <b>Shift + Mouse scroll</b> for more characteristics. </p></font></i>''')
        
        # build the scatter plot once data retrieved
        _scatter_ui = self._build_scatter()
        self.selected_elements = pd.DataFrame([]) #for now, zero items have been selected from the scatter.

        # button for next step > portfolio creation
        # create a text placeholder to store the number of items selected
        self._nb_selected_items = ipywidgets.HTML()

        # create button to bring to next screen
        self._button_rv = ipywidgets.Button(description='Build Portfolio', button_style='success', icon='check')
        self._button_rv.on_click(self._run_relative_comparision)

        # define the output object to get displayed
        output = ipywidgets.VBox([self._screen_box, top_filters, self._data_grid, tips, 
                                    ipywidgets.HBox([_scatter_ui, ipywidgets.VBox([self._nb_selected_items, self._button_rv])])
                                ])
        
        self._tab2_box.children = [output]


    def _run_relative_comparision(self, caller):
        try:
            if self._scatt.selected:
                self.selected_elements = self._subset_data.loc[self._scatt.selected]
                # go to next screen (Relative valuation)
                self._main_tab.selected_index = 2
                self._run_model_portfolio()
            else:
                _logger.warn('Select at least one element to get to next screen.')
        except:
            try:
                # in case no scatter plot (due to display issue), one may want to 
                # access the selection from the data grid
                self.selected_elements = self._data_grid.data.iloc[self._data_grid.selected_row_indices]
            except:
                pass


    def _reset_button(self, caller):
        if caller._id == 'Country':
            self._country_select.value = list(sorted(self._df_all['Country'].unique()))
        if caller._id == 'Industry':
            self._sector_select.value = list(sorted(self._df_all['Industry'].unique()))


    def _filter_dataframe(self, caller):
        # retrieve the list of entries for each filters
        country_filter_list = self._country_select.value
        sector_filter_list  = self._sector_select.value
        # build the mask of the dataset depending on each filter
        sub_section_country = self._df_all['Country'].isin(country_filter_list)
        sub_section_sector  = self._df_all['Industry'].isin(sector_filter_list)
        
        # apply the mask to the full dataset
        new_df = self._df_all[sub_section_country & sub_section_sector]
        self._subset_data = new_df.reset_index(drop=True)

        try:
            self._data_grid.data = self._subset_data.fillna('-')
            self._screen_box.value = '<h4>Results for selection ({} results)</h4>'.format(len(self._subset_data))
            
            # apply subset_data to the scatter plot as well
            self._refresh_scatter_data()

            # update the reg line if activated
            self._update_regression_line()
        
        except Exception as e:
            _logger.warn('No filter applied. Issue when connecting the dots.. {}'.format(e))
            

    def _build_filters_for_table(self):
        # specific layout for button  (big red cross)
        button_layout = {'width':'15px','height':'68px','margin':'4px 2px 0 2px', 'overflow_x':'hidden'}

        # get unique list of filters
        unique_countries = list(sorted(self._df_all['Country'].unique()))
        unique_sectors = list(sorted(self._df_all['Industry'].unique()))

        # create the multi-select
        country_label = ipywidgets.HTML(value='Filter by Country')
        self._country_select = ipywidgets.SelectMultiple(options=unique_countries, rows=4, value=unique_countries)
        self._country_select.observe(self._filter_dataframe, 'value')

        sector_label = ipywidgets.HTML(value='Filter by Industry')
        self._sector_select = ipywidgets.SelectMultiple(options=unique_sectors, rows=4, value=unique_sectors)
        self._sector_select.observe(self._filter_dataframe, 'value')

        # create the button to reset the selection easily
        country_reset = ipywidgets.Button(button_style='danger', description='x', layout=button_layout)
        country_reset._id = 'Country'
        country_reset.on_click(self._reset_button)
        sector_reset = ipywidgets.Button(button_style='danger', description='x', layout=button_layout)
        sector_reset._id = 'Industry'
        sector_reset.on_click(self._reset_button)

        ui_set_country = ipywidgets.HBox([
                                ipywidgets.VBox([country_label,  
                                                 ipywidgets.HBox([self._country_select, country_reset]),]),
                                ipywidgets.VBox([sector_label,  
                                                 ipywidgets.HBox([self._sector_select, sector_reset]),
                                        ])
            ])
        return ui_set_country


    def _hightlight_scatter(self, caller):
        try:
            idx = caller.new
            self._scatt.selected = idx

            # and at the same time, update the text above the model portfolio button
            self._nb_selected_items.value = 'Selected securities: {}'.format(len(self._scatt.selected)) 
        except:
            if not self._bool_no_scatter:
                _logger.error('No data or no scatter plot available.')
                self._bool_no_scatter = True


#########     Anything about scatter (hover+button_main UI)     #################################

    def _on_distrib_hover(self, caller, event):
        try:
            i = event.get('data', {})['index']
            exclusion_list = ['index','Year to mat','US 10y T','intRating']
            
            # define the elements as list of ipywidgets to 
            # store the item charateristics
            elements = []
            for e in self._subset_data.columns:
                if not e in exclusion_list:
                    elements.append(ipywidgets.HTML('<p><span style="font-weight:bold; color:dimgrey;">{}: </span> \
                                                     <span>{}</span></p>'.format(e, self.df_temp_scatter.reset_index().loc[i,e])))

            self._distrib_tooltip.children = elements

        except Exception as e:
            _logger.warn('Small glitch while fetching tooltip data: {}'.format(e))


    def _on_distrib_click(self, caller, event):
        try:
            # if this callback is triggered, some elements are selected 
            # we can then display the number in the label
            self._nb_selected_items.value = 'Selected securities: {}'.format(len(self._scatt.selected))
        except:
            pass


    def _activate_lasso(self, change):
        if change.new:
            self._distrib.interaction = self._brusher
        else:
            self._distrib.interaction = None


    def _activate_regression_line(self, *args):
        self._update_regression_line()

    def _update_regression_line(self, deg=1):
        # get the list of points available on the scatter
        x_ = self._scatt.x
        y_ = self._scatt.y

        if self._r_control_scatter.value:
            try:
                # run regression
                fit = np.polyfit(x_, y_, deg)
                # create new line mark
                self._reg_line.x = x_, 
                self._reg_line.y = fit[0] * x_ + fit[1]

            # Plot can contain date or string information
            except TypeError:
                self._reg_line.x = []
                self._reg_line.y = []
                _logger.warn('Error type issue in regression line (no line coefficient)')
        else:
            self._reg_line.x = []
            self._reg_line.y = []
            

    def _refresh_scatter_data(self):
        # retrieve the list of fields selected in the controls
        columns = '|'.join(str(e) for e in [self._x_control_scatter.value,self._y_control_scatter.value,self._z_control_scatter.value]).split('|')
        # create a temp df to host the data only for the scatter 
        self.df_temp_scatter = self._data_grid.data.replace('-',np.nan).dropna(axis=0, subset=columns)

        # assign the data to the scatter axis
        self._scatt.x = self.df_temp_scatter[self._x_control_scatter.value]
        self._scatt.y = self.df_temp_scatter[self._y_control_scatter.value]
        self._scatt.color = self.df_temp_scatter[self._z_control_scatter.value]


    def _build_scatter(self):
        '''
        Summary: main function that constructs the scatter plot
                 at the bottom of the Datgrid (Tab#2)
         '''
        try: 
            # create 3 dropdowns for the user to select the metrics for the scatter plot
            self._x_control_scatter = ipywidgets.Dropdown(description='x-axis control',
                                                          options=list(self.table_tab_select_x), layout={'width':'200px'})
            self._y_control_scatter = ipywidgets.Dropdown(description='y-axis control',
                                                          options=list(self.table_tab_select_y), layout={'width':'200px'})
            self._z_control_scatter = ipywidgets.Dropdown(description='color scale',
                                                          options=list(self.table_tab_select_z), layout={'width':'200px'})
            control_set_1 = ipywidgets.HBox([self._x_control_scatter, self._y_control_scatter, self._z_control_scatter])

            # create the 2 checkbox to control the reg line and lasso selection
            # checkbox for regression line activation
            self._r_control_scatter = ipywidgets.Checkbox(description='Activate Regression Line', value=True,
                                                          style={'description_width':'initial'})
            self._r_control_scatter.observe(self._activate_regression_line, 'value')
            # checkbox for lasso selection activation
            self._l_control_scatter = ipywidgets.Checkbox(description='Activate Lasso selection', value=False,
                                                          style={'description_width':'initial'})
            self._l_control_scatter.observe(self._activate_lasso, 'value')

            control_set_2 = ipywidgets.HBox([self._r_control_scatter, self._l_control_scatter])

            self._controls_scatter = ipywidgets.VBox([control_set_1, control_set_2],
                                                      layout={'padding':'10px', 'border':'1px solid dimgray', 'margin':'5px 0 0 0'})

            
            # create the tooltip for scatter plot
            self._distrib_tooltip = ipywidgets.VBox(layout={'width':'360px','height':'320px','overflow_y':'hidden'})

            # create the scatter object (scale, brusher, reg line, axis, and figure)
            sc_x, sc_y, sc_c = LinearScale(), LinearScale(), ColorScale(min=0)

            self._scatt = Scatter(x=[], y=[], color=[], 
                            scales={'x': sc_x, 'y': sc_y, 'color':sc_c},
                            colors=['dodgerblue'], stroke='white',
                            interactions={'hover':'tooltip','click':'select'}, tooltip=self._distrib_tooltip,
                            selected_style={'opacity':1.0, 'fill':'DarkOrange', 'stroke':'Red'},
                            unselected_style={'opacity':0.9})

            # create the brush selector object
            self._brusher = BrushSelector(x_scale=sc_x, y_scale=sc_y, marks=[self._scatt], color='orange')
            self._brusher.observe(self._brusher_callback, names=['brunching'])

            # add a regression line on the scatter plot
            self._reg_line = Lines(x=[], y=[], opacities=[.5], colors=['DarkOrange'],
                                   line_style='solid', stroke_width=1.5,
                                   scales={'x': sc_x, 'y': sc_y})

            self.ax_x, self.ax_y, self.ax_c = Axis(scale=sc_x, label=self._x_control_scatter.value), \
                                              Axis(scale=sc_y, orientation='vertical', tick_format='0.1f', label=self._y_control_scatter.value), \
                                              ColorAxis(scale=sc_c, label=self._z_control_scatter.value, orientation='vertical', side='right')

            self._distrib = Figure(marks=[self._scatt, self._reg_line], axes=[self.ax_x, self.ax_y, self.ax_c],
                                   title='Distribution of bond universe', animation_duration=1000,
                                   fig_margin={'bottom':30, 'left':45, 'right':120, 'top':30})

            # handle the hover effect and click action
            self._scatt.on_hover(self._on_distrib_hover)
            self._scatt.on_element_click(self._on_distrib_click)
            
            # observe controls for the dropdowns
            def _scatter_axis_change(caller):
                self._refresh_scatter_data()
                if caller.owner == self._x_control_scatter:
                    self.ax_x.label = caller.new
                elif caller.owner == self._y_control_scatter:
                    self.ax_y.label = caller.new
                elif caller.owner == self._z_control_scatter:
                    self.ax_c.label = caller.new
                else:
                    pass
                self._update_regression_line()

            self._x_control_scatter.observe(_scatter_axis_change, 'value')
            self._y_control_scatter.observe(_scatter_axis_change, 'value')
            self._z_control_scatter.observe(_scatter_axis_change, 'value')


            # call the data scatter refresh at least once to display initial dataset
            self._refresh_scatter_data()
            self._activate_regression_line()

            return ipywidgets.VBox([self._distrib, self._controls_scatter], 
                                    layout={'margin':'5px'})  

        except Exception as e:
            _logger.error('Cannot display the scatter chart. Not enough data. Error: {}'.format(e))
            return ipywidgets.HBox([])


    def _brusher_callback(self, change):
        # get the boundaries of the highlighted data
        x_bounds = self._brusher.selected_x
        y_bounds = self._brusher.selected_y

        # get the data from the current subset displayed in the table (in case some filtering)
        d = self._subset_data

        # get the field names of the current dropdown selection
        x = self._x_control_scatter.value
        y = self._y_control_scatter.value

        d_brushed = d[(d[x]>x_bounds[0]) & (d[x]<x_bounds[1]) & (d[y]>y_bounds[0]) & (d[y]<y_bounds[1])]

        # apply the brushed data to the data table and to the model portfolio selection
        self._data_grid.data = d_brushed#.fillna('-')

        #self.selected_elements = self._subset_data.iloc[self._scatt.selected]
        self._nb_selected_items.value = 'Selected securities: {}'.format(len(d_brushed)) 
        _logger.info('Selected securities by lasso: {}'.format(len(d_brushed)) )

# --------  end TAB # 2  ----------------------------------------------------------------
# -----------   TAB # 3  ----------------------------------------------------------------
    def _build_model_portfolio(self):
        
        # text label on top of the tab
        self._model_title = ipywidgets.HTML('<h3>Model portfolio valuation </h3>')
        default_text = ipywidgets.HTML('Select some elements from the table')
        
        self._output_tab3 = ipywidgets.VBox([self._model_title, default_text],
                                            layout={'margin':'20px'})


    def _run_model_portfolio(self):
        try:
            if not self.selected_elements.empty:
                # use this technic to display item items along the flow. Helps in debugging
                tab3_children = [self._model_title]
                # make sure the table can be displayed
                model_df = self.selected_elements.set_index('index')[list(self.model_tab_header)]
                model_df = model_df.replace('-',np.nan)
                
                # create the df.render for the data display
                obj_df = self._final_to_html(model_df)
                self._final_data = ipywidgets.HTML(obj_df) 
                tab3_children.append(ipywidgets.Box([ self._final_data], layout={'margin':'10px 0 30px 0'}))

                # define the dropdown for selection
                self._item_select = ipywidgets.Dropdown(options=list(self.model_tab_select_x), description='Select a metric', 
                                                        style={'description_width':'initial'})
                self._item_select.observe(self._on_item_select_change, 'value')
                tab3_children.append(self._item_select)

                # construct the line chart\
                self._valuation_lines = self._construct_valuation_lines()
                tab3_children.append(self._valuation_lines)

                # run the bar chart display once after loading the page
                self._on_item_select_change({'new':list(self.model_tab_select_x)[0]})

                # create a container with the dorpdown for the chart, the chart itself,
                # and the save to portfolio button
                def save_to_port_callback(caller):
                    self.portfolio_save_status.value = 'Saving Portfolio...'
                    # define the name
                    self.portfolio_label_name.value = 'MODEL_FI_001' if self.portfolio_label_name.value == '' else self.portfolio_label_name.value
                    # get the universe defined
                    tickers_selected = list(self.selected_elements['index'])
                    self.save_portfolio(name=self.portfolio_label_name.value, tickers_list=tickers_selected)


                self.btn_save_to_portfolio = ipywidgets.Button(description='Save to PORT', button_style='success')
                self.btn_save_to_portfolio.on_click(save_to_port_callback)
                self.portfolio_label_name = ipywidgets.Text(description='Model Name', placeholder='MODEL_FI_001',
                                                             layout={'description_width':'initial'})
                self.portfolio_save_status = ipywidgets.HTML('Select a name and hit Save to share <br/>this model portfolio with others.',
                                                              layout={'description_width':'initial'})

                self.save_port_box = ipywidgets.HBox([self.portfolio_label_name, self.btn_save_to_portfolio, self.portfolio_save_status],
                                                      layout={'padding':'10px', 'border':'1px solid dimgray', 'margin':'20px 0 0 0'})
                tab3_children.append(self.save_port_box)

                # append to the output display for tab 3
                self._tab3_box.children = [ipywidgets.VBox(children=tab3_children, layout={'margin':'20px'})]

        except Exception as e:
            _logger.warn('Small glitch in the matrix. Try other inputs...')
            _logger.warn('Error: {}'.format(e))
            # append to the output display for tab 3
            self._tab3_box.children = [ipywidgets.VBox(children=tab3_children, layout={'margin':'20px'})]   


    def save_portfolio(self, name, tickers_list):
        try:
            # Create portfolio
            port_df = pd.DataFrame([
                {'date':datetime.datetime.today() + datetime.timedelta(days=-5*365), 'security':ticker, 'quantity':1} for ticker in tickers_list
            ])
            port_df.set_index(['date', 'security'], inplace=True)
            portfolio_obj = bqport.new_portfolio(from_=port_df, type_=bqport.PositionType.SIZED, name=name)
            portfolio_obj.update()
            
            portfolio_obj.save()
            _logger.info('Portfolio saved. ')
            self.portfolio_save_status.value = 'Access it on >><a color="white" href="https://blinks.bloomberg.com/screens/PORT">PORT</a>'
            
        except Exception as e:
            self.portfolio_save_status.value = '<font color="#cc1619">Error while saving.</font> (no save)'
            _logger.warn('Error while saving... {}'.format(e))


    # def _construct_group_data(self):

    #     # transform data in numerical values 
    #     # and remove the nans 
    #     self.selected_elements = self.selected_elements.replace('-',np.nan).dropna(axis=0)
    #     items = list(self.model_tab_select_x)

    #     # build the group generator
    #     gr_model_p = self.selected_elements.groupby(by=self.model_tab_group_a)[items]

    #     # get the min/mean/max
    #     df_min = gr_model_p.min()[items]
    #     df_min.rename(columns={c:'{}_Min'.format(c) for c in df_min.columns}, inplace=True)

    #     df_mean = gr_model_p.mean()[items]
    #     df_mean.rename(columns={c:'{}_Mean'.format(c) for c in df_mean.columns}, inplace=True)

    #     df_max = gr_model_p.max()[items]
    #     df_max.rename(columns={c:'{}_Max'.format(c) for c in df_max.columns}, inplace=True)

    #     # stitch the data together
    #     gr_model = pd.merge(df_min, df_mean, left_index=True, right_index=True)
    #     gr_model = pd.merge(gr_model, df_max, left_index=True, right_index=True)
    #     return gr_model.round(2)


    def _to_html(self, df):
        return (
                df.round(2).style
                .set_properties(**{'font-size':'9pt', 'color':'white', 'font-family':'Arial', })
                .render()
            )


    def _final_to_html(self, df):
        try:
            def hover(hover_color='#525252'):
                return dict(selector='tr:hover',
                            props=[('background-color', hover_color)])
            
            return (
                    df.round(2).style
                    .set_properties(**{'font-size':'9pt', 'color':'white'})
                    .bar(subset=['Z-Spread','Z-Score'], color='#ec7014')
                    .set_table_styles([
                        hover(),
                        dict(selector='table', props=[('border-spacing','50px'), ('background-color','transparent')]),
                        dict(selector='th', props=[('font-size','110%'), ('text-align','center'),
                                                   ('padding','5px'), ('border-bottom','1px solid #ddd')]),
                        dict(selector='tr', props=[('font-size','100%'), ('text-align','center'),]),
                        dict(selector='caption', props=[('caption-side','top')])
                    ])
                    .render()
                )
        except:
            _logger.error('Cannot display final table. Going on...')


    def _on_item_select_change(self, caller):
        i = caller['new']

        ## for LINE chart
        tickers = list(self.selected_elements['index'])
        df = self._model._get_history(ids=tickers, field_name=i, history_period='-1y')

        self._valuation_lines.marks[0].x = df.index
        self._valuation_lines.marks[0].y = df.T.values
        self._valuation_lines.marks[0].labels = list(df.columns)
        self._valuation_lines.title = 'Relative valuation ({})'.format(i)
        

    def _construct_credit_bar(self):
        # create the scales
        sc_x, sc_y = OrdinalScale(), LinearScale()
        # define the tooltip when mouse over
        _bar_tooltip = Tooltip(fields=['x', 'y'], formats=['', '.2f'])
        # define the bar mark
        bar = Bars(x=[], y=[], scales={'x': sc_x, 'y': sc_y}, padding=0.2, type='grouped',
                   color_mode='group', colors=['#edf8b1','#7fcdbb','#2c7fb8'], stroke='black',
                   interactions={'hover':'tooltip','click':'select'}, tooltip=_bar_tooltip,
                   selected_style={'opacity':1.0,'fill':'DarkOrange','stroke':'Red'}, unselected_style={'opacity':0.9})

        ax_x, ax_y = Axis(scale=sc_x, tick_rotate=-25, tick_style={'text-anchor': 'end'}), \
                     Axis(scale=sc_y, orientation='vertical')
        
        # define figure
        credit_bar_fig = Figure(marks=[bar], axes=[ax_x, ax_y], 
                                title='Min/Avg/Max by Credit groups',
                                fig_margin={'bottom':90, 'left':20, 'right':0, 'top':20})

        return credit_bar_fig


    def _index_change_callback(self, change):
        if change['new']:
            s_date = np.datetime64(change['new'][0]).astype(datetime)
            
            try:
                value = '{:0.2f}'.format(df.loc[datetime.strftime(s_date, '%Y-%m-%d')])
            except:
                value = '-'
            self._highlighted_text.value = '<p style="color:ivory;">Selected date is {} - value is {}</p>'.format(datetime.strftime(s_date, '%d-%b-%y'), value)
        

    def _construct_valuation_lines(self):
        # create the scales
        sc_x, sc_y = DateScale(), LinearScale()
        # build the axis
        ax_x = Axis(
            scale=sc_x, tick_rotate=-45, tick_style={'text-anchor': 'end'}, label_location='middle', 
            grid_lines='none', tick_format='%d-%b-%y', num_ticks=10)
        ax_y = Axis(orientation='vertical', scale=sc_y, label_location='middle', grid_lines='none')
        # define the line mark
        lines = Lines(x=[], y=[], labels=[], scales={'x': sc_x, 'y': sc_y}, 
                      labels_visibility='label', display_legend=True,
                      colors=['#0066ff','#33ccff','#00ff99','#99ff33','#ccff33','#ffff66','#ffffcc'], stroke_width=2)

        # HTML label to indicate which date has been highlighted
        self._highlighted_text = ipywidgets.HTML()

        # final figure, integrating the index_selector as interaction
        fig_line = Figure(marks=[lines], axes=[ax_x, ax_y], title='Relative valuation', layout={'width': '99%', 'height': '400px'})

        return fig_line


######################################################################################
####################   Class for UniversePicker       ################################
######################################################################################

    class UniversePicker:   
        def __init__(self, layout=None):
            """Widgets for picking a universe. Index members and portfolio members are supported."""
            config_file = pd.read_excel('config.xlsx', sheetname='controls')
            self._default_index = config_file[config_file.control_name == 'index']['default'].values[0]

            widget_layout = {'width':'120px'}
            self._dropdown_type = ipywidgets.Dropdown(options=['Index', 'Portfolio', 'List'], layout={'max_width':'80px'})
            self._dropdown_port = ipywidgets.Dropdown(layout=widget_layout)
            self._ac_index = TickerAutoComplete(yellow_keys=['Index'], value=self._default_index, layout=widget_layout)
            self._txt_custom = ipywidgets.Textarea(placeholder='Place one ticker per line', layout=widget_layout, rows=8)
            
            layout = {'layout': layout} if layout else {}
            self._box = ipywidgets.HBox([self._dropdown_type], **layout)
            
            self._dropdown_type.observe(self._on_univ_type_change, 'value')
            
            # Call the event handler to show the default widget.
            self._on_univ_type_change()

        def show(self):
            return self._box

        def _on_univ_type_change(self, *args, **kwargs):
            # Show different widgets according to the universe type user selected.
            univ = self._dropdown_type.value
            if univ == 'Index':
                self._box.children = [self._dropdown_type, self._ac_index]
            
            elif univ == 'Portfolio':
                self._box.children = [self._dropdown_type, self._dropdown_port]
                portfolios = bqport.list_portfolios()
                portfolios = sorted([(p['name'], p['id']) for p in portfolios])
                self._dropdown_port.options = portfolios
                
            elif univ == 'List':
                self._txt_custom.placeholder = 'Place one ticker per line'
                self._box.children = [self._dropdown_type, self._txt_custom]


   ######################################################################################