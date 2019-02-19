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
""" The OpenMotics plugin controller. """

import cherrypy
import inspect
import logging
import os
import pkgutil
import threading
import traceback
from datetime import datetime

try:
    import json
except ImportError:
    import simplejson as json

from plugins.runner import PluginRunner

LOGGER = logging.getLogger("openmotics")


class PluginController(object):
    """ The controller keeps track of all plugins in the system. """

    def __init__(self, webinterface, config_controller, runtime_path='/opt/openmotics/python/plugin_runtime'):
        self.__webinterface = webinterface
        self.__config_controller = config_controller
        self.__runtime_path = runtime_path

        self.__stopped = True
        self.__logs = {}
        # TODO: The plugins should not start when initializing the controller, but when start() is called
        self.__runners = self.__init_runners()

        self.__metrics_controller = None

    def start(self):
        """ Start the plugins and expose them via the webinterface. """
        if self.__stopped:
            for runner in self.__runners:
                self.__expose(runner)
        else:
            LOGGER.error('The PluginController is already running')

    def stop(self):
        for runner in self.__runners:
            runner.stop()
        self.__stopped = True

    def __expose(self, runner):
        """ Expose the runner using cherrypy. """
        root_config = {'tools.sessions.on': False,
                       'tools.cors.on': self.__config_controller.get_setting('cors_enabled', False)}

        cherrypy.tree.mount(runner.get_webservice(self.__webinterface),
                            '/plugins/{0}'.format(runner.name),
                            {'/': root_config})

    def set_metrics_controller(self, metrics_controller):
        """ Sets the metrics controller """
        self.__metrics_controller = metrics_controller

    def __init_runners(self):
        """ Scan the plugins package for installed plugins in the form of subpackages. """
        import plugins
        objects = pkgutil.iter_modules(plugins.__path__)  # (module_loader, name, ispkg)

        package_names = [o[1] for o in objects if o[2]]

        runners = []
        for package_name in package_names:
            try:
                logger = self.get_logger(package_name)
                plugin_path = os.path.join(PluginController.__get_plugin_root(), package_name)
                runner = PluginRunner(self.__runtime_path, plugin_path, logger)
                runner.start()
                runners.append(runner)
            except Exception as exception:
                self.log(package_name, 'Could not load plugin', exception)

        # Check for double plugins
        per_name = {}
        for runner in runners:
            if runner.name not in per_name:
                per_name[runner.name] = [runner]
            else:
                per_name[runner.name].append(runner)

        # Remove plugins that are defined in multiple packages
        filtered = []
        for name in per_name:
            if len(per_name[name]) != 1:
                self.log(name,
                         'Could not enable plugin',
                         'found in multiple pacakges: {0}'.format(', '.join(r.plugin_path for r in per_name[name])))
                for runner in per_name[name]:
                    runner.stop()
            else:
                filtered.append(per_name[name][0])

        return filtered

    @staticmethod
    def __get_plugin_root():
        import plugins
        return os.path.abspath(os.path.dirname(inspect.getfile(plugins)))

    def get_plugins(self):
        """ Get a list of all installed plugins. """
        return self.__runners

    def __get_plugin(self, name):
        """ Get a plugin by name, None if it the plugin is not installed. """
        for runner in self.__runners:
            if runner.name == name:
                return runner
        return None

    def install_plugin(self, md5, package_data):
        """ Install a new plugin. """
        from tempfile import mkdtemp
        from shutil import rmtree
        from subprocess import call
        import hashlib

        # Check if the md5 sum matches the provided md5 sum
        hasher = hashlib.md5()
        hasher.update(package_data)
        calculated_md5 = hasher.hexdigest()

        if calculated_md5 != md5:
            raise Exception('The provided md5sum ({0}) does not match the actual md5 of the package data ({1}).'.format(md5, calculated_md5))

        tmp_dir = mkdtemp()
        try:
            # Extract the package_data
            with open('{0}/package.tgz'.format(tmp_dir), "wb") as tgz:
                tgz.write(package_data)

            retcode = call('cd {0}; mkdir new_package; tar xzf package.tgz -C new_package/'.format(tmp_dir),
                           shell=True)
            if retcode != 0:
                raise Exception('The package data (tgz format) could not be extracted.')

            # Create an __init__.py file, if it does not exist
            init_path = '{0}/new_package/__init__.py'.format(tmp_dir)
            if not os.path.exists(init_path):
                with open(init_path, 'w'):
                    # Create an empty file
                    pass

            # Check if the package contains a valid plugin
            logger = self.get_logger('new_package')
            runner = PluginRunner(self.__runtime_path, '{0}/new_package'.format(tmp_dir), logger)
            runner.start()
            runner.stop()
            name, version = runner.name, runner.version

            def parse_version(version_string):
                """ Parse the version from a string "x.y.z" to a tuple(x, y, z). """
                return tuple([int(x) for x in version_string.split('.')])

            # Check if a newer version of the package is already installed
            installed_plugin = self.__get_plugin(name)
            if installed_plugin is not None:
                if parse_version(version) <= parse_version(installed_plugin.version):
                    raise Exception('A newer version of plugins {0} is already installed (current version = {1}, to installed = {2}).'.format(name, installed_plugin.version, version))
                else:
                    # Remove the old version of the plugin
                    # TODO: Stop the plugin if it's running
                    retcode = call('cd /opt/openmotics/python/plugins; rm -R {0}'.format(name),
                                   shell=True)
                    if retcode != 0:
                        raise Exception('The old version of the plugin could not be removed.')

            # Check if the package directory exists, this can only be the case if a previous
            # install failed or if the plugin has gone corrupt: remove it !
            plugin_path = '/opt/openmotics/python/plugins/{0}'.format(name)
            if os.path.exists(plugin_path):
                rmtree(plugin_path)

            # Install the package
            retcode = call('cd {0}; mv new_package {1}'.format(tmp_dir, plugin_path), shell=True)
            if retcode != 0:
                raise Exception('The package could not be installed.')

            # Initiate a reload of the OpenMotics daemon
            # TODO: Start the plugin's process
            PluginController.__exit()

            return {'msg': 'Plugin successfully installed'}

        finally:
            rmtree(tmp_dir)

    @staticmethod
    def __exit():
        """ Exit the cherrypy server after 1 second. Lets the current request terminate. """
        threading.Timer(1, lambda: os._exit(0)).start()

    def remove_plugin(self, name):
        """
        Remove a plugin, this removes the plugin package and configuration.
        It also calls the remove function on the plugin to cleanup other files written by the
        plugin.
        """
        from shutil import rmtree

        plugin = self.__get_plugin(name)

        # Check if the plugin in installed
        if plugin is None:
            raise Exception('Plugin \'{0}\' is not installed.'.format(name))

        # Execute the on_remove callbacks
        try:
            plugin.remove_callback()
        except Exception as exception:
            LOGGER.error('Exception while removing plugin \'{0}\': {1}'.format(name, exception))

        # Remove the plugin package
        plugin_path = '/opt/openmotics/python/plugins/{0}'.format(name)
        try:
            rmtree(plugin_path)
        except Exception as exception:
            raise Exception('Error while removing package for plugin \'{0}\': {1}'.format(name, exception))

        # Remove the plugin configuration
        conf_file = '/opt/openmotics/etc/pi_{0}.conf'.format(name)
        if os.path.exists(conf_file):
            os.remove(conf_file)

        # Initiate a reload of the OpenMotics daemon
        # TODO: Stop the plugin's process
        PluginController.__exit()

        return {'msg': 'Plugin successfully removed'}

    def process_input_status(self, data):
        """ Should be called when the input status changes, notifies all plugins. """
        for runner in self.__runners:
            runner.process_input_status((data['input'], data['output']))

    def process_output_status(self, output_status_inst):
        """ Should be called when the output status changes, notifies all plugins. """
        for runner in self.__runners:
            runner.process_output_status(output_status_inst)

    def process_shutter_status(self, shutter_status_inst):
        """ Should be called when the shutter status changes, notifies all plugins. """
        for runner in self.__runners:
            runner.process_shutter_status(shutter_status_inst)

    def process_event(self, code):
        """ Should be called when an event is triggered, notifies all plugins. """
        for runner in self.__runners:
            runner.process_event(code)

    def _request(self, name, method, args=None, kwargs=None):
        """ Allows to execute a programmatorical http request to the plugin """
        for runner in self.__runners:
            if runner.name == name:
                return runner.request(method, args=args, kwargs=kwargs)

    def collect_metrics(self):
        """ Collects all metrics from all plugins """
        for runner in self.__runners:
            for metric in runner.collect_metrics():
                if metric is None:
                    continue
                else:
                    yield metric

    def distribute_metric(self, metric):
        """ Enqueues all metrics in a separate queue per plugin """
        delivery_count = 0
        for runner in self.__runners:
            for receiver in runner.get_metric_receivers():
                try:
                    sources = self.__metrics_controller.get_filter('source', receiver['source'])
                    metric_types = self.__metrics_controller.get_filter('metric_type', receiver['metric_type'])
                    if metric['source'] in sources and metric['type'] in metric_types:
                        runner.distribute_metric(receiver['name'], metric)
                        delivery_count += 1
                except Exception as exception:
                    self.log(runner.name, 'Exception while distributing metrics', exception, traceback.format_exc())
        return delivery_count

    def get_metric_receivers(self):
        receivers = []
        for runner in self.__runners:
            receivers.extend(runner.get_metric_receivers())
        return receivers

    def get_metric_definitions(self):
        """ Loads all metric definitions of all plugins """
        definitions = {}

        for runner in self.__runners:
            definitions[runner.name] = runner.get_metric_definitions()

        return definitions

    def log(self, plugin, msg, exception, stacktrace=None):
        """ Append an exception to the log for the plugins. This log can be retrieved using get_logs. """
        if plugin not in self.__logs:
            self.__logs[plugin] = []

        LOGGER.error('Plugin {0}: {1} ({2})'.format(plugin, msg, exception))
        if stacktrace is None:
            self.__logs[plugin].append('{0} - {1}: {2}'.format(datetime.now(), msg, exception))
        else:
            self.__logs[plugin].append('{0} - {1}: {2}\n{3}'.format(datetime.now(), msg, exception, stacktrace))
        if len(self.__logs[plugin]) > 100:
            self.__logs[plugin].pop(0)

    def get_logger(self, plugin_name):
        """ Get a logger for a plugin. """
        if plugin_name not in self.__logs:
            self.__logs[plugin_name] = []

        def log(msg):
            """ Log function for the given plugin."""
            LOGGER.info('PLUGIN {0}: {1}'.format(plugin_name, msg))
            self.__logs[plugin_name].append('{0} - {1}'.format(datetime.now(), msg))
            if len(self.__logs[plugin_name]) > 100:
                self.__logs[plugin_name].pop(0)

        return log

    def get_logs(self):
        """ Get the logs for all plugins. Returns a dict where the keys are the plugin names and the value is a string. """
        return dict((plugin, '\n'.join(entries)) for plugin, entries in self.__logs.iteritems())
