import inspect
import re

from plugin_runtime.base import PluginException, OMPluginBase
from plugin_runtime.interfaces import check_interfaces


def get_plugin_class(package_name):
    """ Get the plugin class using the name of the plugin package. """
    plugin = __import__(package_name, globals(), locals(), ['main'])
    plugin_classes = {}

    if not hasattr(plugin, 'main'):
        raise PluginException('Module main was not found in plugin {0}'.format(package_name))

    for _, obj in inspect.getmembers(plugin.main):
        if not inspect.isclass(obj):
            continue
        mro = inspect.getmro(obj)
        if len(mro) < 3 or OMPluginBase.__name__ not in str(mro[-2]):
            continue
        plugin_classes[mro] = obj

    if not plugin_classes:
        raise PluginException('No children of OMPluginBase class found in {0}.main'.format(package_name))
    if len(plugin_classes) == 1:
        mro, plugin_class = plugin_classes.popitem()
        return plugin_class
    # In this case, we have deeper inheritance. We take the most specific one.
    # Note that we only support inheritance in one direct path (no branching).
    max_path = max(len(mro) for mro in plugin_classes)
    for depth in range(2, max_path):
        paths = {mro[-depth - 1:] for mro in plugin_classes if len(mro) > depth}
        if len(paths) != 1:
            raise PluginException('Found multiple children of OMPluginBase class of same generation in {0}.main'.format(package_name))
    return plugin_classes[paths.pop()]


def check_plugin(plugin_class):
    """
    Check if the plugin class has name, version and interfaces attributes.
    Raises PluginException when the attributes are not present.
    """
    if not hasattr(plugin_class, 'name'):
        raise PluginException('Attribute \'name\' is missing from the plugin class')

    # Check if valid plugin name
    if not re.match(r'^[a-zA-Z0-9_]+$', plugin_class.name):
        raise PluginException('Plugin name \'{0}\' is malformed: can only contain letters, numbers and underscores.'.format(plugin_class.name))

    if not hasattr(plugin_class, 'version'):
        raise PluginException('Attribute \'version\' is missing from the plugin class')

    # Check if valid version (a.b.c)
    if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+$', plugin_class.version):
        raise PluginException('Plugin version \'{0}\' is malformed: expected \'a.b.c\' where a, b and c are numbers.'.format(plugin_class.version))

    if not hasattr(plugin_class, 'interfaces'):
        raise PluginException('Attribute \'interfaces\' is missing from the plugin class')

    check_interfaces(plugin_class)


def get_special_methods(plugin_object, method_attribute):
    """ Get all methods of a plugin object that have the given attribute. """
    def __check(member):
        """ Check if a member is a method and has the given attribute. """
        return inspect.ismethod(member) and hasattr(member, method_attribute)
    return [m[1] for m in inspect.getmembers(plugin_object, predicate=__check)]
