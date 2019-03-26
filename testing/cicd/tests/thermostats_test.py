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
import subprocess
import os
import unittest
import time
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
        if not cls.tools.initialisation_success:
            raise unittest.SkipTest('Unable to initialise the Testee. All tests are skipped.')

    def setUp(self):
        self.tools.configure_thermostat(0, self.NIGHT_TEMP_INIT, self.DAY_BLOCK1_INIT, self.DAY_BLOCK2_INIT)  # Configuring thermostat 0
        self.token = self.tools.get_new_token(self.tools.username, self.tools.password)
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools.assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: %s due to discovery failure.', self.id())
                self.skipTest('Failed to discover modules.')
        LOGGER.info('Running: %s', self.id())
        os.system(self.tools.SSH_LOGGER_COMMAND.format(self.tools.testee_ip, self.id()))

    def tearDown(self):
        self.tools.unconfigure_thermostat(0)  # Unconfiguring thermostat 0 after finishing

    @exception_handler
    def test_thermostat_config_after_reset(self):
        """ Testing whether or not the thermostat configuration will be kept after resetting and power cycle. """
        sensor_config = {'id': 31, 'name': 'v_sensor', 'virtual': True, 'room': 255}
        params = {'config': json.dumps(sensor_config)}
        self.tools.api_testee(api='set_sensor_configuration', params=params, token=self.token, expected_failure=False)

        sensor_31_config = {'sensor_id': 31, 'temperature': 1, 'humidity': 1, 'brightness': 1}
        self.tools.api_testee(api='set_virtual_sensor', params=sensor_31_config, token=self.token, expected_failure=False)

        thermostat_auto_config = {'thermostat_on': True, 'automatic': True, 'setpoint': 0, 'cooling_mode': False, 'cooling_on': True}
        self.tools.api_testee(api='set_thermostat_mode', params=thermostat_auto_config, token=self.token, expected_failure=False)

        setpoint_config = {'thermostat': 0, 'temperature': 9}
        self.tools.api_testee(api='set_current_setpoint', params=setpoint_config, token=self.token, expected_failure=False)

        response_dict = self.tools.api_testee(api='get_thermostat_status', token=self.token, expected_failure=False)

        self.assertTrue(response_dict.get('automatic', False) is True and response_dict.get('setpoint', 99) == 0 and response_dict.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set. Got: {0}".format(response_dict))

        response_dict = self.tools.api_testee(api='reset_master', token=self.token, expected_failure=False)
        self.assertTrue(response_dict.get('status', 'Failed') == 'OK', "Should successfully reset the master. Got: {0}".format(response_dict))

        response_dict = self._get_new_thermostat_status(timeout=120)

        self.assertTrue(response_dict.get('automatic', False) is True and response_dict.get('setpoint', 99) == 0 and response_dict.get('status')[0].get('csetp') == 9,
                        "Should return a thermostat status according to the thermostat auto config that has been set after resetting the master. Got: {0}".format(response_dict))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        response_dict = self._get_new_thermostat_status(timeout=120)
        self.assertTrue(response_dict.get('automatic', False) is True and response_dict.get('setpoint', 99) == 0 and response_dict.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set after a full power cycle. Got: {0}".format(response_dict))

        # Testing the mode persistence after reset

        thermostat_auto_config = {'thermostat_on': True, 'automatic': False, 'setpoint': 5, 'cooling_mode': False, 'cooling_on': True}
        new_token = self.tools._get_new_token(self.tools.username, self.tools.password)['token']
        self.tools.api_testee(api='set_thermostat_mode', params=thermostat_auto_config, token=new_token, expected_failure=False)

        response_dict = self.tools.api_testee(api='get_thermostat_status', token=new_token, expected_failure=False)

        self.assertTrue(response_dict.get('automatic', True) is False and response_dict.get('setpoint', 99) == 5 and response_dict.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config. Got: {0}".format(response_dict))

        self.tools.api_testee(api='reset_master', token=new_token, expected_failure=False)

        response_dict = self._get_new_thermostat_status(timeout=120)

        self.assertTrue(response_dict.get('automatic', True) is False and response_dict.get('setpoint', 99) == 5 and response_dict.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config after resetting the master. Got: {0}".format(response_dict))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        response_dict = self._get_new_thermostat_status(timeout=120)

        self.assertTrue(response_dict.get('automatic', True) is False and response_dict.get('setpoint', 99) == 5 and response_dict.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config after a full power cycle. Got: {0}".format(response_dict))

        setpoint_config = {'thermostat': 0, 'temperature': 9}
        self.tools.api_testee(api='set_current_setpoint', params=setpoint_config, token=self.token, expected_failure=False)

        self.tools.api_testee(api='reset_master', token=new_token, expected_failure=False)

        response_dict = self._get_new_thermostat_status(timeout=120)

        self.assertTrue(response_dict.get('automatic', True) is False and response_dict.get('setpoint', 99) == 5 and response_dict.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat configuration with the new settings after resetting the master. Got: {0}".format(response_dict))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        response_dict = self._get_new_thermostat_status(timeout=120)

        self.assertTrue(response_dict.get('automatic', True) is False and response_dict.get('setpoint', 99) == 5 and response_dict.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat configuration with the new settings after a full power cycle. Got: {0}".format(response_dict))

    def _get_new_thermostat_status(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            new_token = self.tools.get_new_token(self.tools.username, self.tools.password)
            response_dict = self.tools.api_testee(api='get_thermostat_status', token=new_token, expected_failure=True)
            if response_dict != "invalid_token":
                if response_dict.get('success') is False:
                    time.sleep(0.3)
                elif response_dict.get('success') is True:
                    return response_dict
            else:
                time.sleep(0.3)
