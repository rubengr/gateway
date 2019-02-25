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
The io_test contains tests related to input and output configurations.
"""
import unittest
import time
import datetime
import urllib
import simplejson as json
import logging
import toolbox
from pytz import timezone
from toolbox import exception_handler
from random import randint

LOGGER = logging.getLogger('openmotics')


class IoTest(unittest.TestCase):
    webinterface = None
    tools = None
    token = ''
    TESTEE_POWER = 8
    ROOM_NUMBER = 5
    INPUT_COUNT = 8

    @classmethod
    def setUpClass(cls):
        if not cls.tools.healthy_status:
            raise unittest.SkipTest('The Testee is showing an unhealthy status. All tests are skipped.')
        cls.token = cls.tools._get_new_token('openmotics', '123456')

    def setUp(self):
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools._assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                self.skipTest('Failed to discover modules.')
        LOGGER.info('Running: {}'.format(self.id()))

    @exception_handler
    def test_toggle_all_outputs_testee(self):
        """ Testing toggling on all outputs on the Testee. """
        config = self.tools._api_testee('get_output_configurations', self.token).get('config', [])
        self.assertTrue(bool(config), 'Should not be empty and should have the output configurations of the testee. But got {0}'.format(config))
        for one in config:
            self.tools.clicker_releaser(one['id'], self.token, True)
            result = self._check_if_event_is_captured(one['id'], 1)
            self.assertTrue(result, 'Should confirm that the Tester\'s input saw a press. Got: {0}'.format(result))

            self.tools.clicker_releaser(one['id'], self.token, False)
            result = self._check_if_event_is_captured(one['id'], 0)
            self.assertTrue(result, 'Should confirm that the Tester\'s input saw a release. Got: {0}'.format(result))

    @exception_handler
    def test_set_input_configuration(self):
        """ Testing configuring and linking inputs to outputs; action: output_id. """
        initial_config = []
        for input_number in xrange(self.INPUT_COUNT):
            config = {'name': 'input'+str(input_number), 'basic_actions': '', 'invert': 255, 'module_type': 'I', 'can': '',
                      'action': input_number, 'id': input_number, 'room': self.ROOM_NUMBER}
            initial_config.append(config)
            url_params = urllib.urlencode({'config': json.dumps(config)})
            self.tools._api_testee('set_input_configuration?{0}'.format(url_params), self.token)
        response_json = self.tools._api_testee('get_input_configurations', self.token)
        response_config = response_json.get('config')
        self.assertEquals(response_config, initial_config, 'If the link is established, both configs should be the same')

    @exception_handler
    def test_discovery(self):
        """ Testing discovery mode. """
        self.tools._api_testee('module_discover_start', self.token)
        time.sleep(0.3)
        response_json = self.tools._api_testee('module_discover_status', self.token)
        self.assertEquals(response_json.get('running'), True, 'Should be true to indicate discovery mode has started.')

        self.tools.human_click(toolbox.DISCOVER_TESTEE_OUTPUT_ID, True, self.webinterface)
        self.tools.human_click(toolbox.DISCOVER_TESTEE_INPUT_ID, True, self.webinterface)

        self.tools._api_testee('module_discover_stop', self.token)
        response_json = self.tools._api_testee('module_discover_status', self.token)
        self.assertEquals(response_json.get('running'), False, 'Should be true to indicate discovery mode has stopped.')

        response_json = self.tools._api_testee('get_modules', self.token)
        if response_json is None:
            self.tools.discovery_success = False
        if len(response_json.get('outputs', [])) != 1 or len(response_json.get('inputs', [])) != 1:
            self.tools.discovery_success = False

        self.assertTrue(len(response_json.get('outputs', [])) == 1, 'Should be true to indicate that the testee has only 1 output module.')
        self.assertTrue(len(response_json.get('inputs', [])) == 1, 'Should be true to indicate that the testee has only 1 input module.')

    @exception_handler
    def test_discovery_authorization(self):
        """ Testing discovery mode auth verification. """
        response_json = self.tools._api_testee('module_discover_start', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        response_json = self.tools._api_testee('module_discover_status', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        response_json = self.tools._api_testee('module_discover_stop', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

    @unittest.skip('Currently factory reset is not working properly')
    @exception_handler
    def test_factory_reset_and_reconfigure_use_case(self):
        """ Testing factory reset and reconfiguring Testee. """
        if self.tools._api_testee('factory_reset', self.token) is not None:
            self.tools.enter_testee_autorized_mode(self.webinterface, 6)
            url_params = urllib.urlencode({'username': 'openmotics', 'password': '123456'})
            self.tools._api_testee('create_user?{0}'.format(url_params))
            self.tools.exit_testee_autorized_mode(self.webinterface)
            url_params = urllib.urlencode({'username': 'openmotics', 'password': '123456', 'accept_terms': True})
            self.token = self.tools._api_testee('login?{0}'.format(url_params)).get('token', False)
            self.assertIsNot(self.token, False)
            self.assertTrue(bool(self.token), ' Should not have an empty token or None.')
        health = self.tools._api_testee('health_check').get('health', {})
        for one in health.values():
            self.assertEquals(one.get('state'), True)
        time.sleep(10)
        self.test_discovery()
        self.test_set_input_configuration()
        self.test_output_stress_toggling()

    @exception_handler
    def test_output_stress_toggling(self):
        """ Testing stress toggling all outputs on the Testee. """
        response_json = self.tools._api_testee('get_output_configurations', self.token)
        config = response_json.get('config')
        self.assertTrue(bool(config), 'Should not be empty and should have the output configurations of the testee. Got: {0}'.format(config))
        for one in config:
            for _ in xrange(30):
                self.tools.clicker_releaser(one['id'], self.token, True)
                self.assertTrue(self._check_if_event_is_captured(one['id'], 1), 'Toggled output must show input press. Got: {0}'.format(self.tools.input_status))

                self.tools.clicker_releaser(one['id'], self.token, False)
                self.assertTrue(self._check_if_event_is_captured(one['id'], 0), 'Untoggled output must show input release. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_output_stress_toggling_authorization(self):
        """ Testing stress toggling all outputs on the Testee auth verification. """
        response_json = self.tools._api_testee('get_output_configuration', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        response_json = self.tools._api_testee('get_output_configurations', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        url_params = urllib.urlencode({'id': 3, 'is_on': True})
        response_json = self.tools._api_testee('set_output?{0}'.format(url_params), 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

    @exception_handler
    def test_get_version(self):
        """ Testing getting the firmware and gateway versions. """
        response_json = self.tools._api_testee('get_version', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        response_json = self.tools._api_testee('get_version', self.token)
        self.assertTrue(response_json.get('gateway') is not None, 'Should be true and have the gateway\'s version.')
        self.assertTrue(response_json.get('version') is not None, 'SShould be true and have the firmware version.')

    @exception_handler
    def test_get_modules(self):
        """ Testing getting the list of modules. """
        response_json = self.tools._api_testee('get_modules', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        response_json = self.tools._api_testee('get_modules', self.token)
        self.assertTrue(len(response_json.get('outputs', [])) == 1, 'Should be true to indicate that the testee has only 1 output module.')
        self.assertTrue(len(response_json.get('inputs', [])) == 1, 'Should be true to indicate that the testee has only 1 input module.')

    @exception_handler
    def test_validate_master_status(self):
        """ Testing master's timezone. """
        response_json = self.tools._api_testee('get_timezone', self.token)
        self.assertEquals(response_json.get('timezone'), 'UTC', 'Expected default timezone on the gateway to be UTC but got {0}'.format(response_json))

        now = datetime.datetime.utcnow()
        response_json = self.tools._api_testee('get_status', self.token)
        self.assertEquals(response_json.get('time'), now.strftime('%H:%M'))

        url_params = urllib.urlencode({'timezone': 'America/Bahia'})
        self.tools._api_testee('set_timezone?{0}'.format(url_params), self.token)

        response_json = self.tools._api_testee('get_timezone', self.token)
        self.assertNotEquals(response_json.get('timezone'), 'UTC', 'Timezone on the gateway should be updated')
        self.assertEquals(response_json.get('timezone'), 'America/Bahia')

        bahia_timezone = timezone('America/Bahia')
        now = datetime.datetime.now(bahia_timezone)
        response_json = self.tools._api_testee('get_status', self.token)
        self.assertEquals(response_json.get('time'), now.strftime('%H:%M'))

        url_params = urllib.urlencode({'timezone': 'UTC'})
        self.tools._api_testee('set_timezone?{0}'.format(url_params), self.token)

        response_json = self.tools._api_testee('get_timezone', self.token)
        self.assertEquals(response_json.get('timezone'), 'UTC', 'Timezone on the gateway should be UTC again.')
        self.assertNotEquals(response_json.get('timezone'), 'America/Bahia', 'Timezone on the gateway should be back to normal.')

        now = datetime.datetime.utcnow()
        response_json = self.tools._api_testee('get_status', self.token)
        self.assertEquals(response_json.get('time'), now.strftime('%H:%M'))

    @exception_handler
    def test_validate_master_status_authorization(self):
        """ Testing master's timezone. """
        response_json = self.tools._api_testee('get_timezone', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        response_json = self.tools._api_testee('set_timezone', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

        response_json = self.tools._api_testee('get_status', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

    @exception_handler
    def test_get_features(self):
        """ Testing whether or not the API call does return the features list. """
        response_json = self.tools._api_testee('get_features', self.token)
        self.assertTrue(bool(response_json.get('features')), 'Should have the list of features after the API call. Got: {0}'.format(response_json))

    @exception_handler
    def test_get_features_authorization(self):
        """ Testing whether or not the API call does return the features list. """
        response_json = self.tools._api_testee('get_features', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token')

    @unittest.skip('can\'t truly validate. Visual validation required')
    @exception_handler
    def test_indicate(self):
        """ Testing API call to indicate LEDs. Only verifying the API currently. """
        response_json = self.tools._api_testee('indicate', self.token)
        self.assertEquals(response_json.get('success'), True, 'Should return true to indicate a successful indicate API call.')

    @exception_handler
    def test_indicate_authorization(self):
        """ Testing API call to indicate LEDs. Only verifying the API currently. """
        response_json = self.tools._api_testee('indicate', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token', 'The indicate API call should return \'invalid_token\' when called with an invalid token.')

    @exception_handler
    def test_open_maintenance(self):
        """ Testing API call to open maintenance and get the port. """
        response_json = self.tools._api_testee('open_maintenance', self.token)
        self.assertTrue(bool(response_json.get('port')), 'The open_maintenance API call should return the port of the maintenance socket.')

    @exception_handler
    def test_open_maintenance_authorization(self):
        """ Testing API call to open maintenance and get the port. """
        response_json = self.tools._api_testee('open_maintenance', 'some_token', expected_failure=True)
        self.assertEquals(response_json, 'invalid_token', 'The open_maintenance API call should return \'invalid_token\' when called with an invalid token.')

    def test_how_healthy_after_reboot(self):
        """ Testing how healthy the services are after power cycle. """
        response_json = json.loads(self.webinterface.get_output_status())
        status_list = response_json.get('status', [])
        self.assertTrue(bool(status_list), 'Should contain the list of output statuses. Got: {0}'.format(status_list))
        if status_list[8].get('status') == 0:
            json.loads(self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True))
        else:
            json.loads(self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False))
            time.sleep(0.5)
            json.loads(self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True))

        response_json = self.tools._api_testee('health_check')

        if response_json is None:
            self.tools.healthy_status = False
            self.fail('Failed to report health check. Service openmotics might have crashed. Please run \'supervisorctl restart openmotics\' or see logs for more details.')

        self.assertIsNotNone(response_json, 'Should not be none and should have the response back from the API call. Got: {0}'.format(response_json))
        self.assertTrue(response_json.get('health_version') > 0, 'Should have a health_version int to indicate the health check API version.')

        health = response_json.get('health', None)
        self.assertIsNotNone(health, 'Should not be none and should have health dict object. Got: {0}'.format(health))
        for one in health.values():
            if one.get('state') is False:
                self.tools.healthy_status = False
                self.fail('Service {0} is showing an unhealthy status. Current health status: {1}'.format(one, health))
        url_params = urllib.urlencode({'username': 'openmotics', 'password': '123456', 'accept_terms': True})
        self.tools.token = self.tools._api_testee('login?{0}'.format(url_params)).get('token')

    @exception_handler
    def test_set_output_configuration(self):
        output_configurations = []
        for i in xrange(8):
            one_output_configuration = {"room": 5,
                                        "can_led_4_function": "UNKNOWN",
                                        "floor": 3,
                                        "can_led_1_id": 255,
                                        "can_led_1_function": "UNKNOWN",
                                        "timer": 65535,
                                        "can_led_4_id": 255,
                                        "can_led_3_id": 255,
                                        "can_led_2_function": "UNKNOWN",
                                        "id": i,
                                        "module_type": "O",
                                        "can_led_3_function": "UNKNOWN",
                                        "type": 255,  # configured as light
                                        "can_led_2_id": 255,
                                        "name": "Out{0}".format(i)
                                        }

            output_configurations.append(one_output_configuration)
        url_params = urllib.urlencode({'config': json.dumps(output_configurations)})
        response_json = self.tools._api_testee('set_output_configuration?{0}'.format(url_params), self.token)
        self.assertTrue(response_json.get('success'), 'Should set the output configuration and return success: True. Got: {0}'.format(response_json))

    @exception_handler
    def test_get_output_status(self):

        output_number = randint(0, 7)
        token = self.tools._get_new_token('openmotics', '123456')
        output_statuses = self.tools._api_testee('get_output_status', token).get('status')
        self.assertTrue(output_statuses[output_number].get('status') == 0, 'Should be off by default. Got: {0}'.format(output_statuses))

        self.tools.clicker_releaser(output_number, token, True)
        self.assertTrue(self._check_if_event_is_captured(output_number, 1), 'Toggled output must show input press. Got: {0}'.format(self.tools.input_status))

        output_statuses = self.tools._api_testee('get_output_status', token).get('status')
        self.assertTrue(output_statuses[output_number].get('status') == 1, 'Should be off by default. Got: {0}'.format(output_statuses))

        self.tools.clicker_releaser(output_number, token, False)
        self.assertTrue(self._check_if_event_is_captured(output_number, 0), 'Untoggled output must show input release. Got: {0}'.format(self.tools.input_status))

        output_statuses = self.tools._api_testee('get_output_status', token).get('status')
        self.assertTrue(output_statuses[output_number].get('status') == 0, 'Should be off by default. Got: {0}'.format(output_statuses))

    def _check_if_event_is_captured(self, toggled_output, value):
        """
        Checks if the toggled output has turned an input on.
        :param toggled_output: the id of the toggled output
        :type toggled_output: int

        :param value: the expected is_on value of the input.
        :type value: int

        :return: if the the toggled output has turned an input on
        :rtype: bool
        """
        start = time.time()
        while self.tools.input_status.get(str(toggled_output)) is not str(value):
            if time.time() - start < self.tools.TIMEOUT:
                time.sleep(0.3)
            else:
                return False
        return True
