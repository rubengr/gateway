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
The actions_test.py file contains tests related to action types and action numbers and other private methods
that the tests will use.
"""
import time
import logging
from random import randint
import simplejson as json
from toolbox import exception_handler, OMTestCase

logger = logging.getLogger('openmotics')


class ActionsTest(OMTestCase):
    """
    The ActionsTest is a test case for action types and action numbers.
    """
    TESTEE_POWER = 8
    ROOM_NUMBER = 5
    GROUP_ACTION_CONFIG = '240,0,244,{0},240,10,161,{0},235,5,160,{0},235,255,240,20,160,{0},235,5,161,{0},235,255,240,255'
    FLOOR_NUMBER = 3
    GROUP_ACTION_TARGET_ID = 0
    INPUT_COUNT = 8

    @exception_handler
    def test_do_group_action_on_off(self):
        """ Testing the execution of all configured group actions on the testee. """
        self._set_group_actions_config()
        response_dict = self.tools.api_testee(api='get_group_action_configurations', token=self.token)
        config = response_dict.get('config')
        self.assertIsNotNone(config, 'Should return the config of the group actions.')
        self.assertTrue(self.tools.is_not_empty(config), 'The config should not be empty when returned from get group action configurations API. Got: {0}'.format(response_dict))
        configured_actions = []
        for one in config:
            if one.get('actions', '') != '':
                configured_actions.append(one)

        for one in configured_actions:
            params = {'group_action_id': one.get('id')}
            self.tools.api_testee(api='do_group_action', params=params, token=self.token)
        pressed_inputs = json.loads(self.webinterface.get_last_inputs()).get('inputs')
        self.assertIsNotNone(pressed_inputs)
        self.assertTrue(pressed_inputs)

    @exception_handler
    def test_do_group_action_on_off_authorization(self):
        """ Testing do_group_action API auth verification. """
        response_dict = self.tools.api_testee(api='get_group_action_configurations', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token',
                         'Should not be able to return group action configurations without a valid token. Got: {0}'.format(response_dict))

        response_dict = self.tools.api_testee(api='get_output_status', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token',
                         'The get_group_action_configurations API call should return \'invalid_token\' when called with an invalid token. Got: {0}'.format(response_dict))

        invalid_group_action_id = 9999
        params = {'group_action_id': invalid_group_action_id}
        response_dict = self.tools.api_testee(api='do_group_action', params=params, token=self.token, expected_failure=True)
        self.assertEqual(response_dict.get('msg'),
                         'group_action_id not in [0, 160]: {0}'.format(invalid_group_action_id),
                         'Should return an error message when calling do group action API with an invalid group action ID. Got: {0}'.format(response_dict))

    @exception_handler
    def test_set_group_action_configuration(self):
        """ Testing the setting up of one group action. """
        i = randint(0, 159)
        one_group_action_config = {'id': i,
                                   'actions': self.GROUP_ACTION_CONFIG.format(0),
                                   'name': 'Test' + str(i)}
        params = {'config': json.dumps(one_group_action_config)}  # Will turn on output 0 if it's off and turn it back off, reverse if it's on already.

        self.tools.api_testee(api='set_group_action_configuration', params=params, token=self.token)

        params = {'id': i}
        response_dict = self.tools.api_testee(api='get_group_action_configuration', params=params, token=self.token)
        self.assertEqual(response_dict.get('config'), one_group_action_config,
                         'The new config should be the same as the present group action config. Got: returned: {0} configured: {1}'.format(response_dict.get('config'), one_group_action_config))

        params = {'group_action_id': i}
        self.tools.api_testee(api='do_group_action', params=params, token=self.token)

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=self.GROUP_ACTION_TARGET_ID, value=1),
                        'Should return true after calling do_group_action API. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=self.GROUP_ACTION_TARGET_ID, value=0),
                        'Should untoggled output 0 after a moment and must show input releases. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_set_group_action_configuration_authorization(self):
        """ Testing the setting up of one group action auth verification. """
        response_dict = self.tools.api_testee(api='set_group_action_configuration', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token',
                         'Should be True after setting the group action configuration. Got: {0}'.format(response_dict))

    @exception_handler
    def test_set_group_action_configurations(self):
        """ Testing the setting up of all configurable group actions ( all = 160 available group actions configurations ) """
        _, config = self._set_group_actions_config()

        response_dict = self.tools.api_testee(api='get_group_action_configurations', token=self.token)
        self.assertEqual(response_dict.get('config'), config)

    @exception_handler
    def test_set_group_action_configurations_authorization(self):
        """ Testing set_group_action_configurations auth verification """
        response_dict = self.tools.api_testee(api='set_group_action_configurations', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        response_dict = self.tools.api_testee(api='get_group_action_configurations', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

    @exception_handler
    def test_set_startup_action_configuration(self):
        """ Testing the setting up of the startup action configuration. """
        config = {"actions": self.GROUP_ACTION_CONFIG.format(0)}
        params = {'config': json.dumps(config)}

        self.tools.api_testee(api='set_startup_action_configuration', params=params, token=self.token)

        response_dict = self.tools.api_testee(api='get_startup_action_configuration', token=self.token)
        self.assertEqual(response_dict.get('config'), config, 'The new config should be the same as the present startup action config. Got{0}'.format(response_dict))

        response_dict = json.loads(self.webinterface.get_output_status())

        status_list = response_dict.get('status', [])
        self.assertTrue(self.tools.is_not_empty(status_list), 'Should contain the list of output statuses. Got: {0}'.format(status_list))
        if status_list[8].get('status') == 0:
            self.webinterface.set_output_status(id=self.TESTEE_POWER, is_on=True)
        else:
            self.webinterface.set_output_status(id=self.TESTEE_POWER, is_on=False)
            time.sleep(0.5)
            self.webinterface.set_output_status(id=self.TESTEE_POWER, is_on=True)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=self.GROUP_ACTION_TARGET_ID, value=1), 'Should execute startup action and turn output 0 on, Tester\'s input will see a press')

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=self.GROUP_ACTION_TARGET_ID, value=0), 'Should execute startup action and turn output 0 off, Tester\'s input will see a press')

        self.tools.token = self.token = self.tools.get_new_token(self.tools.username, self.tools.password)
        self.tools.configure_thermostat(thermostat_number=0, night_temp=10, day_block1_temp=10.5, day_block2_temp=11)

    @exception_handler
    def test_set_startup_action_configuration_authorization(self):
        """ Testing the setting up of the startup action configuration. """
        response_dict = self.tools.api_testee(api='set_startup_action_configuration', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

    @exception_handler
    def test_do_basic_action(self):
        """ Testing if do basic action API call and execution works. """
        action_number = randint(0, 7)
        params = {'action_type': 165, 'action_number': action_number}  # ActionType 165 turns on an output.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=action_number, value=1),
                        'Should have toggled the tester\'s input. Got {0}, expected output ID to toggle: {1}'.format(self.tools.input_status, action_number))

        params = {'action_type': 160, 'action_number': action_number}  # ActionType 160 turns off an output.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=action_number, value=0),
                        'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(self.tools.input_status, action_number))
        self.tools.api_testee(api='get_output_status', token=self.token)

    @exception_handler
    def test_do_basic_action_authorization(self):
        """ Testing do basic action API auth verification. """
        response_dict = self.tools.api_testee(api='do_basic_action', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

        params = {'action_type': 165, 'action_number': 46}
        response_dict = self.tools.api_testee(api='do_basic_action', params=params, token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token')

    @exception_handler
    def test_motion_sensor_timer_short(self):
        """ Testing the setting up of a virtual motion sensor and validating the timer setting ( short = 2m30s ) """
        input_number = randint(0, 7)

        self._set_input_advanced_configuration('MotionS', input_number, 195)

        self.webinterface.set_output_status(id=input_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_number, is_on=False)  # Sensor stops detecting movement

        time.sleep(0.3)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=1), 'Should turn on an input on the Tester that act as a motion sensor.')

        result = self.tools.check_if_event_is_captured(toggled_output=input_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_number))
        total_pressed_duration = self.tools.input_record.get(str(input_number))["0"] - self.tools.input_record.get(str(input_number))["1"]
        self.assertTrue(152 > total_pressed_duration > 148, 'Should toggle off after around 2m30s. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_get_input_configuration_authorization(self):
        """ Testing if getting input configurations works without a valid authorization. """
        params = {'id': 3}

        response_dict = self.tools.api_testee(api='get_input_configuration', params=params, token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token', 'Expecting the response to be invalid_token. Got: {0}'.format(response_dict))

        response_dict = self.tools.api_testee(api='get_input_configurations', token='some_token', expected_failure=True)
        self.assertEqual(response_dict, 'invalid_token', 'Expecting the response to be invalid_token. Got: {0}'.format(response_dict))

    @exception_handler
    def test_execute_group_action(self):
        """ Testing the execution of a group action that toggles output 0. """
        self._set_group_actions_config()

        input_number = randint(0, 7)
        group_action_number = randint(0, 159)
        config = {'name': 'input_ex',
                  'basic_actions': '2,{0}'.format(group_action_number),
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': input_number,
                  'room': 255}
        params = {'config': json.dumps(config)}
        token = self.tools.get_new_token(self.tools.username, self.tools.password)
        self.tools.api_testee(api='set_input_configuration', params=params, token=token)
        self.webinterface.set_output_status(id=input_number, is_on=True)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=0, value=1), 'Should execute a group action to toggle on output 0.')

        self.webinterface.set_output_status(id=input_number, is_on=False)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=0, value=0), 'Should execute a group action to toggle off output 0 after a while.')

    @exception_handler
    def test_toggles_output(self):
        """ Testing toggling one output. """
        self._set_default_output_config()
        time.sleep(0.3)
        output_to_toggle = randint(0, 7)

        self._set_input_advanced_configuration('togglINP', output_to_toggle, 162)

        self.webinterface.set_output_status(id=output_to_toggle,
                                            is_on=True)  # Toggling the Tester's output, The Testee's input will see a press that executes an action that toggles an output, to confirm the output toggling, we can check the Tester's input module (all modules are cross configured).
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=1),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=output_to_toggle, is_on=False)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=1),
                        'The Tester\'s input module should keep seeing a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=output_to_toggle,
                                            is_on=True)  # Toggling the Tester's output, The Testee's input will see a press that executes an action that toggles an output, to confirm the output toggling, we can check the Tester's input module (all modules are cross configured).
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=0),
                        'The Tester\'s input module should see a release after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=output_to_toggle, is_on=False)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=0),
                        'The Tester\'s input module should keep seeing a release after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_turn_output_on_off(self):
        """ Testing turning one output on and off. """
        self._set_default_output_config()
        time.sleep(0.3)
        output_to_toggle = randint(0, 7)

        self._set_input_advanced_configuration('onoffINP', output_to_toggle, 161)

        self.webinterface.set_output_status(id=output_to_toggle, is_on=True)
        # Toggling the Tester's output, The Testee's input will see a press that executes an action that toggles an output, to confirm the output toggling, we can check the Tester's input module (all modules are cross configured).
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=1),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=output_to_toggle, is_on=False)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=1),
                        'Even if the Tester\'s output is off, the Testee\'s input should keep seeing a press. Got: {0}'.format(self.tools.input_status))

        self._set_input_advanced_configuration('onoffINP', output_to_toggle, 160)

        self.webinterface.set_output_status(id=output_to_toggle, is_on=True)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=0),
                        'The Tester\'s input module should see a release after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=output_to_toggle, is_on=False)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=output_to_toggle, value=0),
                        'The Tester\'s input module should keep seeing a release after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_toggles_all_outputs(self):
        """ Testing toggling all outputs. """
        self._set_default_output_config()
        time.sleep(0.3)
        configured_input_number = randint(0, 7)
        config = {'name': 'togglerO',
                  'basic_actions': '173,255',
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': configured_input_number,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=configured_input_number, is_on=True)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=1),
                            'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=configured_input_number, is_on=False)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=1),
                            'The Tester\'s input module should keep seeing a press since its a toggle action toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        time.sleep(0.3)
        self.webinterface.set_output_status(id=configured_input_number, is_on=True)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=0),
                            'The Tester\'s input module should see releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        time.sleep(0.3)
        self.webinterface.set_output_status(id=configured_input_number, is_on=False)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=0),
                            'The Tester\'s input module should keep see seeing releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_turn_all_outputs_on_off(self):
        """ Testing turning all outputs on and off. """
        output_to_toggle = randint(0, 7)
        self._set_default_output_config()
        config = {'name': 'turnallO',
                  'basic_actions': '172,255',
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': output_to_toggle,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=output_to_toggle, is_on=True)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=1),
                            'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=output_to_toggle, is_on=False)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=1),
                            'The Tester\'s input module should keep seeing a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        config = {'name': 'turnallO',
                  'basic_actions': '171,255',
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': output_to_toggle,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=output_to_toggle, is_on=True)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=0),
                            'The Tester\'s input module should see releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)
        self.webinterface.set_output_status(id=output_to_toggle, is_on=False)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=0),
                            'The Tester\'s input module should keep seeing releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_toggles_all_outputs_floor(self):
        """ Testing toggling all outputs by floor number. """
        self._set_input_room_config()
        self._set_default_output_config()
        time.sleep(0.3)

        input_number = randint(0, 7)
        config = {'name': 'toggfO',
                  'basic_actions': '173,{}'.format(self.FLOOR_NUMBER),
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': input_number,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=input_number, is_on=True)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=1),
                            'The Tester\'s input module should see presses after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)

        self.webinterface.set_output_status(id=input_number, is_on=False)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=1),
                            'The Tester\'s input module should keep seeing presses after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)

        self.webinterface.set_output_status(id=input_number, is_on=True)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=0),
                            'The Tester\'s input module should see releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)

        self.webinterface.set_output_status(id=input_number, is_on=False)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=0),
                            'The Tester\'s input module should keep seeing releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_turn_all_outputs_on_off_floor(self):
        """ Testing turning all outputs on and off by floor number. """
        self._set_input_room_config()
        self._set_default_output_config()

        time.sleep(0.3)
        configured_input_number = randint(0, 7)
        config = {'name': 'turnerfO',
                  'basic_actions': '172,{}'.format(self.FLOOR_NUMBER),
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': configured_input_number,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=configured_input_number, is_on=True)
        time.sleep(0.5)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=1),
                            'The Tester\'s input module should see presses after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)

        self.webinterface.set_output_status(id=configured_input_number, is_on=False)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=1),
                            'The Tester\'s input module should keep seeing presses after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        config = {'name': 'turnerfO',
                  'basic_actions': '171,{}'.format(self.FLOOR_NUMBER),
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': configured_input_number,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=configured_input_number, is_on=True)
        time.sleep(0.5)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=0),
                            'The Tester\'s input module should see releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))
        time.sleep(0.3)

        self.webinterface.set_output_status(id=configured_input_number, is_on=False)
        for input_number in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_number, value=0),
                            'The Tester\'s input module should keep seeing releases after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_turn_all_outputs_off(self):
        """ Testing turning all outputs off. """
        self._set_input_room_config()
        self._set_default_output_config()

        input_number = randint(0, 7)
        config = {'name': 'turnoffO',
                  'basic_actions': '172,255',
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': input_number,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=input_number, is_on=True)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=1),
                            'The Tester\'s input module should see presses after toggling the Testee\'s output. Got: {0}'.format(
                                self.tools.input_status))
        time.sleep(0.3)

        self.webinterface.set_output_status(id=input_number, is_on=False)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=1),
                            'The Tester\'s input module should keep seeing presses after toggling the Testee\'s output. Got: {0}'.format(
                                self.tools.input_status))

        config = {'name': 'turnoffO',
                  'basic_actions': '164,0',
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': input_number,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=input_number, is_on=True)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=0),
                            'The Tester\'s input module should see releases after toggling the Testee\'s output. Got: {0}'.format(
                                self.tools.input_status))
        time.sleep(0.3)

        self.webinterface.set_output_status(id=input_number, is_on=False)
        for i in xrange(self.INPUT_COUNT):
            self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=i, value=0),
                            'The Tester\'s input module should keep seeing releases after toggling the Testee\'s output. Got: {0}'.format(
                                self.tools.input_status))

    @exception_handler
    def test_execute_group_actions_after_xtime(self):
        """ Testing the execution of a group action that will be executed after pressing an output for a while. """
        self._set_input_room_config()
        self._set_default_output_config()

        config = {'id': 1, 'actions': self.GROUP_ACTION_CONFIG.format(1), 'name': 'Test1'}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_group_action_configuration', params=params, token=self.token)

        config = {'id': 2, 'actions': self.GROUP_ACTION_CONFIG.format(2), 'name': 'Test2'}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_group_action_configuration', params=params, token=self.token)

        config = {'id': 3, 'actions': self.GROUP_ACTION_CONFIG.format(3), 'name': 'Test3'}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_group_action_configuration', params=params, token=self.token)

        config = {'id': 4, 'actions': self.GROUP_ACTION_CONFIG.format(4), 'name': 'Test4'}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_group_action_configuration', params=params, token=self.token)

        config = {'id': 5, 'actions': self.GROUP_ACTION_CONFIG.format(5), 'name': 'Test5'}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_group_action_configuration', params=params, token=self.token)

        config = {'name': 'exectime',
                  'basic_actions': '207,1,208,2,209,3,210,4,211,5',
                  'invert': 255,
                  'module_type': 'I',
                  'can': '',
                  'action': 240,
                  'id': 0,
                  'room': 255}
        params = {'config': json.dumps(config)}
        self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        self.webinterface.set_output_status(id=self.GROUP_ACTION_TARGET_ID, is_on=True)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=1, value=1),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=2, value=1),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=3, value=1),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=4, value=1),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=5, value=1),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.webinterface.set_output_status(id=self.GROUP_ACTION_TARGET_ID, is_on=False)

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=1, value=0),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=2, value=0),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=3, value=0),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=4, value=0),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=5, value=0),
                        'The Tester\'s input module should see a press after toggling the Testee\'s output. Got: {0}'.format(self.tools.input_status))

    @exception_handler
    def test_motion_sensor_timer_7m30s(self):
        """ Testing the setting up of a simulated motion sensor and validating the timer setting for toggling an output for 7m30s """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed196', input_output_number, 196)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        time.sleep(300)
        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result,
                        'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(460 > total_pressed_duration > 440, 'Should toggle off after around 7m30s. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_motion_sensor_timer_15m(self):
        """ Testing the setting up of a simulated motion sensor and validating the timer setting for toggling an output for 15m """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed197', input_output_number, 197)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        time.sleep(780)
        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result,
                        'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(910 > total_pressed_duration > 890, 'Should toggle off after around 15m. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_motion_sensor_timer_25m(self):
        """ Testing the setting up of a simulated motion sensor and validating the timer setting for toggling an output for 25m """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed198', input_output_number, 198)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        time.sleep(1380)
        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(1510 > total_pressed_duration > 1490, 'Should toggle off after around 25m. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_motion_sensor_timer_37m(self):
        """ Testing the setting up of a simulated motion sensor and validating the timer setting for toggling an output for 37m """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed199', input_output_number, 199)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        time.sleep(2100)
        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(2230 > total_pressed_duration > 2210, 'Should toggle off after around 37m. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_motion_sensor_timer_52m(self):
        """ Testing the setting up of a simulated motion sensor and validating the timer setting for toggling an output for 52m """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed200', input_output_number, 200)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1), 'Should turn on an input on the Tester that act as a motion sensor.')

        time.sleep(3000)
        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        # time.sleep(3000)
        # output_is_off = self.tools.check_if_event_is_captured(input_output_number, 0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(3130 > total_pressed_duration > 3110, 'Should toggle off after around 52m. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_time_no_overrule_2m30s(self):
        """ Testing the execution of an action (toggling output for 2m30s) - does not overrule the timer """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed201', input_output_number, 201)

        self._set_output_advanced_config(input_output_number)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(158 > total_pressed_duration > 148, 'Should still turn off after 2m30s since it first turned on. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_time_no_overrule_7m30s(self):
        """ Testing the execution of an action (toggling output for 7m30s) - does not overrule the timer """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed202', input_output_number, 202)

        self._set_output_advanced_config(input_output_number)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        start = time.time()

        while time.time() - start < 360:
            time.sleep(1)

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1), 'Should turn on an input on the Tester that act as a motion sensor.')

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(460 > total_pressed_duration > 440, 'Should still turn off after 7m30s since it first turned on. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_time_no_overrule_15m(self):
        """ Testing the execution of an action (toggling output for 15m) - does not overrule the timer """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed203', input_output_number, 203)

        self._set_output_advanced_config(input_output_number)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        start = time.time()

        while time.time() - start < 780:
            time.sleep(1)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(910 > total_pressed_duration > 890, 'Should still turn off after 15m since it first turned on. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_time_no_overrule_25(self):
        """ Testing the execution of an action (toggling output for 25m) - does not overrule the timer """
        input_output_number = randint(0, 7)

        self._set_input_advanced_configuration('timed204', input_output_number, 204)

        self._set_output_advanced_config(input_output_number)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        start = time.time()

        while time.time() - start < 1380:
            time.sleep(1)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))

        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(1510 > total_pressed_duration > 1490, 'Should still turn off after 25m since it first turned on. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_time_no_overrule_37m(self):
        """ Testing the execution of an action (toggling output for 37m) - does not overrule the timer """
        input_output_number = randint(0, 7)

        self._set_output_advanced_config(input_output_number)

        self._set_input_advanced_configuration('timed205', input_output_number, 205)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        start = time.time()

        while time.time() - start < 2100:
            time.sleep(1)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result,
                        'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))
        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(2230 > total_pressed_duration > 2210, 'Should still turn off after 37m since it first turned on. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_time_no_overrule_52m(self):
        """ Testing the execution of an action (toggling output for 52m) - does not overrule the timer """
        input_output_number = randint(0, 7)

        self._set_output_advanced_config(input_output_number)

        self._set_input_advanced_configuration('timed206', input_output_number, 206)

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        start = time.time()

        while time.time() - start < 3000:
            time.sleep(1)
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=1),
                        'Should turn on an input on the Tester that act as a motion sensor.')

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        self.webinterface.set_output_status(id=input_output_number, is_on=True)  # Sensor detects movement
        time.sleep(0.2)
        self.webinterface.set_output_status(id=input_output_number, is_on=False)  # Sensor stops detecting movement

        result = self.tools.check_if_event_is_captured(toggled_output=input_output_number, value=0)

        self.assertTrue(result, 'Should have unpressed the tester\'s input. Got {0}, expected output ID to untoggle: {1}'.format(result, input_output_number))
        total_pressed_duration = self.tools.input_record.get(str(input_output_number))["0"] - self.tools.input_record.get(str(input_output_number))["1"]

        self.assertTrue(3130 > total_pressed_duration > 3110, 'Should still turn off after 52m since it first turned on. Got: {0}'.format(total_pressed_duration))

    @exception_handler
    def test_thermostat_setpoint_action_type(self):
        """ Testing changing the setpoint of the Testee's thermostat 0. """
        self.tools.configure_thermostat(thermostat_number=0, night_temp=10, day_block1_temp=10.5, day_block2_temp=11)

        params = {'action_type': 148, 'action_number': 0}  # ActionType 148 changes the set point of thermostat X to 16.
        token = self.tools.get_new_token(self.tools.username, self.tools.password)
        self.tools.api_testee(api='do_basic_action', params=params, token=token)
        response = self.tools.api_testee(api='get_thermostat_status', token=token)
        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 16, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 16'.format(thermostat_status[0]['csetp']))

        params = {'action_type': 149, 'action_number': 0}  # ActionType 149 changes the set point of thermostat X to 22.5.
        self.tools.api_testee(api='do_basic_action', params=params, token=token)
        response = self.tools.api_testee(api='get_thermostat_status', token=token)
        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 22.5, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 22.5'.format(thermostat_status[0]['csetp']))

        self.tools.unconfigure_thermostat(thermostat_number=0)

    @exception_handler
    def test_thermostat_increase_setpoint_action_type(self):
        """ Testing increasing the setpoint of the Testee's thermostat 0. """
        self.tools.configure_thermostat(thermostat_number=0, night_temp=10, day_block1_temp=10.5, day_block2_temp=11)

        params = {'action_type': 148, 'action_number': 0}  # ActionType 148 changes the set point of thermostat X to 16.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)
        response = self.tools.api_testee(api='get_thermostat_status', token=self.token)

        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 16, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 16'.format(thermostat_status[0]['csetp']))

        params = {'action_type': 143, 'action_number': 0}  # ActionType 143 increases the set point by 0.5 of thermostat X.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

        response = self.tools.api_testee(api='get_thermostat_status', token=self.token)
        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 16.5, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 16.5'.format(thermostat_status[0]['csetp']))

        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)
        time.sleep(0.2)
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

        response = self.tools.api_testee(api='get_thermostat_status', token=self.token)
        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 17.5, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 17.5'.format(thermostat_status[0]['csetp']))

        self.tools.unconfigure_thermostat(thermostat_number=0)

    @exception_handler
    def test_thermostat_decrease_setpoint_action_type(self):
        """ Testing decreasing the setpoint of the Testee's thermostat 0. """
        self.tools.configure_thermostat(thermostat_number=0, night_temp=10, day_block1_temp=10.5, day_block2_temp=11)

        params = {'action_type': 149, 'action_number': 0}  # ActionType 149 changes the set point of thermostat X to 22.5.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)
        response = self.tools.api_testee(api='get_thermostat_status', token=self.token)

        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 22.5, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 22.5'.format(thermostat_status[0]['csetp']))

        params = {'action_type': 142, 'action_number': 0}  # ActionType 142 decreases the set point by 0.5 of thermostat X.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

        response = self.tools.api_testee(api='get_thermostat_status', token=self.token)
        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 22, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 22'.format(thermostat_status[0]['csetp']))

        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)
        time.sleep(0.2)
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

        response = self.tools.api_testee(api='get_thermostat_status', token=self.token)
        thermostat_status = response.get('status')
        if not thermostat_status:
            self.fail('Setting standard thermostat set point has failed.')
        self.assertEqual(thermostat_status[0]['csetp'], 21, 'Current setpoint doesn\'t match the expected setpoint: {0} vs 21'.format(thermostat_status[0]['csetp']))

        self.tools.unconfigure_thermostat(thermostat_number=0)

    @exception_handler
    def test_turn_only_lights_off(self):
        """ Testing turning only lights off. """
        self._set_default_output_config()

        params = {'action_type': 172, 'action_number': 3}  # ActionType 172 will turn all lights on a specific floor.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

        for output_number in xrange(8):
            config = {"room": 5,
                      "can_led_4_function": "UNKNOWN",
                      "floor": 3,
                      "can_led_1_id": 255,
                      "can_led_1_function": "UNKNOWN",
                      "timer": 65535,
                      "can_led_4_id": 255,
                      "can_led_3_id": 255,
                      "can_led_2_function": "UNKNOWN",
                      "id": output_number,
                      "module_type": "O",
                      "can_led_3_function": "UNKNOWN",
                      "type": 0 if output_number % 2 == 0 else 255,
                      "can_led_2_id": 255,
                      "name": "Out{0}".format(output_number)
                      }  # this will set relay, light, relay...etc
            params = {'config': json.dumps(config)}
            self.tools.api_testee(api='set_output_configuration', params=params, token=self.token)

        params = {'action_type': 163, 'action_number': randint(0, 239)}  # ActionType 172 will turn all lights by floor.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=0, value=1),
                        'Output 0 should stay on since its a relay. Got: {0}'.format(self.tools.input_status))
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=1, value=0),
                        'Output 1 should turn off since its a light. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=2, value=1),
                        'Output 2 should stay on since its a relay. Got: {0}'.format(self.tools.input_status))
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=3, value=0),
                        'Output 3 should turn off since its a light. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=4, value=1),
                        'Output 4 should stay on since its a relay. Got: {0}'.format(self.tools.input_status))
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=5, value=0),
                        'Output 5 should turn off since its a light. Got: {0}'.format(self.tools.input_status))

        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=6, value=1),
                        'Output 6 should stay on since its a relay. Got: {0}'.format(self.tools.input_status))
        self.assertTrue(self.tools.check_if_event_is_captured(toggled_output=7, value=0),
                        'Output 7 should turn off since its a light. Got: {0}'.format(self.tools.input_status))

        self._set_default_output_config()

        params = {'action_type': 173, 'action_number': 3}  # Turning all outputs off.
        self.tools.api_testee(api='do_basic_action', params=params, token=self.token)

    def _set_group_actions_config(self):
        """
        Sets the standard 160 group actions configurations that will toggle output id=0

        :return: the response from setting the group action configurations
        :rtype: request.Response

        """
        config = []
        for i in xrange(160):
            one_group_action_config = {'id': i,
                                       'actions': '240,0,244,0,240,10,161,0,235,5,160,0,235,255,240,20,160,0,235,5,161,0,235,255,240,255',
                                       'name': 'Test{0}'.format(i)}
            config.append(one_group_action_config)
        params = {'config': json.dumps(config)}

        token = self.tools.get_new_token(self.tools.username, self.tools.password)

        return self.tools.api_testee(api='set_group_action_configurations', params=params, token=token), config

    def _set_input_room_config(self):
        """
        Sets the standard input configuration with the relevant floor number and room number

        :return: the response from setting room configurations.
        :rtype: request.Response
        """
        for i in xrange(self.INPUT_COUNT):
            config = {'name': 'input' + str(i), 'basic_actions': '', 'invert': 255, 'module_type': 'I', 'can': '',
                      'action': i, 'id': i, 'room': self.ROOM_NUMBER}
            params = {'config': json.dumps(config)}
            self.tools.api_testee(api='set_input_configuration', params=params, token=self.token)

        config = []
        for i in xrange(100):
            one_room_config = {'id': i, 'name': 'room{}'.format(self.ROOM_NUMBER), 'floor': self.FLOOR_NUMBER}
            config.append(one_room_config)
        params = {'config': json.dumps(config)}

        return self.tools.api_testee(api='set_room_configurations', params=params, token=self.token)

    def _set_default_output_config(self):
        token = self.tools.get_new_token(self.tools.username, self.tools.password)
        for i in xrange(8):
            config = {"room": 5,
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

            params = {'config': json.dumps(config)}
            self.tools.api_testee(api='set_output_configuration', params=params, token=token)

    def _set_output_advanced_config(self, input_output_number):
        token = self.tools.get_new_token(self.tools.username, self.tools.password)
        modified_output_config = {"room": 5,
                                  "can_led_4_function": "UNKNOWN",
                                  "floor": 3,
                                  "can_led_1_id": 255,
                                  "can_led_1_function": "UNKNOWN",
                                  "timer": 30,
                                  "can_led_4_id": 255,
                                  "can_led_3_id": 255,
                                  "can_led_2_function": "UNKNOWN",
                                  "id": input_output_number,
                                  "module_type": "O",
                                  "can_led_3_function": "UNKNOWN",
                                  "type": 255,
                                  "can_led_2_id": 255,
                                  "name": "Out{0}".format(input_output_number)}

        params = {'config': json.dumps(modified_output_config)}
        self.tools.api_testee(api='set_output_configuration', params=params, token=token)

    def _set_input_advanced_configuration(self, input_name, input_output_number, action_type):
        modified_input_config = {"name": "{0}".format(input_name),
                                 "basic_actions": "{0},{1}".format(action_type, input_output_number),
                                 "invert": 255,
                                 "module_type": "I",
                                 "can": "",
                                 "action": 240,
                                 "id": input_output_number,
                                 "room": 255}

        params = {'config': json.dumps(modified_input_config)}
        token = self.tools.get_new_token(self.tools.username, self.tools.password)
        self.tools.api_testee(api='set_input_configuration', params=params, token=token)
