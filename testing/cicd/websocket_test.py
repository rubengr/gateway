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
import requests
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
    DATA = None

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
    def test_websocket_output_change(self):
        """ Testing the websocket on the Testee for output_change event. """

        token = requests.get('https://{0}/login'.format(self.tools.testee_ip),
                             params={'username': 'openmotics',
                                     'password': '123456'},
                             verify=False).json()['token']
        socket = PassthroughClient('wss://{0}/ws_events'.format(self.tools.testee_ip),
                                   protocols=['authorization.bearer.{0}'.format(
                                       base64.b64encode(token.encode('ascii')).decode('utf-8').replace('=', ''))], callback=_callback)
        socket.connect()

        self.tools.clicker_releaser(3, token, True)
        self.tools.check_if_event_is_captured(3, 1)
        time.sleep(0.5)
        self.assertTrue(bool(WebsocketTest.DATA), ' Should not be None. Got: {0}'.format(WebsocketTest.DATA))
        time.sleep(1)
        LOGGER.info(WebsocketTest.DATA)
        self.assertTrue(WebsocketTest.DATA['data']['status']['on'], 'Should contain the status of the output. Got: {0}'.format(WebsocketTest.DATA))
        self.assertEqual(WebsocketTest.DATA['data']['id'], 3, 'Should contain the correct triggered ID. Got: {0}'.format(WebsocketTest.DATA))
        self.assertEqual(WebsocketTest.DATA['type'], 'OUTPUT_CHANGE', 'Should contain the correct event type. Got: {0}'.format(WebsocketTest.DATA))

        time.sleep(0.5)

        self.tools.clicker_releaser(3, token, False)

        self.tools.check_if_event_is_captured(3, 0)

        time.sleep(0.5)
        self.assertTrue(bool(WebsocketTest.DATA), ' Got something else: {0}'.format(WebsocketTest.DATA))
        time.sleep(1)
        self.assertTrue(not WebsocketTest.DATA['data']['status']['on'], 'Should contain the status of the output. Got: {0}'.format(WebsocketTest.DATA))
        self.assertEqual(WebsocketTest.DATA['data']['id'], 3, 'Should contain the correct triggered ID. Got: {0}'.format(WebsocketTest.DATA))
        self.assertEqual(WebsocketTest.DATA['type'], 'OUTPUT_CHANGE', 'Should contain the correct event type. Got: {0}'.format(WebsocketTest.DATA))

    @exception_handler
    def test_websocket_input_trigger(self):
        """ Testing the websocket on the Testee for input_trigger event. """
        token = requests.get('https://{0}/login'.format(self.tools.testee_ip),
                             params={'username': 'openmotics',
                                     'password': '123456'},
                             verify=False).json()['token']
        socket = PassthroughClient('wss://{0}/ws_events'.format(self.tools.testee_ip),
                                   protocols=['authorization.bearer.{0}'.format(
                                       base64.b64encode(token.encode('ascii')).decode('utf-8').replace('=', ''))], callback=_callback)
        socket.connect()

        self.webinterface.set_output(id=4, is_on=True)
        time.sleep(0.5)
        self.webinterface.set_output(id=4, is_on=False)
        self.assertTrue(bool(WebsocketTest.DATA), ' Got something else: {0}'.format(WebsocketTest.DATA))
        time.sleep(1)
        self.assertEqual(WebsocketTest.DATA['data']['id'], 4, 'Should contain the correct triggered ID. Got: {0}'.format(WebsocketTest.DATA))
        self.assertEqual(WebsocketTest.DATA['type'], 'INPUT_TRIGGER', 'Should contain the correct event type. Got: {0}'.format(WebsocketTest.DATA))

        time.sleep(0.5)

        self.webinterface.set_output(id=4, is_on=True)
        time.sleep(0.5)
        self.webinterface.set_output(id=4, is_on=False)
        self.assertTrue(bool(WebsocketTest.DATA), ' Got something else: {0}'.format(WebsocketTest.DATA))
        time.sleep(1)
        self.assertEqual(WebsocketTest.DATA['data']['id'], 4, 'Should contain the correct triggered ID. Got: {0}'.format(WebsocketTest.DATA))
        self.assertEqual(WebsocketTest.DATA['type'], 'INPUT_TRIGGER', 'Should contain the correct event type. Got: {0}'.format(WebsocketTest.DATA))


class PassthroughClient(WebSocketClient):
    """ PassthroughClient is a custom WebSocketClient. """
    def __init__(self, *args, **kwargs):
        self.callback = kwargs.pop('callback')
        WebSocketClient.__init__(self, *args, **kwargs)

    def opened(self):
        self.send(
            msgpack.dumps(
                {'type': 'ACTION',
                 'data': {'action': 'set_subscription',
                          'types': ['OUTPUT_CHANGE', 'INPUT_TRIGGER']}}
            ),
            binary=True
        )

    def received_message(self, message):
        try:
            data = msgpack.loads(message.data)
            self.callback(data)
        except Exception:
            pass


def _callback(data):
    """ _callback will set the variable DATA when a message is received. """
    WebsocketTest.DATA = data
