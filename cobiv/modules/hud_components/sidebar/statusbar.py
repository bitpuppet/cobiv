from kivy.factory import Factory
from kivy.properties import NumericProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from cobiv.modules.core.component import Component


class StatusLabel(Component, Label):
    def __init__(self, **kwargs):
        super(StatusLabel, self).__init__(valign='middle', **kwargs)
        self.bind(size=self.setter('text_size'))
        self.session = self.get_session()
        self.template_text = kwargs.get('text')
        self.refresh()

    def refresh(self):
        if self.session is not None:
            self.text = self.session.fill_text_fields(self.template_text)
        else:
            self.text = self.template_text


class StatusBar(Component, BoxLayout):
    enabled = BooleanProperty(True)

    def __init__(self, **kwargs):
        height = kwargs.pop('height', 20)
        super().__init__(size_hint=(1, None), height=height, **kwargs)
        self.session = self.get_session()
        if self.session is not None:
            self.session.cursor.bind(file_id=self.on_file_id_change)
        self.bind(enabled=self.set_enabled)

    def set_enabled(self, instance, value):
        if value:
            self.bind_cursor()
        else:
            self.unbind_cursor()

    def on_file_id_change(self, instance, value):
        self.refresh_widgets()

    def refresh_widgets(self):
        for c in self.children:
            refresh = getattr(c, 'refresh', None)
            if refresh is not None:
                c.refresh()

    def add_label(self, text='', align='center', size=0, **kwargs):
        if size == 0:
            label = StatusLabel(text=text, halign=align)
        else:
            label = StatusLabel(text=text, halign=align, width=size, size_hint=(None, 1))
        self.add_widget(label)

    def init_items(self, config_items):
        for cfg_item in config_items:
            self.add_label(**cfg_item)

    def bind_cursor(self):
        pass

    def unbind_cursor(self):
        pass

Factory.register('SimpleStatusBar', cls=StatusBar)
