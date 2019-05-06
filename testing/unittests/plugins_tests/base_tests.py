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
"""
Tests for plugins.base.
"""

import inspect
import os
import plugins
import plugin_runtime
import shutil
import time
import unittest
import xmlrunner
from plugin_runtime.base import PluginConfigChecker, PluginException

BASE_PATH = os.path.dirname(plugins.__file__)
RUNTIME_PATH = os.path.dirname(plugin_runtime.__file__)


class PluginControllerTest(unittest.TestCase):
    """ Tests for the PluginController. """

    @staticmethod
    def create_plugin(name, code):
        """ Create a plugin with a given name and the provided code. """
        path = '{0}/{1}'.format(BASE_PATH, name)
        os.makedirs(path)

        with open('{0}/main.py'.format(path), 'w') as code_file:
            code_file.write(code)

        with open('{0}/__init__.py'.format(path), 'w'):
            pass

    @staticmethod
    def destroy_plugin(name):
        """ Remove the code for a plugin created by create_plugin. """
        path = '{0}/{1}'.format(BASE_PATH, name)
        if os.path.exists(path):
            shutil.rmtree(path)

    def test_get_one_plugin(self):
        """ Test getting one plugin in the plugins package. """
        controller = None
        try:
            PluginControllerTest.create_plugin('P1', """
from plugins.base import *

class P1(OMPluginBase):
    name = 'P1'
    version = '1.0.0'
    interfaces = []
""")
            from plugins.base import PluginController

            controller = PluginController(None, None, RUNTIME_PATH)
            controller.start()
            plugin_list = controller.get_plugins()
            self.assertEquals(1, len(plugin_list))
            self.assertEquals('P1', plugin_list[0].name)
        finally:
            if controller is None:
                controller.stop()
            PluginControllerTest.destroy_plugin('P1')

    def test_get_two_plugins(self):
        """ Test getting two plugins in the plugins package. """
        controller = None
        try:
            PluginControllerTest.create_plugin('P1', """
from plugins.base import *

class P1(OMPluginBase):
    name = 'P1'
    version = '1.0.0'
    interfaces = []
""")

            PluginControllerTest.create_plugin('P2', """
from plugins.base import *

class P2(OMPluginBase):
    name = 'P2'
    version = '1.0.0'
    interfaces = []
""")

            from plugins.base import PluginController

            controller = PluginController(None, None, RUNTIME_PATH)
            controller.start()
            plugin_list = controller.get_plugins()
            self.assertEquals(2, len(plugin_list))
            names = sorted([plugin_list[0].name, plugin_list[1].name])
            self.assertEquals(['P1', 'P2'], names)
        finally:
            if controller is None:
                controller.stop()
            PluginControllerTest.destroy_plugin('P1')
            PluginControllerTest.destroy_plugin('P2')

    def test_get_special_methods(self):
        """ Test getting special methods on a plugin. """
        controller = None
        try:
            PluginControllerTest.create_plugin('P1', """
import time
from plugins.base import *

class P1(OMPluginBase):
    name = 'P1'
    version = '0.1.0'
    interfaces = [('webui', '1.0')]

    def __init__(self, webservice, logger):
        OMPluginBase.__init__(self, webservice, logger)
        self._bg_running = False
        self._input_data = None
        self._output_data = None

    @om_expose(auth=True)
    def html_index(self):
        return 'HTML'

    @om_expose(auth=False)
    def get_log(self):
        return {'bg_running': self._bg_running,
                'input_data': self._input_data,
                'output_data': self._output_data}

    @input_status
    def input(self, input_status_inst):
        self._input_data = input_status_inst

    @output_status
    def output(self, output_status_inst):
        self._output_data = output_status_inst

    @background_task
    def run(self):
        while True:
            self._bg_running = True
            time.sleep(1)
""")

            from plugins.base import PluginController

            controller = PluginController(None, None, RUNTIME_PATH)
            controller.start()

            response = controller._request('P1', 'html_index')
            self.assertEqual(response, 'HTML')

            controller.process_input_status({'input': 'INPUT',
                                             'output': 'OUTPUT'})
            controller.process_output_status('OUTPUT')

            start = time.time()
            while time.time() - start < 2:
                response = controller._request('P1', 'get_log')
                if response['input_data'] is not None and response['output_data'] is not None:
                    break
                time.sleep(0.1)
            self.assertEqual(response, {'bg_running': True,
                                        'input_data': ['INPUT', 'OUTPUT'],
                                        'output_data': 'OUTPUT'})
        finally:
            if controller is None:
                controller.stop()
            PluginControllerTest.destroy_plugin('P1')

    def test_check_plugin(self):
        """ Test the exception that can occur when checking a plugin. """
        from plugin_runtime.utils import check_plugin
        from plugin_runtime.base import OMPluginBase

        from plugins.base import PluginController
        PluginController(None, None)

        class P1(OMPluginBase):
            """ Plugin without name. """
            pass

        try:
            check_plugin(P1)
        except PluginException as exception:
            self.assertEquals('Attribute \'name\' is missing from the plugin class', str(exception))

        class P2(OMPluginBase):
            """ Plugin with malformed name. """
            name = 'malformed name'

        try:
            check_plugin(P2)
        except PluginException as exception:
            self.assertEquals('Plugin name \'malformed name\' is malformed: can only contain letters, numbers and underscores.', str(exception))

        class P3(OMPluginBase):
            """ Plugin without version. """
            name = 'test_name123'

        try:
            check_plugin(P3)
        except PluginException as exception:
            self.assertEquals('Attribute \'version\' is missing from the plugin class', str(exception))

        class P4(OMPluginBase):
            """ Plugin without interfaces. """
            name = 'test'
            version = '1.0.0'

        try:
            check_plugin(P4)
        except PluginException as exception:
            self.assertEquals('Attribute \'interfaces\' is missing from the plugin class', str(exception))

        class P5(OMPluginBase):
            """ Valid plugin. """
            name = 'test'
            version = '1.0.0'
            interfaces = []

        check_plugin(P5)

        class P6(OMPluginBase):
            """ Plugin that violates the webui interface. """
            name = 'test'
            version = '1.0.0'
            interfaces = [('webui', '1.0')]

        try:
            check_plugin(P6)
        except PluginException as exception:
            self.assertEquals('Plugin \'test\' has no method named \'html_index\'', str(exception))


