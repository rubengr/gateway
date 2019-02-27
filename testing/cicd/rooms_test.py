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
The rooms_test.py file contains room configuration test methods and other private methods that the tests will use.
"""
import unittest
import urllib
import logging
from random import randint
import simplejson as json
from toolbox import exception_handler


LOGGER = logging.getLogger('openmotics')


class RoomsTest(unittest.TestCase):
    """
    The RoomsTest is a test case for room configuration.
    """
    webinterface = None
    tools = None
    token = ''
    FLOOR_NUMBER = 3
    INPUT_COUNT = 8
    ROOM_NUMBER = 5

    @classmethod
    def setUpClass(cls):
        if not cls.tools.healthy_status:
            raise unittest.SkipTest('The Testee is showing an unhealthy status. All tests are skipped.')
        cls.token = cls.tools.get_new_token('openmotics', '123456')

    def setUp(self):
        self.token = self.tools.get_new_token('openmotics', '123456')
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools.assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: %s due to discovery failure.', self.id())
                self.skipTest('Failed to discover modules.')
        LOGGER.info('Running: %s', self.id())

    @exception_handler
    def test_set_output_configurations_rooms_floors(self):
        """ Testing setting up outputs floor. """
        expected_to_be_inserted_config = self._set_room_floor_configuration(room_number=self.ROOM_NUMBER)
        token = self.tools.get_new_token('openmotics', '123456')
        response_json = self.tools.api_testee('get_output_configurations', token)
        response_config = response_json.get('config')
        self.assertEqual(response_config, expected_to_be_inserted_config,
                         'Expected the output configuration to be updated. Got: {0} {1}'.format(response_config,
                                                                                                expected_to_be_inserted_config))

    @exception_handler
    def test_set_room_configurations(self):
        """ Testing setting up rooms. """
        config = []
        for i in xrange(100):
            one_room_config = {'id': i, 'name': 'room{0}'.format(self.ROOM_NUMBER), 'floor': self.FLOOR_NUMBER}
            config.append(one_room_config)

        url_params = urllib.urlencode({'config': json.dumps(config)})
        self.tools.api_testee('set_room_configurations?{0}'.format(url_params), self.token)

        response_json = self.tools.api_testee('get_room_configurations', self.token)
        self.assertEqual(response_json.get('config'), config)

    @exception_handler
    def test_set_room_configurations_authorization(self):
        """ Testing setting up rooms auth validation. """
        response_json = self.tools.api_testee('set_room_configurations', 'some_token', expected_failure=True)
        self.assertEqual(response_json, 'invalid_token',
                         'Should not be able to call set_room_configurations API without a valid token. Got: {0}'.format(
                             response_json))

        response_json = self.tools.api_testee('get_room_configurations', 'some_token', expected_failure=True)
        self.assertEqual(response_json, 'invalid_token',
                         'Should not be able to call get_room_configurations API without a valid token. Got: {0}'.format(
                             response_json))

    @exception_handler
    def test_set_room_configuration(self):
        """ Testing setting up one room. """
        i = randint(0, 99)
        one_room_config = {'id': i, 'name': 'room' + str(i), 'floor': self.FLOOR_NUMBER}
        url_params = urllib.urlencode({'config': json.dumps(one_room_config)})
        self.tools.api_testee('set_room_configuration?{0}'.format(url_params), self.token)

        url_params = urllib.urlencode({'id': i})
        response_json = self.tools.api_testee('get_room_configuration?{0}'.format(url_params), self.token)
        self.assertEqual(response_json.get('config'), one_room_config)

    @exception_handler
    def test_set_room_configuration_authorization(self):
        """ Testing setting up one room auth validation. """
        response_json = self.tools.api_testee('set_room_configuration', 'some_token', expected_failure=True)
        self.assertEqual(response_json, 'invalid_token',
                         'Should not be able to call set_room_configuration API without a valid token. Got: {0}'.format(
                             response_json))

        response_json = self.tools.api_testee('get_room_configuration', 'some_token', expected_failure=True)
        self.assertEqual(response_json, 'invalid_token',
                         'Should not be able to call get_room_configuration API without a valid token. Got: {0}'.format(
                             response_json))

    @exception_handler
    def test_set_all_lights_off(self):
        """ Testing turning all lights off. """
        url_params = urllib.urlencode({'floor': self.FLOOR_NUMBER})
        self.tools.api_testee('set_all_lights_floor_on?{0}'.format(url_params), self.token)

        self.tools.api_testee('set_all_lights_off', self.token)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(i, 0),
                            'Untoggled outputs must show input releases. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_set_all_lights_off_force_checked(self):
        """ Testing turning all lights off auth validation. """
        response_json = self.tools.api_testee('set_all_lights_off', 'some_token', expected_failure=True)
        self.assertEqual(response_json, 'invalid_token',
                         'Should not be able to call set_all_lights_off API without a valid token. Got: {0}'.format(
                             response_json))

        url_params = urllib.urlencode({'floor': 'floor_number'})
        response_json = self.tools.api_testee('set_all_lights_floor_off?{0}'.format(url_params), self.token,
                                              expected_failure=True)
        self.assertEqual(response_json, 'invalid_parameters',
                         'Should not be able to call set_all_lights_floor_off API without a valid parameter type. Got:{0}'.format(
                             response_json))

        url_params = urllib.urlencode({'floor': 600})
        response_json = self.tools.api_testee('set_all_lights_floor_off?{0}'.format(url_params), self.token,
                                              expected_failure=True)
        self.assertEqual(response_json.get('success'), False,
                         'Should not be able to call set_all_lights_floor_off API without a valid parameter value. Got: {0}'.format(
                             response_json))

    @exception_handler
    def test_set_all_lights_floor_off(self):
        """ Testing turning all lights off for a specific floor number. """
        self._set_room_floor_configuration(
            room_number=self.ROOM_NUMBER)  # Setting up configuration first. Room: 5, Floor 3

        url_params = urllib.urlencode({'floor': self.FLOOR_NUMBER})
        self.tools.api_testee('set_all_lights_floor_on?{0}'.format(url_params), self.token)

        url_params = urllib.urlencode({'floor': self.FLOOR_NUMBER})
        self.tools.api_testee('set_all_lights_floor_off?{0}'.format(url_params), self.token)

        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(i, 0),
                            'Untoggled outputs must show input releases. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_set_all_lights_floor_authorization(self):
        """ Testing turning all lights off for a specific floor number auth validation. """
        response_json = self.tools.api_testee('set_all_lights_floor_off', 'some_token', expected_failure=True)
        self.assertEqual(response_json, 'invalid_token',
                         'Should not be able to call set_all_lights_floor_off API without a valid token. Got: {0}'.format(
                             response_json))

        response_json = self.tools.api_testee('set_all_lights_floor_on', 'some_token', expected_failure=True)
        self.assertEqual(response_json, 'invalid_token',
                         'Should not be able to call set_all_lights_floor_on API without a valid token. Got: {0}'.format(
                             response_json))

    @exception_handler
    def test_set_all_lights_floor_on(self):
        """ Testing turning all lights on for a specific floor number. """
        self._set_room_floor_configuration(
            room_number=self.ROOM_NUMBER)  # Setting up configuration first. Room: 5, Floor 3

        url_params = urllib.urlencode({'floor': self.FLOOR_NUMBER})
        self.tools.api_testee('set_all_lights_floor_off?{0}'.format(url_params), self.token)

        url_params = urllib.urlencode({'floor': 'floor_number'})
        response_json = self.tools.api_testee('set_all_lights_floor_on?{0}'.format(url_params), self.token,
                                              expected_failure=True)
        self.assertEqual(response_json, 'invalid_parameters',
                         'Should not be able to call set_all_lights_floor_on API without a valid parameter type. Got: {0}'.format(
                             response_json))

        url_params = urllib.urlencode({'floor': 600})
        response_json = self.tools.api_testee('set_all_lights_floor_on?{0}'.format(url_params), self.token,
                                              expected_failure=True)
        self.assertEqual(response_json.get('success'), False,
                         'Should not be able to call set_all_lights_floor_on API without a valid parameter value. Got: {0}'.format(
                             response_json))

        url_params = urllib.urlencode({'floor': self.FLOOR_NUMBER})
        self.tools.api_testee('set_all_lights_floor_on?{0}'.format(url_params), self.token)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(i, 1),
                            'Toggled outputs must show input presses on the Tester. Got: {0}'.format(
                                self.tools.input_status))

    def _set_room_floor_configuration(self, room_number):
        """ Setting room floor and room configurations: Used to eliminate dependencies between tests. """
        expected_to_be_inserted_config = []
        for i in xrange(self.INPUT_COUNT):
            config = {'room': room_number, 'can_led_4_function': 'UNKNOWN', 'floor': 3, 'can_led_1_id': 255,
                      'can_led_1_function': 'UNKNOWN',
                      'timer': 65535, 'can_led_4_id': 255, 'can_led_3_id': 255, 'can_led_2_function': 'UNKNOWN',
                      'id': i, 'module_type': 'O',
                      'can_led_3_function': 'UNKNOWN', 'type': 255, 'can_led_2_id': 255, 'name': 'Out' + str(i)}
            expected_to_be_inserted_config.append(config)
        url_params = urllib.urlencode({'config': json.dumps(expected_to_be_inserted_config)})
        token = self.tools.get_new_token('openmotics', '123456')
        self.tools.api_testee('set_output_configurations?{0}'.format(url_params), token)
        return expected_to_be_inserted_config
