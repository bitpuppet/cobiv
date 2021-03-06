from kivy.factory import Factory
from kivy.uix.label import Label

from cobiv.modules.core.component import Component


class LabelWidget(Label, Component):
    def __init__(self, **kwargs):
        super().__init__(markup=True, size_hint=(1, None), halign='left', valign='top', **kwargs)
        self.bind(width=lambda *x: self.setter('text_size')(self, (self.width, None)),
                  texture_size=lambda *x: self.setter('height')(self, self.texture_size[1]))

        self.session = self.get_app().lookup("session", "Entity")
        self.template_text = kwargs.get('text')
        self.refresh()

    def refresh(self):
        self.text = self.session.fill_text_fields(self.template_text)


Factory.register('LabelWidget', cls=LabelWidget)