FULL_DESCR = [
    {'name': 'hostname', 'type': 'str', 'description': 'The hostname of the server.'},
    {'name': 'port', 'type': 'int', 'description': 'Port on the server.'},
    {'name': 'use_auth', 'type': 'bool', 'description': 'Use authentication while connecting.'},
    {'name': 'password', 'type': 'password', 'description': 'Your secret password.'},
    {'name': 'enumtest', 'type': 'enum', 'description': 'Test for enum',
     'choices': ['First', 'Second']},
    {'name': 'outputs', 'type': 'section', 'repeat': True, 'min': 1,
     'content': [{'name': 'output', 'type': 'int'}]},
    {'name': 'network', 'type': 'nested_enum',
     'choices': [{'value': 'Facebook', 'content': [{'name': 'likes', 'type': 'int'}]},
                 {'value': 'Twitter', 'content': [{'name': 'followers', 'type': 'int'}]}]}
]


class PluginConfigCheckerTest(unittest.TestCase):
    """ Tests for the PluginConfigChecker. """

    def test_constructor(self):
        """ Test for the constructor. """
        _ = self
        PluginConfigChecker(FULL_DESCR)

    def test_constructor_error(self):
        """ Test with an invalid data type """
        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker({'test': 123})
        self.assertTrue('list' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'test': 123}])
        self.assertTrue('name' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 123}])
        self.assertTrue('name' in ctx.exception.message and 'string' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'test'}])
        self.assertTrue('type' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'test', 'type': 123}])
        self.assertTrue('type' in ctx.exception.message and 'string' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'test', 'type': 'something_else'}])
        self.assertTrue('type' in ctx.exception.message and 'something_else' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'test', 'type': 'str', 'description': []}])
        self.assertTrue('description' in ctx.exception.message and 'string' in ctx.exception.message)

    def test_constructor_str(self):
        """ Test for the constructor for str. """
        PluginConfigChecker([{'name': 'hostname', 'type': 'str', 'description': 'The hostname of the server.'}])
        PluginConfigChecker([{'name': 'hostname', 'type': 'str'}])

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'type': 'str'}])
        self.assertTrue('name' in ctx.exception.message)

    def test_constructor_int(self):
        """ Test for the constructor for int. """
        PluginConfigChecker([{'name': 'port', 'type': 'int', 'description': 'Port on the server.'}])
        PluginConfigChecker([{'name': 'port', 'type': 'int'}])

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'type': 'int'}])
        self.assertTrue('name' in ctx.exception.message)

    def test_constructor_bool(self):
        """ Test for the constructor for bool. """
        PluginConfigChecker([{'name': 'use_auth', 'type': 'bool', 'description': 'Use authentication while connecting.'}])
        PluginConfigChecker([{'name': 'use_auth', 'type': 'bool'}])

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'type': 'bool'}])
        self.assertTrue('name' in ctx.exception.message)

    def test_constructor_password(self):
        """ Test for the constructor for bool. """
        PluginConfigChecker([{'name': 'password', 'type': 'password', 'description': 'A password.'}])
        PluginConfigChecker([{'name': 'password', 'type': 'password'}])

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'type': 'password'}])
        self.assertTrue('name' in ctx.exception.message)

    def test_constructor_enum(self):
        """ Test for the constructor for enum. """
        PluginConfigChecker([{'name': 'enumtest', 'type': 'enum', 'description': 'Test for enum', 'choices': ['First', 'Second']}])
        PluginConfigChecker([{'name': 'enumtest', 'type': 'enum', 'choices': ['First', 'Second']}])

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'enumtest', 'type': 'enum', 'choices': 'First'}])
        self.assertTrue('choices' in ctx.exception.message and 'list' in ctx.exception.message)

    def test_constructor_section(self):
        """ Test for the constructor for section. """
        PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'repeat': True, 'min': 1, 'content': [{'name': 'output', 'type': 'int'}]}])
        PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'repeat': False, 'content': [{'name': 'output', 'type': 'int'}]}])
        PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'content': [{'name': 'output', 'type': 'int'}]}])

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'repeat': 'hello', 'content': [{'name': 'output', 'type': 'int'}]}])
        self.assertTrue('repeat' in ctx.exception.message and 'bool' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'min': 1, 'content': [{'name': 'output', 'type': 'int'}]}])
        self.assertTrue('min' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'content': 'error'}])
        self.assertTrue('content' in ctx.exception.message and 'list' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'content': [{'name': 123}]}])
        self.assertTrue('content' in ctx.exception.message and 'name' in ctx.exception.message and 'string' in ctx.exception.message)

    def test_constructor_nested_enum(self):
        """ Test for constructor for nested enum. """
        PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': [
            {'value': 'Facebook', 'content': [{'name': 'likes', 'type': 'int'}]},
            {'value': 'Twitter', 'content': [{'name': 'followers', 'type': 'int'}]}
        ]}])

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': 'test'}])
        self.assertTrue('choices' in ctx.exception.message and 'list' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': ['test']}])
        self.assertTrue('choices' in ctx.exception.message and 'dict' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': [{}]}])
        self.assertTrue('choices' in ctx.exception.message and 'value' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': [{'value': 123}]}])
        self.assertTrue('choices' in ctx.exception.message and 'network' in ctx.exception.message and 'content' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': [{'value': 'test'}]}])
        self.assertTrue('choices' in ctx.exception.message and 'content' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': [{'value': 'test', 'content': 'test'}]}])
        self.assertTrue('choices' in ctx.exception.message and 'content' in ctx.exception.message and 'list' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': [{'value': 'test', 'content': [{}]}]}])
        self.assertTrue('choices' in ctx.exception.message and 'content' in ctx.exception.message and 'name' in ctx.exception.message)

    def test_check_config_error(self):
        """ Test check_config with an invalid data type """
        checker = PluginConfigChecker([{'name': 'hostname', 'type': 'str'}])

        with self.assertRaises(PluginException) as ctx:
            checker.check_config('string')
        self.assertTrue('dict' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({})
        self.assertTrue('hostname' in ctx.exception.message)

    def test_check_config_str(self):
        """ Test check_config for str. """
        checker = PluginConfigChecker([{'name': 'hostname', 'type': 'str'}])
        checker.check_config({'hostname': 'cloud.openmotics.com'})

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'hostname': 123})
        self.assertTrue('str' in ctx.exception.message)

    def test_check_config_int(self):
        """ Test check_config for int. """
        checker = PluginConfigChecker([{'name': 'port', 'type': 'int'}])
        checker.check_config({'port': 123})

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'port': "123"})
        self.assertTrue('int' in ctx.exception.message)

    def test_check_config_bool(self):
        """ Test check_config for bool. """
        checker = PluginConfigChecker([{'name': 'use_auth', 'type': 'bool'}])
        checker.check_config({'use_auth': True})

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'use_auth': 234543})
        self.assertTrue('bool' in ctx.exception.message)

    def test_check_config_password(self):
        """ Test check_config for bool. """
        checker = PluginConfigChecker([{'name': 'password', 'type': 'password'}])
        checker.check_config({'password': 'test'})

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'password': 123})
        self.assertTrue('str' in ctx.exception.message)

    def test_check_config_section(self):
        """ Test check_config for section. """
        checker = PluginConfigChecker([{'name': 'outputs', 'type': 'section', 'repeat': True, 'min': 1, 'content': [{'name': 'output', 'type': 'int'}]}])

        checker.check_config({'outputs': []})
        checker.check_config({'outputs': [{'output': 2}]})
        checker.check_config({'outputs': [{'output': 2}, {'output': 4}]})

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'outputs': 'test'})
        self.assertTrue('list' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'outputs': [{'test': 123}]})
        self.assertTrue('section' in ctx.exception.message and 'output' in ctx.exception.message)

    def test_check_config_nested_enum(self):
        """ Test check_config for nested_enum. """
        checker = PluginConfigChecker([{'name': 'network', 'type': 'nested_enum', 'choices': [
            {'value': 'Facebook', 'content': [{'name': 'likes', 'type': 'int'}]},
            {'value': 'Twitter', 'content': [{'name': 'followers', 'type': 'int'}]}
        ]}])

        checker.check_config({'network': ['Twitter', {'followers': 3}]})
        checker.check_config({'network': ['Facebook', {'likes': 3}]})

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'network': 'test'})
        self.assertTrue('list' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'network': []})
        self.assertTrue('list' in ctx.exception.message and '2' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'network': ['something else', {}]})
        self.assertTrue('choices' in ctx.exception.message)

        with self.assertRaises(PluginException) as ctx:
            checker.check_config({'network': ['Twitter', {}]})
        self.assertTrue('nested_enum dict' in ctx.exception.message and 'followers' in ctx.exception.message)

    def test_simple(self):
        """ Test a simple valid configuration. """
        _ = self
        checker = PluginConfigChecker([
            {'name': 'log_inputs', 'type': 'bool', 'description': 'Log the input data.'},
            {'name': 'log_outputs', 'type': 'bool', 'description': 'Log the output data.'}
        ])
        checker.check_config({'log_inputs': True, 'log_outputs': False})

    def test_load_webinterface(self):
        """ Tests whether the webinterface.py parsing works as expected """
        from plugin_runtime import web
        from gateway.webservice import WebInterface
        found_calls = web._load_webinterface()

        ramaining_methods = found_calls.keys()
        for method_info in inspect.getmembers(WebInterface, predicate=lambda m: inspect.ismethod(m)):
            method = method_info[1]
            method_name = method.__name__
            call_info = found_calls.get(method_name)
            if not hasattr(method, 'plugin_exposed'):
                # Not an @openmotics_api call
                self.assertIsNone(call_info, 'An unexpected call was exposed to the plugins: {0}'.format(method_name))
                continue
            if method.plugin_exposed is False or method.deprecated is True:
                self.assertIsNone(call_info, 'An unexpected call was exposed to the plugins: {0}'.format(method_name))
                continue
            self.assertIsNotNone(call_info, 'Expected call was not exposed to plugins: {0}'.format(method_name))
            arg_spec = inspect.getargspec(method)
            self.assertEquals(arg_spec.args[0], 'self')
            self.assertEquals(arg_spec.args[1:], call_info)
            ramaining_methods.remove(method_name)
        self.assertEqual(ramaining_methods, [])


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
