import logging
import os

try:
    import ujson as json
except ImportError:
    # This is the case when the plugin runtime is unittested
    import json  # type: ignore

from decorators import *  # Import for backwards compatibility

logger = logging.getLogger("openmotics")


class PluginException(Exception):
    """ Exception that is raised when there are errors in a plugin implementation. """
    pass


class OMPluginBase(object):
    """
    Base class for an OpenMotics plugin. Every plugin package should contain a
    module with the name 'main' that contains a class that extends this class.
    """

    def __init__(self, webinterface, logger):
        """
        The web interface is provided to the plugin to interface with the OpenMotics system.

        :param webinterface: Reference the OpenMotics webinterface, this can be used to
        perform actions, fetch status data, etc.
        :param logger: Function that can be called with one parameter: message (String),
        the message will be appended to the plugin's log. This log can be fetched using
        the webinterface.
        """
        self.webinterface = webinterface
        self.logger = logger

    def __get_config_path(self):
        """ Get the path for the plugin configuration file based on the plugin name. """
        return '/opt/openmotics/etc/pi_{0}.conf'.format(self.__class__.name)

    def read_config(self, default_config=None):
        """ Read the configuration file for the plugin: the configuration file contains json
        string that will be converted to a python dict, if an error occurs, the default confi
        is returned. The PluginConfigChecker can be used to check if the configuration is valid,
        this has to be done explicitly in the Plugin class.
        """
        config_path = self.__get_config_path()

        if os.path.exists(config_path):
            config_file = open(config_path, 'r')
            config = config_file.read()
            config_file.close()

            try:
                return json.loads(config)
            except Exception as exception:
                logger.error('Exception while getting config for plugin \'{0}\': {1}'.format(self.__class__.name, exception))

        return default_config

    def write_config(self, config):
        """ Write the plugin configuration to the configuration file: the config is a python dict
        that will be serialized to a json string.
        """
        config_file = open(self.__get_config_path(), 'w')
        config_file.write(json.dumps(config))
        config_file.close()


