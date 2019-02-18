# Copyright (C) 2016 OpenMotics BVBA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
""" Contains the definition of the plugin interfaces. """

import inspect

from base import PluginException


class PluginInterface(object):
    """
    Definition of a plugin interface. Contains a name, version and a list
    of PluginMethods defined by the interface.
    """

    def __init__(self, name, version, methods):
        """
        Default constructor.

        :param name: Name of the interface
        :type name: str
        :param version: Version of the interface
        :type version: str
        :param methods: The methods defined by the interface
        :type methods: list of plugin_runtime.interfaces.PluginMethod
        """
        self.name = name
        self.version = version
        self.methods = methods


class PluginMethod(object):
    """
    Defines a method. Contains the name of the method, whether authentication
    is required for the method and the arguments for the method.
    """

    def __init__(self, name, auth, arguments):
        """
        Default constructor.

        :param name: Name of the method
        :type name: str
        :param auth: Whether authentication is required for the method
        :type auth: bool
        :param arguments: list of the names of the arguments
        :type arguments: list of str
        """
        self.name = name
        self.auth = auth
        self.arguments = arguments


INTERFACES = [
    PluginInterface('webui', '1.0', [
        PluginMethod('html_index', True, [])
    ]),
    PluginInterface('config', '1.0', [
        PluginMethod('get_config_description', True, []),
        PluginMethod('get_config', True, []),
        PluginMethod('set_config', True, ['config'])
    ]),
    PluginInterface('metrics', '1.0', [])
]


def get_interface(name, version):
    """ Get the PluginInterface with a given name and version, None if it doesn't exist. """
    for interface in INTERFACES:
        if name == interface.name and version == interface.version:
            return interface
    return None


def check_interface(plugin, interface):
    """
    Check if the methods defined by the interface are present on the plugin.

    :param plugin: The plugin to check.
    :type plugin: plugin_runtime.base.OMPluginBase
    :param interface: The plugin to check.
    :type interface: plugin_runtime.interfaces.PluginInterface
    :raises: PluginExcpetion if a method defined by the interface is not present.
    """
    plugin_name = plugin.name

    for method in interface.methods:
        plugin_method = getattr(plugin, method.name, None)

        if plugin_method is None or not callable(plugin_method):
            raise PluginException('Plugin \'{0}\' has no method named \'{0}\''.format(plugin_name, method.name))

        if not hasattr(plugin_method, 'om_expose'):
            raise PluginException('Plugin \'{0}\' does not expose method \'{1}\''.format(plugin_name, method.name))

        # noinspection PyUnresolvedReferences
        if plugin_method.om_expose['auth'] != method.auth:
            raise PluginException('Plugin \'{0}\': authentication for method \'{1}\' does not match the interface authentication ({2}required).'.format(
                plugin_name, method.name, '' if method.auth else 'not '
            ))

        # noinspection PyUnresolvedReferences
        argspec = inspect.getargspec(plugin_method.om_expose['method'])
        if len(argspec.args) == 0 or argspec.args[0] != "self":
            raise PluginException('Method \'{0}\' on plugin \'{1}\' lacks \'self\' as first argument.'.format(method.name, plugin_name))

        if argspec.args[1:] != method.arguments:
            raise PluginException('Plugin \'{0}\': the arguments for method \'{1}\': {2} do not match the interface arguments: {3}.'.format(
                plugin_name, method.name, argspec.args[1:], method.arguments
            ))


def check_interfaces(plugin):
    """
    Check the interfaces of a plugin. Raises a PluginException if there are problems
    with the interfaces on the plugin. Possible problems are: the interface was not found,
    the methods defined by the interface are not present.

    :param plugin: The plugin to check.
    :type plugin: plugin_runtime.base.OMPluginBase
    :raises: PluginException
    """
    if not isinstance(plugin.interfaces, list):
        raise PluginException('The interfaces attribute on plugin \'{0}\' is not a list.'.format(plugin.name))
    else:
        for i in plugin.interfaces:
            if not isinstance(i, tuple) or len(i) != 2:
                raise PluginException('Interface \'{0}\' on plugin \'{1}\' is not a tuple of (name, version).'.format(i, plugin.name))

            (name, version) = i
            interface = get_interface(name, version)
            if interface is None:
                raise PluginException('Interface \'{0}\' with version \'{1}\' was not found.'.format(name, version))
            else:
                check_interface(plugin, interface)


def has_interface(plugin, name, version):
    for interface in plugin.interfaces:
        interface_name, interface_version = interface
        if interface_name == name and interface_version == version:
            return True
    return False
