import os
import kivy
import yaml
from cobiv.modules.entity import Entity
from cobiv.modules.hud import Hud
from cobiv.modules.view import View
from kivy.app import App
from MainContainer import MainContainer
from kivy.lang import Builder
from yapsy.PluginManager import PluginManager

kivy.require('1.9.1')

Builder.load_file('main.kv')


class Cobiv(App):
    root = None

    def __init__(self, **kwargs):
        super(Cobiv, self).__init__(**kwargs)
        self.plugin_manager = PluginManager()
        self.plugin_manager.setPluginPlaces(["modules"])
        self.plugin_manager.setCategoriesFilter({
            "View": View,
            "Entity": Entity,
            "Hud": Hud
        })

        self.plugin_manager.locatePlugins()
        self.plugin_manager.loadPlugins()

        config_path=os.path.join(os.path.expanduser('~'),'.cobiv')
        if not os.path.exists(config_path):
            os.makedirs(config_path)

    def build_yaml_config(self):
        if not os.path.exists('cobiv.yml'):
            f=open('cobiv.yml', 'w')
            data=self.root.build_yaml_main_config()
            for plugin in self.plugin_manager.getAllPlugins():
                plugin.plugin_object.build_yaml_config(data)
            yaml.dump(data,f)
            f.close()
        f=open('cobiv.yml')
        config=yaml.safe_load(f)
        f.close()
        self.root.configuration=config
        self.root.read_yaml_main_config(config)
        for plugin in self.plugin_manager.getAllPlugins():
            plugin.plugin_object.read_yaml_config(config)

    def build(self):
        self.root = MainContainer()

        for plugin in self.plugin_manager.getPluginsOfCategory("View"):
            self.root.available_views[plugin.plugin_object.get_name()] = plugin.plugin_object

        self.build_yaml_config()

        for plugin in self.plugin_manager.getAllPlugins():
            plugin.plugin_object.ready()
            print("plugin ready : "+str(plugin.plugin_object))

        self.root.switch_view("browser")

        self.root.ready()




        return self.root

    def on_stop(self):
        for plugin in self.plugin_manager.getAllPlugins():
            plugin.plugin_object.on_application_quit()

    def lookup(self, name, category):
        return self.plugin_manager.getPluginByName(name, category=category).plugin_object

    def get_user_path(self,*args):
        return os.path.join(os.path.expanduser('~'),'.cobiv',*args)

    def get_config_value(self,key,default=None):
        keys=key.split('.')
        cfg=self.root.configuration
        for k in keys:
            if cfg.has_key(k):
                cfg=cfg.get(k)
            else:
                return default
        return cfg

if __name__ == '__main__':
    Cobiv().run()