class PluginConfigChecker(object):
    """
    The standard configuration controller for plugins enables the plugin creator to easily
    implement the 'config' plugin interface. By specifying a configuration description, the
    PluginConfigController is able to verify if a configuration dict matches this description.
    The description is a list of dicts, each dict contains the 'name', 'type' and optionally
    'description' and 'i18n' keys.

    These are the basic types: 'str', 'int', 'bool', 'password', these types don't have additional
    keys. For the 'enum' type the user specifies the possible values in a list of strings in the
    'choices' key.

    The complex types 'section' and 'nested_enum' allow the creation of lists and conditional
    elements.

    A 'nested_enum' allows the user to create a subsection of which the content depends on the
    choosen enum value. The 'choices' key should contain a list of dicts with two keys: 'value',
    the value of the enum and 'content', a configuration description like specified here.

    A 'section' allows the user to create a subsection or a list of subsections (when the 'repeat'
    key is present and true, a minimum number of subsections ('min' key) can be provided when
    'repeat' is true. The 'content' key should provide a configuration description like specified
    above.

    An example of a description:
    [
      {'name': 'hostname', 'type': 'str',      'description': 'The hostname of the server.', 'i18n': 'hostname'},
      {'name': 'port',     'type': 'int',      'description': 'Port on the server.',         'i18n': 'port'},
      {'name': 'use_auth', 'type': 'bool',     'description': 'Use authentication while connecting.'},
      {'name': 'password', 'type': 'password', 'description': 'Your secret password.' },
      {'name': 'enumtest', 'type': 'enum',     'description': 'Test for enum',
       'choices': ['First', 'Second']},

      {'name': 'outputs', 'type': 'section', 'repeat': True, 'min': 1,
       'content': [{'name': 'output', 'type': 'int'}]},

      {'name': 'network', 'type': 'nested_enum', 'choices': [
           {'value': 'Facebook', 'content': [{'name': 'likes', 'type': 'int'}]} ,
           {'value': 'Twitter', 'content': [{'name': 'followers', 'type': 'int'}]}
       ]}
    ]
    """

    MISSES_KEY = 'The configuration item \'{0}\' does not contain a \'{1}\' key.'
    KEY_INVALID_TYPE = 'The key \'{0}\' of configuration item \'{1}\' is not {2}.'
    UNKNOWN_TYPE = 'The configuration item \'{0}\' contains unknown type \'{1}\'.'
    CHOICES_INVALID_TYPE = 'An element of the \'choices\' list of configuration item \'{0}\' is not {1}.'
    CONFIG_INVALID_TYPE = 'Config \'{0}\': \'{1}\' is not {2}.'

    def __init__(self, description):
        """
        Creates a PluginConfigChecker using a description. If the description is not valid,
        a PluginException will be thrown.
        """
        self._check_description(description)
        self.__description = description

    def _check_description(self, description):
        """ Checks if a plugin configuration description is valid. """
        if not isinstance(description, list):
            raise PluginException('The configuration description is not a list')
        else:
            for item in description:
                for key, mandatory in [('name', True),
                                       ('type', True),
                                       ('description', False),
                                       ('i18n', False)]:
                    if mandatory is True and key not in item:
                        raise PluginException(PluginConfigChecker.MISSES_KEY.format(item, key))
                    if key in item and not isinstance(item[key], basestring):
                        raise PluginException(PluginConfigChecker.KEY_INVALID_TYPE.format(key, item, 'a string'))

                if item['type'] == 'enum':
                    PluginConfigChecker._check_enum(item)
                elif item['type'] == 'section':
                    self._check_section(item)
                elif item['type'] == 'nested_enum':
                    self._check_nested_enum(item)
                elif item['type'] not in ['str', 'int', 'bool', 'password']:
                    raise PluginException(PluginConfigChecker.UNKNOWN_TYPE.format(item, item['type']))

    @staticmethod
    def _check_enum(item):
        """ Check an enum configuration description. """
        if 'choices' not in item:
            raise PluginException(PluginConfigChecker.MISSES_KEY.format(item, 'choices'))
        if not isinstance(item['choices'], list):
            raise PluginException(PluginConfigChecker.KEY_INVALID_TYPE.format('choices', item, 'a list'))

        for choice in item['choices']:
            if not isinstance(choice, basestring):
                raise PluginException(PluginConfigChecker.CHOICES_INVALID_TYPE.format(item, 'a string'))

    def _check_section(self, item):
        """ Check an section configuration description. """
        if 'repeat' in item and not isinstance(item['repeat'], bool):
            raise PluginException(PluginConfigChecker.KEY_INVALID_TYPE.format('repeat', item, 'a bool'))

        if ('repeat' not in item or item['repeat'] is False) and 'min' in item:
            raise PluginException('The configuration item \'%s\' does contains a \'min\' key but is not repeatable.'.format(item))

        if 'min' in item and not isinstance(item['min'], int):
            raise PluginException(PluginConfigChecker.KEY_INVALID_TYPE.format('min', item, 'an int'))

        if 'content' not in item:
            raise PluginException(PluginConfigChecker.MISSES_KEY.format(item, 'content'))

        try:
            self._check_description(item['content'])
        except PluginException as exception:
            raise PluginException('Exception in \'content\': {0}'.format(exception))

    def _check_nested_enum(self, item):
        """ Check a nested enum configuration description. """
        if 'choices' not in item:
            raise PluginException(PluginConfigChecker.MISSES_KEY.format(item, 'choices'))
        if not isinstance(item['choices'], list):
            raise PluginException(PluginConfigChecker.KEY_INVALID_TYPE.format('choices', item, 'a list'))

        for choice in item['choices']:
            if not isinstance(choice, dict):
                raise PluginException(PluginConfigChecker.KEY_INVALID_TYPE.format('choices', item, 'a dict'))

            for key in ['value', 'content']:
                if key not in choice:
                    raise PluginException('The choices dict \'{0}\' of item \'{1}\' does not contain a \'{2}\' key.'.format(choice, item['name'], key))

            if not isinstance(choice['value'], str):
                raise PluginException('The \'value\' key of choices dict \'{0}\' of item \'{1}\' is not a string.'.format(choice, item['name']))

            try:
                self._check_description(choice['content'])
            except PluginException as exception:
                raise PluginException('Exception in \'choices\' - \'content\': {0}'.format(exception))

    def check_config(self, config):
        """
        Check if a config is valid for the description.
        Raises a PluginException if the config is not valid.
        """
        self._check_config(config, self.__description)

    def _check_config(self, config, description):
        """
        Check if a config is valid for this description.
        Raises a PluginException if the config is not valid.
        """
        if not isinstance(config, dict):
            raise PluginException('The config \'{0}\' is not a dict'.format(config))

        for item in description:
            name = item['name']
            if name not in config:
                raise PluginException('The config does not contain key \'{0}\'.'.format(name))

            for key, type_info in {'str': (basestring, 'a string'),
                                   'int': (int, 'an int'),
                                   'bool': (bool, 'a bool'),
                                   'password': (basestring, 'a string'),
                                   'section': (list, 'a list')}.iteritems():
                if item['type'] == key and not isinstance(config[name], type_info[0]):
                    raise PluginException(PluginConfigChecker.CONFIG_INVALID_TYPE.format(name, config[name], type_info[1]))

            if item['type'] == 'enum':
                if config[name] not in item['choices']:
                    raise PluginException('Config \'{0}\': \'{1}\' is not in the choices: {2}'.format(name, config[name], ', '.format(item['choices'])))
            elif item['type'] == 'section':
                for config_section in config[name]:
                    try:
                        self._check_config(config_section, item['content'])
                    except PluginException as exception:
                        raise PluginException('Exception in section list: {0}'.format(exception))
            elif item['type'] == 'nested_enum':
                if not isinstance(config[name], list) or len(config[name]) != 2:
                    raise PluginException('Config \'{0}\': \'{1}\' is not a list of length 2'.format(name, config[name]))

                choices = [choice['value'] for choice in item['choices']]
                try:
                    i = choices.index(config[name][0])
                    self._check_config(config[name][1], item['choices'][i]['content'])
                except PluginException as ex:
                    raise PluginException("Exception in nested_enum dict: %s" % ex)
                except ValueError:
                    raise PluginException('Config \'{0}\': \'{1}\' is not in the choices: {2}'.format(name, config[name], ', '.join(choices)))
