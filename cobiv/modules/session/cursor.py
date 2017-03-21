from kivy.app import App
from kivy.event import EventDispatcher
from kivy.properties import StringProperty, ObjectProperty, NumericProperty


class CursorInterface(EventDispatcher):
    filename = StringProperty(None)
    id = NumericProperty(None)

    def go_next(self):
        return False

    def go_previous(self):
        return False

    def go_first(self):
        return False

    def go_last(self):
        return False

    def get_file_key(self):
        return None

    def get_pos(self):
        return 0

    def get(self, idx):
        return self

    def go(self, idx):
        return False

    def get_tags(self):
        return []

    def mark(self):
        pass

    def get_mark(self):
        return False

    def remove(self):
        return False

    def __len__(self):
        return 0


class Cursor(EventDispatcher):
    filename = StringProperty(None)
    implementation = None
    id = NumericProperty(None)

    def __init__(self, **kwargs):
        super(Cursor, self).__init__(**kwargs)

    def get_app(self):
        return App.get_running_app()

    def set_implementation(self, instance):
        if self.implementation is not None:
            self.implementation.unbind(filename=self.on_filename_change, id=self.on_id_change)
        self.implementation = instance
        if instance is not None:
            self.implementation.bind(filename=self.on_filename_change)
            self.implementation.bind(id=self.on_id_change)
            self.filename = self.implementation.filename
            self.id = self.implementation.id
        else:
            self.filename = None
            self.id = None

    def on_id_change(self, instance, value):
        self.id = value

    def on_filename_change(self, instance, value):
        self.filename = value

    def go_next(self):
        return self.implementation.go_next()

    def go_previous(self):
        return self.implementation.go_previous()

    def go_first(self):
        return self.implementation.go_first()

    def go_last(self):
        return self.implementation.go_last()

    def get_file_key(self):
        return self.implementation.get_file_key()

    def get_pos(self):
        return self.implementation.get_pos()

    def get(self, idx):
        return self.implementation.get(idx)

    def go(self, idx):
        return self.implementation.go(idx)

    def get_tags(self):
        return self.implementation.get_tags()

    def mark(self):
        self.implementation.mark()
        self.get_app().root.execute_cmd("refresh-marked")

    def get_mark(self):
        return self.implementation.get_mark()

    def remove(self):
        return self.implementation.remove()

    def __len__(self):
        return self.implementation.__len__()