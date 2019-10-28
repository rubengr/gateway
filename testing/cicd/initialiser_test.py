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

# TODO: Cleanup, as this is a copy-paste from the old tester-plugin code

"""
The initialiser.py file contains a test that will also initliase the Testee.
"""
import time
import logging
import simplejson as json
import toolbox
from toolbox import exception_handler, OMTestCase


LOGGER = logging.getLogger('openmotics')


class InitialiserTest(OMTestCase):
    """
    The InitialiserTest will initialise the Testee.
    """
    FLOOR_NUMBER = 3
    OUTPUT_COUNT = INPUT_COUNT = 8
    ROOM_NUMBER = 5

    @exception_handler
    def test_testee_initialisation(self):
        """ Testing initialisation for the testee """
        self.tools.enter_testee_authorized_mode(self.webinterface)
        params = {'username': self.tools.username, 'password': self.tools.password}
        self.tools.api_testee(api='create_user', params=params)
        response_dict = self.tools.api_testee(api='get_usernames')
        if self.tools.username not in response_dict.get('usernames'):
            self.tools.initialisation_success = False
            self.fail('failed to initialise at user creation')
        self.tools.exit_testee_authorized_mode(self.webinterface)

        params = {'username': self.tools.username, 'password': self.tools.password, 'accept_terms': True}
        response_dict = self.tools.api_testee(api='login', params=params)

        valid_token = response_dict.get('token')
        if not valid_token:
            self.tools.initialisation_success = False
            self.fail('failed to initialise at login')

        response_dict = self.tools.api_testee(api='get_features', token=valid_token)

        if not response_dict.get('success'):
            self.tools.initialisation_success = False
            self.fail('failed to initialise at token validation')

        self.tools.api_testee(api='module_discover_start', token=valid_token)

        response_dict = self.tools.api_testee(api='module_discover_status', token=valid_token)
        self.assertEqual(response_dict.get('running'), True, 'Should be true to indicate discovery mode has started.')

        self.tools.human_click(toolbox.DISCOVER_TESTEE_OUTPUT_ID, True, self.webinterface)
        self.tools.human_click(toolbox.DISCOVER_TESTEE_INPUT_ID, True, self.webinterface)
        self.tools.human_click(toolbox.DISCOVER_TESTEE_DIMMER_ID, True, self.webinterface)
        self.tools.human_click(toolbox.DISCOVER_TESTEE_TEMPERATURE_ID, True, self.webinterface)
        self.tools.human_click(toolbox.DISCOVER_TESTEE_CAN_ID, True, self.webinterface)

        self.tools.api_testee(api='module_discover_stop', token=valid_token)

        response_dict = self.tools.api_testee(api='get_modules', token=valid_token)
        if response_dict is None:
            self.tools.discovery_success = False
            self.tools.initialisation_success = False
            self.fail('failed to initialise at getting modules')

        if not ('outputs' in response_dict and 'inputs' in response_dict):
            self.tools.discovery_success = False
            self.tools.initialisation_success = False
            self.fail('response was not none but not expected: {0}'.format(response_dict))

        self.assertEquals(sorted(response_dict['outputs']), ['D', 'O'])
        self.assertEquals(sorted(response_dict['inputs']), ['C', 'I', 'T'])

        for i in xrange(self.OUTPUT_COUNT):  # Configuring the 8 first outputs as lights
            config = {'room': self.ROOM_NUMBER,
                      'can_led_4_function': 'UNKNOWN',
                      'floor': self.FLOOR_NUMBER,
                      'can_led_1_id': 255,
                      'can_led_1_function': 'UNKNOWN',
                      'timer': 65535,
                      'can_led_4_id': 255,
                      'can_led_3_id': 255,
                      'can_led_2_function': 'UNKNOWN',
                      'id': i,
                      'module_type': 'O',
                      'can_led_3_function': 'UNKNOWN',
                      'type': 255,  # Light
                      'can_led_2_id': 255,
                      'name': 'Out{0}'.format(i)}

            params = {'config': json.dumps(config)}
            self.tools.api_testee(api='set_output_configuration', params=params, token=valid_token)

        for input_number in xrange(self.INPUT_COUNT):
            config = {'name': 'input' + str(input_number), 'basic_actions': '', 'invert': 255, 'module_type': 'I',
                      'can': '',
                      'action': input_number, 'id': input_number, 'room': self.ROOM_NUMBER}
            params = {'config': json.dumps(config)}
            self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        params = {'floor': self.FLOOR_NUMBER}
        self.tools.api_testee(api='set_all_lights_floor_on', params=params, token=self.token)
        time.sleep(0.5)
        self.tools.api_testee(api='set_all_lights_floor_off', params=params, token=self.token)

        for i in xrange(self.INPUT_COUNT):
            if not self.tools.check_if_event_is_captured(toggled_output=i, value=0):  # Making sure Testee's outputs are off
                self.fail('failed to initialise at turning off outputs.')
        self.tools.unconfigure_thermostat(0)
