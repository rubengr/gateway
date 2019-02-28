# Copyright (C) 2019 OpenMotics BVBA
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
""""
The thermostats_test.py file contains thermostat configuration test.
"""
import unittest
import time
import urllib
import logging
import simplejson as json
from toolbox import exception_handler

LOGGER = logging.getLogger('openmotics')


class ThermostatsTest(unittest.TestCase):
    """
    The ThermostatsTest is a test case for thermostats.
    """
    webinterface = None
    tools = None
    token = ''
    TESTEE_POWER = 8
    NIGHT_TEMP_INIT, DAY_BLOCK1_INIT, DAY_BLOCK2_INIT = 10.0, 10.5, 11.0  # X in X0.0 represent day number.

    @classmethod
    def setUpClass(cls):
        if not cls.tools.healthy_status:
            raise unittest.SkipTest('The Testee is showing an unhealthy status. All tests are skipped.')
        cls.token = cls.tools.get_new_token('openmotics', '123456')

    def setUp(self):
        self.tools.configure_thermostat(0, self.NIGHT_TEMP_INIT, self.DAY_BLOCK1_INIT, self.DAY_BLOCK2_INIT)  # Configuring thermostat 0
        self.token = self.tools.get_new_token('openmotics', '123456')
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools.assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: %s due to discovery failure.', self.id())
                self.skipTest('Failed to discover modules.')
        LOGGER.info('Running: %s', self.id())

    def tearDown(self):
        self.tools.unconfigure_thermostat(0)  # Unconfiguring thermostat 0 after finishing

    @exception_handler
    def test_thermostat_config_after_reset(self):
        """ Testing whether or not the thermostat configuration will be kept after resetting and power cycle. """
        sensor_config = {'id': 31, 'name': 'v_sensor', 'virtual': True, 'room': 255}
        url_params = urllib.urlencode({'config': json.dumps(sensor_config)})
        self.tools.api_testee('set_sensor_configuration?{0}'.format(url_params), self.token, expected_failure=False)

        sensor_31_config = {'sensor_id': 31, 'temperature': 1, 'humidity': None, 'brightness': None}
        url_params = urllib.urlencode(sensor_31_config)
        self.tools.api_testee('set_virtual_sensor?{0}'.format(url_params), self.token, expected_failure=False)

        thermostat_auto_config = {'thermostat_on': True, 'automatic': True, 'setpoint': 0, 'cooling_mode': False,
                                  'cooling_on': True}
        url_params = urllib.urlencode(thermostat_auto_config)
        self.tools.api_testee('set_thermostat_mode?{0}'.format(url_params), self.token, expected_failure=False)

        setpoint_config = {'thermostat': 0, 'temperature': 9}
        url_params = urllib.urlencode(setpoint_config)
        self.tools.api_testee('set_current_setpoint?{0}'.format(url_params), self.token, expected_failure=False)

        response_json = self.tools.api_testee('get_thermostat_status', self.token, expected_failure=False)

        self.assertTrue(response_json.get('automatic', False) is True and response_json.get('setpoint', 99) == 0 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set. Got: {0}".format(response_json))

        response_json = self.tools.api_testee('reset_master', self.token, expected_failure=False)
        self.assertTrue(response_json.get('status', 'Failed') == 'OK', "Should successfully reset the master. Got: {0}".format(response_json))

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools.get_new_token('openmotics', '123456')
            response_json = self.tools.api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)

        self.assertTrue(response_json.get('automatic', False) is True and response_json.get('setpoint', 99) == 0 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set after resetting the master. Got: {0}".format(response_json))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools.get_new_token('openmotics', '123456')
            response_json = self.tools.api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)
        self.assertTrue(response_json.get('automatic', False) is True and response_json.get('setpoint', 99) == 0 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set after a full power cycle. Got: {0}".format(response_json))

        # Testing the mode persistence after reset

        thermostat_auto_config = {'thermostat_on': True, 'automatic': False, 'setpoint': 5, 'cooling_mode': False, 'cooling_on': True}
        url_params = urllib.urlencode(thermostat_auto_config)
        self.tools.api_testee('set_thermostat_mode?{0}'.format(url_params), new_token, expected_failure=False)

        response_json = self.tools.api_testee('get_thermostat_status', new_token, expected_failure=False)

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config. Got: {0}".format(response_json))

        self.tools.api_testee('reset_master', new_token, expected_failure=False)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools.get_new_token('openmotics', '123456')
            response_json = self.tools.api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config after resetting the master. Got: {0}".format(response_json))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools.get_new_token('openmotics', '123456')
            response_json = self.tools.api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config after a full power cycle. Got: {0}".format(response_json))

        setpoint_config = {'thermostat': 0, 'temperature': 9}
        url_params = urllib.urlencode(setpoint_config)
        self.tools.api_testee('set_current_setpoint?{0}'.format(url_params), self.token, expected_failure=False)

        self.tools.api_testee('reset_master', new_token, expected_failure=False)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools.get_new_token('openmotics', '123456')
            response_json = self.tools.api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat configuration with the new settings after resetting the master. Got: {0}".format(response_json))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools.get_new_token('openmotics', '123456')
            response_json = self.tools.api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat configuration with the new settings after a full power cycle. Got: {0}".format(response_json))
