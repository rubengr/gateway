import simplejson as json

from plugins.base import om_expose, OMPluginBase


class BlankPlugin(OMPluginBase):
    name = "blankplugin"
    version = '1.0.0'
    interfaces = [('config', '1.0')]

    config_description = [{}]

    default_config = {}

    def __init__(self, webinterface, logger):
        super(BlankPlugin, self).__init__(webinterface, logger)
        self.logger('I am installed!')

    @om_expose
    def get_config_description(self):
        return json.dumps(BlankPlugin.config_description)

    @om_expose
    def get_config(self):
        return json.dumps(self._config)

    @om_expose
    def set_config(self, config):
        config = json.loads(config)
        config = self.convert(config)
        self._config_checker.check_config(config)
        self._config = config
        self._read_config()
        self.write_config(config)
        return json.dumps({'success': True})