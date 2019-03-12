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
The websocket_test.py file contains tests related to websocket and other private methods
that the tests will use.
"""
import unittest
import base64
import logging
import time
import msgpack
import simplejson as json
from ws4py.client.threadedclient import WebSocketClient
from toolbox import exception_handler

LOGGER = logging.getLogger('openmotics')


class WebsocketTest(unittest.TestCase):
    """
    The WebsocketTest is a test case for websocket.
    """
    webinterface = None
    tools = None
    token = ''

    @classmethod
    def setUpClass(cls):
        if not cls.tools.healthy_status:
            raise unittest.SkipTest('The Testee is showing an unhealthy status. All tests are skipped.')

    def setUp(self):
        self.token = self.tools.get_new_token(self.tools.username, self.tools.password)
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools.assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: %s due to discovery failure.', self.id())
                self.skipTest('Failed to discover modules.')
        self._set_default_input_configuration()
        self._set_default_output_configuration()
        LOGGER.info('Running: %s', self.id())

    @exception_handler
    def test_websocket_output_change(self):
        """ Testing the websocket on the Testee for output_change event. """
        callback_data = {'data': []}

        def _callback(data):
            """ _callback will set the variable DATA when a message is received. """
            callback_data['data'].append(data)

        socket = PassthroughClient('wss://{0}/ws_events'.format(self.tools.testee_ip),
                                   protocols=['authorization.bearer.{0}'.format(base64.b64encode(self.token.encode('ascii')).decode('utf-8').replace('=', ''))], event_name='OUTPUT_CHANGE', callback=_callback)
        socket.connect()

        self.tools.clicker_releaser(3, self.token, True)
        input_triggered = self.tools.check_if_event_is_captured(toggled_output=3, value=1)
        if not input_triggered:
            self.fail('failed to validate state on the Testee\'s output.')
        time.sleep(0.5)

        self.assertTrue(len(callback_data['data']) == 1, 'Websocket returned an empty response!')
        self.assertTrue(callback_data['data'][-1]['data']['status']['on'], 'Should contain the status of the output. Got: {0}'.format(callback_data['data']))
        self.assertEqual(callback_data['data'][-1]['data']['id'], 3, 'Should contain the correct triggered ID. Got: {0}'.format(callback_data['data']))
        self.assertEqual(callback_data['data'][-1]['type'], 'OUTPUT_CHANGE', 'Should contain the correct event type. Got: {0}'.format(callback_data['data']))

        self.tools.clicker_releaser(3, self.token, False)
        self.tools.check_if_event_is_captured(toggled_output=3, value=0)
        time.sleep(0.5)

        self.assertTrue(len(callback_data['data']) == 2, 'Websocket returned an empty response!')
        self.assertFalse(callback_data['data'][-1]['data']['status']['on'], 'Should contain the status of the output. Got: {0}'.format(callback_data['data']))
        self.assertEqual(callback_data['data'][-1]['data']['id'], 3, 'Should contain the correct triggered ID. Got: {0}'.format(callback_data['data']))
        self.assertEqual(callback_data['data'][-1]['type'], 'OUTPUT_CHANGE', 'Should contain the correct event type. Got: {0}'.format(callback_data['data']))
        time.sleep(1)

        callback_data.update({'data': []})
        socket.close(200, 'Test output_change terminated')

    @exception_handler
    def test_websocket_input_trigger(self):
        """ Testing the websocket on the Testee for input_trigger event. """
        callback_data = {'data': []}

        def _callback(data):
            """ _callback will set the variable DATA when a message is received. """
            callback_data['data'].append(data)

        socket = PassthroughClient('wss://{0}/ws_events'.format(self.tools.testee_ip),
                                   protocols=['authorization.bearer.{0}'.format(base64.b64encode(self.token.encode('ascii')).decode('utf-8').replace('=', ''))], event_name='INPUT_TRIGGER', callback=_callback)
        socket.connect()

        self.webinterface.set_output(id=4, is_on=True)
        time.sleep(0.5)
        self.webinterface.set_output(id=4, is_on=False)

        self.assertTrue(len(callback_data['data']) == 1, 'Websocket returned an empty response!')
        self.assertEqual(callback_data['data'][-1]['data']['id'], 4, 'Should contain the correct triggered ID. Got: {0}'.format(callback_data['data']))
        self.assertEqual(callback_data['data'][-1]['type'], 'INPUT_TRIGGER', 'Should contain the correct event type. Got: {0}'.format(callback_data['data']))

        time.sleep(0.5)

        self.webinterface.set_output(id=4, is_on=True)
        time.sleep(0.5)
        self.webinterface.set_output(id=4, is_on=False)

        self.assertTrue(len(callback_data['data']) == 2, 'Websocket returned an empty response!')
        self.assertEqual(callback_data['data'][-1]['data']['id'], 4, 'Should contain the correct triggered ID. Got: {0}'.format(callback_data['data']))
        self.assertEqual(callback_data['data'][-1]['type'], 'INPUT_TRIGGER', 'Should contain the correct event type. Got: {0}'.format(callback_data['data']))

        callback_data.update({'data': []})

        socket.close(200, 'Test input_trigger terminated')

    def _set_default_output_configuration(self):
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

    def _set_default_input_configuration(self):
        token = self.tools.get_new_token(self.tools.username, self.tools.password)
        for i in xrange(8):

            input_configuration = {"name": "input{0}".format(i),
                                   "basic_actions": "",
                                   "invert": 255,
                                   "module_type": "I",
                                   "can": "",
                                   "action": i,
                                   "id": i,
                                   "room": 5}

            params = {'config': json.dumps(input_configuration)}
            self.tools.api_testee(api='set_input_configuration', params=params, token=token)


class PassthroughClient(WebSocketClient):
    """ PassthroughClient is a custom WebSocketClient. """
    def __init__(self, *args, **kwargs):
        self.callback = kwargs.pop('callback')
        self.event = kwargs.pop('event_name')
        WebSocketClient.__init__(self, *args, **kwargs)

    def opened(self):
        self.send(
            msgpack.dumps(
                {'type': 'ACTION',
                 'data': {'action': 'set_subscription',
                          'types': [self.event]}}
            ),
            binary=True
        )

    def received_message(self, message):
        try:
            data = msgpack.loads(message.data)
            self.callback(data)
        except Exception:
            pass
