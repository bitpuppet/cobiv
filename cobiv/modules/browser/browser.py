import threading
from collections import deque

import time
from kivy.app import App
from kivy.effects.dampedscroll import DampedScrollEffect
from kivy.lang import Builder
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView

from cobiv.modules.browser.item import Item
from cobiv.modules.browser.thumbloader import ThumbLoader
from cobiv.modules.component import Component
from cobiv.modules.view import View
from kivy.properties import ObjectProperty, NumericProperty
from kivy.clock import Clock
import os

Builder.load_file('modules/browser/browser.kv')


class VerticalLoadEffect(DampedScrollEffect):
    def __init__(self, **kwargs):
        super(VerticalLoadEffect, self).__init__(**kwargs)
        self.trigger_load_next = Clock.create_trigger(self.load_next, 0.5)
        self.trigger_load_previous = Clock.create_trigger(self.load_prev, 0.5)

    def on_overscroll(self, *args):
        super(VerticalLoadEffect, self).on_overscroll(*args)
        if self.overscroll < -50:
            self.trigger_load_previous()
        elif self.overscroll > 50:
            self.trigger_load_next()

    def load_prev(self, dt):
        App.get_running_app().root.get_view().load_more(direction=False)

    def load_next(self, dt):
        App.get_running_app().root.get_view().load_more()


class ThumbScrollView(ScrollView):
    def __init__(self, **kwargs):
        super(ThumbScrollView, self).__init__(effect_y_cls=VerticalLoadEffect, **kwargs)


