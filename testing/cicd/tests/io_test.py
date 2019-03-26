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
"""
The io_test.py file contains tests related to input and output configurations.
"""
import os
import unittest
import time
import datetime
import simplejson as json
import logging
import toolbox
from pytz import timezone
from toolbox import exception_handler
from random import randint

LOGGER = logging.getLogger('openmotics')


class IoTest(unittest.TestCase):
    """
    The IoTest is a test case for input and output configurations.
    """
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
        if not cls.tools.initialisation_success:
            raise unittest.SkipTest('Unable to initialise the Testee. All tests are skipped.')

    def setUp(self):
        self.token = self.tools.get_new_token(self.tools.username, self.tools.password)
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools.assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: %s due to discovery failure.', self.id())
                self.skipTest('Failed to discover modules.')
        LOGGER.info('Running: %s', self.id())
        os.system(self.tools.SSH_LOGGER_COMMAND.format(self.tools.testee_ip, self.id()))

    @exception_handler
    def test_toggle_all_outputs_testee(self):
        """ Testing toggling on all outputs on the Testee. """
        config = self.tools.api_testee(api='get_output_configurations', token=self.token).get('config', [])
        self.assertTrue(bool(config),
                        'Should not be empty and should have the output configurations of the testee. But got {0}'.format(
                            config))
        for one in config:
            self.tools.clicker_releaser(one['id'], self.token, True)
            result = self.tools.check_if_event_is_captured(toggled_output=one['id'], value=1)
            self.assertTrue(result, 'Should confirm that the Tester\'s input saw a press. Got: {0}'.format(result))

            self.tools.clicker_releaser(one['id'], self.token, False)
            result = self.tools.check_if_event_is_captured(toggled_output=one['id'], value=0)
            self.assertTrue(result, 'Should confirm that the Tester\'s input saw a release. Got: {0}'.format(result))

    @exception_handler
    def test_set_input_configuration(self):
        """ Testing configuring and linking inputs to outputs; action: output_id. """
        initial_config = []
        for input_number in xrange(self.INPUT_COUNT):
            config = {'name': 'input' + str(input_number), 'basic_actions': '', 'invert': 255, 'module_type': 'I',
                      'can': '',
                      'action': input_number, 'id': input_number, 'room': self.ROOM_NUMBER}
            initial_config.append(config)
            params = {'config': json.dumps(config)}
            self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)
        response_dict = self.tools.api_testee(api='get_input_configurations', token=self.token)
        response_config = response_dict.get('config')
        self.assertEqual(response_config, initial_config, 'If the link is established, both configs should be the same')

    @exception_handler
    def test_discovery(self):
        """ Testing discovery mode. """
        self.tools.api_testee(api='module_discover_start', token=self.token)
        time.sleep(0.3)
        response_dict = self.tools.api_testee(api='module_discover_status', token=self.token)
        self.assertEqual(response_dict.get('running'), True, 'Should be true to indicate discovery mode has started.')

        self.tools.human_click(toolbox.DISCOVER_TESTEE_OUTPUT_ID, True, self.webinterface)
        self.tools.human_click(toolbox.DISCOVER_TESTEE_INPUT_ID, True, self.webinterface)

        self.tools.api_testee(api='module_discover_stop', token=self.token)
        response_dict = self.tools.api_testee(api='module_discover_status', token=self.token)
        self.assertEqual(response_dict.get('running'), False, 'Should be true to indicate discovery mode has stopped.')

        response_dict = self.tools.api_testee(api='get_modules', token=self.token)
        if response_dict is None:
            self.tools.discovery_success = False
        if len(response_dict.get('outputs', [])) != 1 or len(response_dict.get('inputs', [])) != 1:
            self.tools.discovery_success = False

        self.assertTrue(len(response_dict.get('outputs', [])) == 1,
                        'Should be true to indicate that the testee has only 1 output module.')
        self.assertTrue(len(response_dict.get('inputs', [])) == 1,
                        'Should be true to indicate that the testee has only 1 input module.')

    @exception_handler
    def test_discovery_authorization(self):
        """ Testing discovery mode auth verification. """
        response_dict = self.tools.api_testee(api='module_discover_start', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='module_discover_status', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='module_discover_stop', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

    @exception_handler
    def test_factory_reset_and_reconfigure_use_case(self):
        """ Testing factory reset and reconfiguring Testee. """
        if self.tools.api_testee(api='factory_reset', token=self.token) is not None:
            self.tools.enter_testee_autorized_mode(self.webinterface, 6)
            params = {'username': 'openmotics', 'password': '123456'}
            self.tools.api_testee(api='create_user', params=params)
            self.tools.exit_testee_autorized_mode(self.webinterface)
            params = {'username': 'openmotics', 'password': '123456', 'accept_terms': True}
            self.token = self.tools.api_testee(api='login', params=params).get('token', False)
            self.assertIsNot(self.token, False)
            self.assertTrue(bool(self.token), ' Should not have an empty token or None.')
        health = self.tools.api_testee(api='health_check').get('health', {})
        for one in health.values():
            self.assertEqual(one.get('state'), True)
        time.sleep(10)
        self.test_discovery()
        self.test_set_input_configuration()
        self.test_output_stress_toggling()

    @exception_handler
    def test_output_stress_toggling(self):
        """ Testing stress toggling all outputs on the Testee. """
        response_dict = self.tools.api_testee(api='get_output_configurations', token=self.token)
        config = response_dict.get('config')
        self.assertTrue(bool(config),
                        'Should not be empty and should have the output configurations of the testee. Got: {0}'.format(config))
        for one in config:
            for _ in xrange(30):
                self.tools.clicker_releaser(one['id'], self.token, True)
                self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=one['id'], value=1),
                                'Toggled output must show input press. Got: {0}'.format(self.tools.input_status))

                self.tools.clicker_releaser(one['id'], self.token, False)
                self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=one['id'], value=0),
                                'Untoggled output must show input release. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_output_stress_toggling_authorization(self):
        """ Testing stress toggling all outputs on the Testee auth verification. """
        response_dict = self.tools.api_testee(api='get_output_configuration', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='get_output_configurations', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        params = {'id': 3, 'is_on': True}
        response_dict = self.tools.api_testee(api='set_output', params=params, token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

    @exception_handler
    def test_get_version(self):
        """ Testing getting the firmware and gateway versions. """
        response_dict = self.tools.api_testee(api='get_version', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='get_version', token=self.token)
        self.assertTrue(response_dict.get('gateway') is not None, 'Should be true and have the gateway\'s version.')
        self.assertTrue(response_dict.get('version') is not None, 'SShould be true and have the firmware version.')

    @exception_handler
    def test_get_modules(self):
        """ Testing getting the list of modules. """
        response_dict = self.tools.api_testee(api='get_modules', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='get_modules', token=self.token)
        self.assertTrue(len(response_dict.get('outputs', [])) == 1,
                        'Should be true to indicate that the testee has only 1 output module.')
        self.assertTrue(len(response_dict.get('inputs', [])) == 1,
                        'Should be true to indicate that the testee has only 1 input module.')

    @exception_handler
    def test_validate_master_status(self):
        """ Testing master's timezone. """
        response_dict = self.tools.api_testee(api='get_timezone', token=self.token)
        self.assertEqual(response_dict.get('timezone'), 'UTC',
                         'Expected default timezone on the gateway to be UTC but got {0}'.format(response_dict))

        now = datetime.datetime.utcnow()
        response_dict = self.tools.api_testee(api='get_status', token=self.token)
        self.assertEqual(response_dict.get('time'), now.strftime('%H:%M'))

        params = {'timezone': 'America/Bahia'}
        self.tools.api_testee(api='set_timezone', params=params, token=self.token)

        response_dict = self.tools.api_testee(api='get_timezone', token=self.token)
        self.assertNotEqual(response_dict.get('timezone'), 'UTC', 'Timezone on the gateway should be updated')
        self.assertEqual(response_dict.get('timezone'), 'America/Bahia')

        bahia_timezone = timezone('America/Bahia')
        now = datetime.datetime.now(bahia_timezone)
        response_dict = self.tools.api_testee(api='get_status', token=self.token)
        self.assertEqual(response_dict.get('time'), now.strftime('%H:%M'))

        params = {'timezone': 'UTC'}
        self.tools.api_testee(api='set_timezone', params=params, token=self.token)

        response_dict = self.tools.api_testee(api='get_timezone', token=self.token)
        self.assertEqual(response_dict.get('timezone'), 'UTC', 'Timezone on the gateway should be UTC again.')
        self.assertNotEqual(response_dict.get('timezone'), 'America/Bahia', 'Timezone on the gateway should be back to normal.')

        now = datetime.datetime.utcnow()
        response_dict = self.tools.api_testee(api='get_status', token=self.token)
        self.assertEqual(response_dict.get('time'), now.strftime('%H:%M'))

    @exception_handler
    def test_validate_master_status_authorization(self):
        """ Testing master's timezone. """
        response_dict = self.tools.api_testee(api='get_timezone', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='set_timezone', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='get_status', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

    @exception_handler
    def test_get_features(self):
        """ Testing whether or not the API call does return the features list. """
        response_dict = self.tools.api_testee(api='get_features', token=self.token)
        self.assertTrue(bool(response_dict.get('features')),
                        'Should have the list of features after the API call. Got: {0}'.format(response_dict))

    @exception_handler
    def test_get_features_authorization(self):
        """ Testing whether or not the API call does return the features list. """
        response_dict = self.tools.api_testee(api='get_features', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

    @exception_handler
    def test_indicate_authorization(self):
        """ Testing API call to indicate LEDs. Only verifying the API currently. """
        response_dict = self.tools.api_testee(api='indicate', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token', 'The indicate API call should return \'invalid_token\' when called with an invalid token.')

    @exception_handler
    @unittest.skip('currently skipped, full maintenance mode related set will be introduced.')
    def test_open_maintenance(self):
        """ Testing API call to open maintenance and get the port. """
        response_dict = self.tools.api_testee(api='open_maintenance', token=self.token)
        self.assertTrue(bool(response_dict.get('port')), 'The open_maintenance API call should return the port of the maintenance socket.')

    @exception_handler
    def test_open_maintenance_authorization(self):
        """ Testing API call to open maintenance and get the port. """
        response_dict = self.tools.api_testee(api='open_maintenance', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token',
                         'The open_maintenance API call should return \'invalid_token\' when called with an invalid token.')

    def test_how_healthy_after_reboot(self):
        """ Testing how healthy the services are after power cycle. """
        response_dict = json.loads(self.webinterface.get_output_status())
        status_list = response_dict.get('status', [])
        self.assertTrue(bool(status_list), 'Should contain the list of output statuses. Got: {0}'.format(status_list))
        if status_list[8].get('status') == 0:
            self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)
        else:
            self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
            time.sleep(0.5)
            self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        response_dict = self.tools.api_testee(api='health_check')

        if response_dict is None:
            self.tools.healthy_status = False
            self.fail(
                'Failed to report health check. Service openmotics might have crashed. Please run \'supervisorctl restart openmotics\' or see logs for more details.')

        self.assertIsNotNone(response_dict,
                             'Should not be none and should have the response back from the API call. Got: {0}'.format(response_dict))
        self.assertTrue(response_dict.get('health_version') > 0,
                        'Should have a health_version int to indicate the health check API version.')

        health = response_dict.get('health', None)
        self.assertIsNotNone(health, 'Should not be none and should have health dict object. Got: {0}'.format(health))
        for one in health.values():
            if one.get('state') is False:
                self.tools.healthy_status = False
                self.fail('Service {0} is showing an unhealthy status. Current health status: {1}'.format(one, health))
        params = {'username': 'openmotics', 'password': '123456', 'accept_terms': True}
        self.tools.token = self.tools.api_testee(api='login', params=params).get('token')

    @exception_handler
    def test_set_output_configuration(self):
        """ Testing setting the output configuration """
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
                                        "name": "Out{0}".format(i)}

            output_configurations.append(one_output_configuration)
        params = {'config': json.dumps(output_configurations)}
        response_dict = self.tools.api_testee(api='set_output_configurations', params=params, token=self.token)
        self.assertTrue(response_dict.get('success'),
                        'Should set the output configuration and return success: True. Got: {0}'.format(response_dict))

        response_dict = self.tools.api_testee(api='get_output_configurations', token=self.token)
        self.assertEqual(output_configurations, response_dict.get('config'),
                         'The returned config should equal the configuration that has been set. Got: {0} vs {1}'.format(output_configurations, response_dict.get('config')))

    @exception_handler
    def test_get_output_status(self):
        """ Testing getting outputs status"""
        output_number = randint(0, 7)
        token = self.tools.get_new_token(self.tools.username, self.tools.password)
        output_statuses = self.tools.api_testee(api='get_output_status', token=token).get('status')

        if not output_statuses:
            self.fail('Unable to get output status.')
        self.assertTrue(output_statuses[output_number]['status'] == 0,
                        'Should be off by default. Got: {0}'.format(output_statuses))

        self.tools.clicker_releaser(output_number, token, True)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_number, value=1),
                        'Toggled output must show input press. Got: {0}'.format(self.tools.input_status))

        output_statuses = self.tools.api_testee(api='get_output_status', token=token).get('status')

        if not output_statuses:
            self.fail('Unable to get output status.')
        self.assertTrue(output_statuses[output_number]['status'] == 1,
                        'Should return status with value 1 after turning on the output.. Got: {0}'.format(output_statuses[output_number]))

        self.tools.clicker_releaser(output_number, token, False)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_number, value=0),
                        'Untoggled output must show input release. Got: {0}'.format(self.tools.input_status))

        output_statuses = self.tools.api_testee(api='get_output_status', token=token).get('status')

        if not output_statuses:
            self.fail('Unable to get output status.')
        self.assertTrue(output_statuses[output_number]['status'] == 0,
                        'Should be off by default. Got: {0}'.format(output_statuses))
