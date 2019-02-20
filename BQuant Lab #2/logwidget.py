from collections import deque
import datetime as dt
from IPython.display import display
from ipywidgets import HTML
import logging


class LogWidgetAdapter(logging.LoggerAdapter):
    def __init__(self, logger, extra={}):
        super().__init__(logger, extra)

    def process(self, msg, kwargs):
        color = kwargs.get('color')
        extra = kwargs.get('extra', {})
        extra['color'] = color
        kwargs['extra'] = extra

        return (msg, kwargs)


class LogWidgetHandler(logging.Handler):
    def __init__(self, widget=None, *args, **kwargs):
        self.widget = widget
        super().__init__(*args, **kwargs)

    def emit(self, record):
        try:
            msg = self.format(record)
            if hasattr(record, 'color'):
                color = record.color
            else:
                color = None

            if color is None:
                if record.levelno == logging.INFO:
                    color = 'whitesmoke'
                elif record.levelno == logging.WARN:
                    color = 'yellow'
                elif record.levelno == logging.ERROR:
                    color = 'crimson'
                else:
                    color = None

            self.widget.log_message(msg, color)

        except Exception:
            self.handleError(record)


class LogWidget(object):
    def __init__(self, max_msgs=20, layout=None):
        self.widgets = dict()
        self.msg_queue = deque(maxlen=max_msgs)

        default_layout = {
            'display': 'flex',
            'max_height': '75px',
            'overflow_y': 'auto'
        }
        default_layout.update(layout or {})
        widget_html_console = HTML('', layout=default_layout)
        self.widgets['html_console'] = widget_html_console

    def log_message(self, msg, color=None):
        if color is not None:
            msg_color_temp = """<font color="{font_color}">{user_msg}</font>"""
            msg = msg_color_temp.format(font_color=str(color), user_msg=msg)

        self.msg_queue.appendleft(msg)
        self._update()

    def _update(self):
        html_string = '<br>'.join(list(self.msg_queue))
        html_string = '<div style="margin: 3px;">{}</div>'.format(html_string)
        self.widgets['html_console'].value = html_string

    def get_widget(self):
        widget_html_console = self.widgets['html_console']
        return widget_html_console

    def display_widget(self):
        display(self.widgets['html_console'])