class Browser(View, FloatLayout):
    cursor = None
    page_cursor = None
    selected_image = None
    grid = ObjectProperty(None)

    cell_size = NumericProperty(120)
    page_rows = NumericProperty(None)
    max_rows = NumericProperty(None)
    max_scroll_ratio = NumericProperty(3)
    max_items_cache = NumericProperty(None)

    global_scroll_pos = NumericProperty(0)
    session = None
    image_queue = deque()
    append_queue = True
    pending_actions = deque()
    widget_to_scroll = None
    thumb_loader = None

    def __init__(self, **kwargs):
        super(Browser, self).__init__(**kwargs)

        self.tg_select_next=Clock.create_trigger(self.select_next,0.1)
        self.tg_select_previous=Clock.create_trigger(self.select_previous,0.1)
        self.tg_select_up=Clock.create_trigger(self.select_up,0.1)
        self.tg_select_down=Clock.create_trigger(self.select_down,0.1)


        self.set_action("load-set", self.load_set)
        self.set_action("next", self.tg_select_next)
        self.set_action("down", self.tg_select_down)
        self.set_action("previous", self.tg_select_previous)
        self.set_action("up", self.tg_select_up)
        self.set_action("mark", self.mark_current)
        self.set_action("mark-all", self.mark_all)
        self.set_action("mark-invert", self.mark_invert)

    def get_name(self=None):
        return "browser"

    def build_yaml_config(self, config):
        config[self.get_name()] = {
            'hotkeys': [
                {'key': '273', 'binding': 'up'},
                {'key': '274', 'binding': 'down'},
                {'key': '275', 'binding': 'next'},
                {'key': '276', 'binding': 'previous'},
                {'key': '32', 'binding': 'mark'},
                {'key': '13', 'binding': 'switch-view viewer'},
                {'key': '97', 'binding': 'mark-all'},
                {'key': '105', 'binding': 'mark-invert'}
            ],
            'cache': {
                'thumbnails': {
                    'size': '500'
                }
            }
        }
        return config

    def ready(self):
        Component.ready(self)
        self.thumbs_path = self.get_global_config_value('thumbnails.path')

        self.session = self.get_app().lookup("session", "Entity")
        self.cursor = self.session.cursor

        self.thumb_loader = ThumbLoader()
        self.thumb_loader.container = self

    def on_switch(self):
        self.cursor.bind(file_id=self.on_id_change)
        self.load_set()
        if self.selected_image is not None:
            Clock.schedule_once(self.scroll_to_image)
        self.thumb_loader.restart()

    def on_switch_lose_focus(self):
        self.cursor.unbind(file_id=self.on_id_change)
        self.thumb_loader.stop()

    def scroll_to_image(self, dt):
        self.ids.scroll_view.scroll_to(self.selected_image)

    #########################################################
    # lazy loading
    #########################################################

    def load_set(self):
        self.grid.clear_widgets()

        if self.cursor.file_id is None:
            return

        self.start_progress("Loading thumbs...")
        self.pending_actions.append(self._load_set)
        self.pending_actions.append(self._load_process)
        self.do_next_action()

    def _load_set(self, dt):
        max_count = self.max_rows * self.grid.cols
        self.set_progress_max_count(max_count)
        self.reset_progress()

        self.page_cursor = self.cursor.get_cursor_by_pos(max(0, self.cursor.pos - max_count / 2))

        c = self.cursor.get_cursor_by_pos(self.page_cursor.pos)
        self.append_queue = True

        count = 0
        for i in range(max_count):
            thumb_data = c.get_thumbnail()

            self.image_queue.append((thumb_data, c.file_id, c.pos, c.filename))

            count += 1
            if count >= max_count or not c.go_next():
                break

        while count < self.max_items_cache * self.grid.cols:
            if not c.go_next():
                break

            self.thumb_loader.append((c.file_id, c.filename))

            count += 1

        self.reset_progress()
        self.do_next_action()

    def _load_process(self, dt):
        t0=time.time()
        if len(self.image_queue) > 0:
            for i in range(self.grid.cols):
                thumb_filename, file_id, pos, image_filename = self.image_queue.popleft()
                thumb = self.thumb_loader.get_image(file_id, thumb_filename, image_filename)

                item = Item(thumb=thumb, container=self,
                            cell_size=self.cell_size, file_id=file_id, position=pos, duration=0)

                if file_id == self.cursor.file_id:
                    self.selected_image = item
                    item.set_selected(True)

                if self.append_queue:
                    self.grid.add_widget(item)
                else:
                    self.grid.add_widget(item, len(self.grid.children))

                self.tick_progress()

            if len(self.image_queue)>0:
                Clock.schedule_once(self._load_process, 0)
        print(str(time.time()-t0))
        self.stop_progress()
        self.do_next_action(immediat=True)

    ####################################################

    def select_next(self,dt):
        if self.cursor.filename is not None:
            self.cursor.go_next()
            if self.grid.children[0].position-self.grid.cols<self.cursor.pos:
                self.load_more()

    def select_previous(self,dt):
        if self.cursor.filename is not None:
            self.cursor.go_previous()
            if self.grid.children[-1].position+self.grid.cols>self.cursor.pos:
                self.load_more(direction=False)

    def select_down(self,dt):
        if self.cursor.filename is not None:
            if not self.select_row(1):
                self.cursor.go_last()

    def select_up(self,dt):
        if self.cursor.filename is not None:
            if not self.select_row(-1):
                self.cursor.go_first()

    def select_row(self, diff):
        pos = self.cursor.pos - self.page_cursor.pos

        nb_cols=self.grid.cols

        linenr = pos / nb_cols
        colnr = pos % nb_cols
        new_pos = colnr + (linenr + diff) * nb_cols

        if new_pos>(self.max_rows-1)*nb_cols:
            self.load_more()
        elif new_pos<=nb_cols:
            self.load_more(direction=False)

        return self.cursor.go(self.page_cursor.pos + new_pos)


    def on_id_change(self, instance, value):
        if self.cursor.filename is None or self.cursor.filename == '' or value is None or len(self.grid.children) == 0:
            if self.selected_image is not None:
                self.selected_image.img.selected = False
            self.selected_image = None
        else:
            thumbs = [image for image in self.grid.children if image.file_id == value]
            if len(thumbs) > 0:
                if self.selected_image is not None:
                    self.selected_image.set_selected(False)
                item = thumbs[0]
                item.set_selected(True)
                self.selected_image = item
                self.ids.scroll_view.scroll_to(item)
            else:
                print("thumbs are empty")
                if self.cursor.pos > self.grid.children[0].position:
                    self.cursor.go(self.grid.children[0].position)
                else:
                    self.cursor.go(self.page_cursor.pos)

    def on_image_touch_up(self, img):
        # select item
        self.cursor.go(img.position)

    def mark_current(self, value=None):
        self.cursor.mark(value)

    def mark_all(self, value=None):
        self.get_app().root.execute_cmd("mark-all", value)

    def mark_invert(self):
        self.get_app().root.execute_cmd("invert-mark")

    def load_more(self, direction=True, factor=1):
        if len(self.grid.children) == 0:
            self.do_next_action()
            return

        if direction:
            last_pos = self.grid.children[0].position
        else:
            last_pos = self.grid.children[-1].position
        c = self.cursor.get_cursor_by_pos(last_pos)

        to_load = self.grid.cols * factor
        max_count = self.max_items_cache * self.grid.cols

        self.image_queue.clear()
        self.append_queue = direction

        if direction:
            list_id = c.get_next_ids(max_count)
        else:
            list_id = c.get_previous_ids(to_load)

        idx = 0
        for id_file, position, filename in list_id:
            if idx < to_load:
                thumb_filename = os.path.join(self.thumbs_path, str(id_file) + '.png')
                self.image_queue.append((thumb_filename, id_file, position, filename))
            else:
                self.thumb_loader.append((id_file, filename))
            idx += 1

        if len(self.image_queue) > 0:
            self.pending_actions.append(self._load_process)
            if direction:
                self.pending_actions.append(self._remove_firsts)
            else:
                self.pending_actions.append(self._remove_lasts)
            self.do_next_action()
        else:
            self.stop_progress()

    def do_next_action(self,immediat=False):
        if len(self.pending_actions) > 0:
            action = self.pending_actions.popleft()
            if immediat:
                action(0)
            else:
                Clock.schedule_once(action)

    def _remove_firsts(self, dt):
        child_count = len(self.grid.children)
        to_remove = child_count - (self.max_rows * self.grid.cols)
        if to_remove > 0:
            for i in range(to_remove):
                widget = self.grid.children[-1]
                self.grid.remove_widget(widget)
                widget.clear_widgets()

            widget = self.grid.children[-1]
            self.page_cursor.go(widget.position)
            if self.cursor.pos < self.page_cursor.pos:
                self.cursor.go(self.grid.children[0].position)
        self.do_next_action()

    def _remove_lasts(self, dt):
        child_count = len(self.grid.children)
        to_remove = child_count - (self.max_rows * self.grid.cols)
        if to_remove > 0:
            for i in range(to_remove):
                widget = self.grid.children[0]
                self.grid.remove_widget(widget)
                widget.clear_widgets()

            widget = self.grid.children[-1]
            self.page_cursor.go(widget.position)
            if self.cursor.pos > self.grid.children[0].position:
                self.cursor.go(self.grid.children[-1].position)

        self.do_next_action()

    def _scroll_on_widget(self, dt):
        if self.widget_to_scroll is None:
            self._scroll_to_current()
        else:
            self.ids.scroll_view.scroll_to(self.widget_to_scroll)
        self.do_next_action()

    def _scroll_to_current(self):
        if self.selected_image is not None:
            self.ids.scroll_view.scroll_to(self.selected_image)
