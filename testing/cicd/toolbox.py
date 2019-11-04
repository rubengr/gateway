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

""""
The toolbox.py contains Toolbox, a helper with useful methods and APIFailedException a custom exception.
"""
import unittest
import random
import string
import time
import logging
import functools
import math
import simplejson as json
import requests
import subprocess
from contextlib import contextmanager
from multiprocessing.connection import Client
from requests.exceptions import ConnectionError
from plugin_runtime.web import WebInterfaceDispatcher

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger('openmotics')
AUTHORIZED_MODE_OUTPUT_ID = 13
DISCOVER_TESTEE_INPUT_ID = 14
DISCOVER_TESTEE_OUTPUT_ID = 15
DISCOVER_TESTEE_DIMMER_ID = 20
DISCOVER_TESTEE_TEMPERATURE_ID = 21
DISCOVER_TESTEE_CAN_ID = 22


class Toolbox(object):
    """"
    The Toolbox is a helper with several methods that the test cases will use.
    """

    def __init__(self, testee_ip, timeout, healthy_status, discovery_success, initialisation_success, username, password):
        self.testee_ip = testee_ip
        self.TIMEOUT = timeout
        self.healthy_status = healthy_status
        self.discovery_success = discovery_success
        self.initialisation_success = initialisation_success
        self.username = username
        self.password = password
        self.SSH_LOGGER_COMMAND = "ssh root@{0} 'echo {1} >> /var/log/supervisor/openmotics_stderr.log'"

    def api_testee(self, api, token=None, params=None, expected_failure=False):
        """
        Used to call APIs on the Testee
        :param api: URI to the target API on the Testee
        :type api: str

        :param token: A valid token of a logged in user on the Testee
        :type token: str

        :param params: A dictionary of parameters for the given API
        :type params: dict

        :param expected_failure: Indicates if the API call is expected to fail / retry few times
        :type expected_failure: bool

        :return: API response
        :rtype: dict
        """

        uri = 'https://{0}/{1}'.format(self.testee_ip, api)
        start = time.time()
        retry_count = 0

        while time.time() - start <= self.TIMEOUT:
            try:
                if token is None:
                    response = requests.get(uri, verify=False, params=params or {})
                else:
                    response = requests.get(uri, verify=False, params=params or {}, headers={'Authorization': 'Bearer {0}'.format(token)})
                if response is None:
                    time.sleep(0.3)
                    continue
                response_dict = response.json()
                if expected_failure is False:
                    if not isinstance(response_dict, dict):
                        if response_dict == 'invalid_token' and retry_count < 1:
                            time.sleep(0.3)
                            token = self.get_new_token(self.username, self.password)
                            retry_count += 1
                            continue
                        raise APIFailedException('The API call {0} encountered an unexpected error and returned: {1}.'.format(api, response_dict))
                    elif response_dict.get('success', False) is False:
                        if response_dict.get('msg') == 'Internal communication timeout':
                            time.sleep(0.3)
                            continue
                        raise APIFailedException('The API call {0} failed with success: False and returned: {1}'.format(api, response_dict))
                return response_dict
            except ConnectionError:
                continue

    @staticmethod
    def randomword(size):
        """
        Random string generator.

        :param size: random word size
        :type size: int
        :return: random string
        :rtype: str
        """
        letters = string.ascii_lowercase
        return ''.join(random.choice(letters) for _ in range(size))

    def enter_testee_authorized_mode(self, web, timeout=None):
        """
        Enters authorized mode on the Testee.
        :param web: Tester's webinterface

        :param timeout: duration in seconds of the output toggling.
        :type timeout: int
        :return: Enters authorized mode on the Testee
        """
        if timeout is None:
            timeout = self.TIMEOUT
        start = time.time()
        web.set_output(id=AUTHORIZED_MODE_OUTPUT_ID, is_on=True)
        while time.time() - start < timeout:
            if self.api_testee(api='get_usernames', expected_failure=True).get('success', False) is True:
                web.set_output(id=AUTHORIZED_MODE_OUTPUT_ID, is_on=False)
                return True
            else:
                time.sleep(0.3)
                continue
        web.set_output(id=AUTHORIZED_MODE_OUTPUT_ID, is_on=False)
        return False

    def exit_testee_authorized_mode(self, web):
        """
        Exits authorized mode on the Testee.
        :param web: Tester's webinterface
        :return: Exists authorized mode on the Testee
        """
        if self.api_testee(api='get_usernames', expected_failure=True).get('success', False) is not False:
            json.loads(web.set_output(id=13, is_on=False))
            time.sleep(0.3)
        web.set_output(id=AUTHORIZED_MODE_OUTPUT_ID, is_on=True)
        time.sleep(0.3)
        web.set_output(id=AUTHORIZED_MODE_OUTPUT_ID, is_on=False)
        time.sleep(0.3)

    def clicker_releaser(self, target_id, token, status):
        """
        Toggles on/off an output
        :param target_id: id of the output to toggle on the Testee
        :type target_id: int

        :param token: A valid token of a logged in user on the Testee
        :type token: str

        :param status: Indicates whether to toggle on or off the output
        :type status: bool

        :return: Status of the API call (True/False)
        :rtype: bool
        """
        params = {'id': str(target_id), 'is_on': str(status)}
        response_json = self.api_testee(api='set_output', params=params, token=token)
        return response_json.get('success', False)

    def human_click_testee(self, target_id, token):
        """
        Toggles on and off an output in 500ms on the Testee.
        :param target_id: id of the output to toggle on the Testee
        :type target_id: int

        :param token: A valid token of a logged in user on the Testee
        :type token: str

        :return: Status of the API call (True/False)
        :rtype: bool
        """
        result1 = self.clicker_releaser(target_id, token, True)
        time.sleep(0.5)
        result2 = self.clicker_releaser(target_id, token, False)
        time.sleep(0.5)
        return result1 and result2

    @staticmethod
    def human_click(target_id, is_on, web):
        """
        Toggles on and off an output in 500ms on the Tester.
        :param target_id: id of the output to toggle on the Tester
        :type target_id: int

        :param is_on: Takes True or False values to indicate whether to toggle on or off an output on the Tester.
        :type is_on: bool

        :param web: Tester's webinterface

        :return: Status of the API call (True/False)
        :rtype: bool
        """
        result1 = json.loads(web.set_output(id=target_id, is_on=is_on)).get('success', False)
        time.sleep(0.5)
        result2 = json.loads(web.set_output(id=target_id, is_on=not is_on)).get('success', False)
        time.sleep(0.5)
        return result1 and result2

    def get_new_token(self, username, password):
        """
        Used to get a new token after calling login API.
        :param username: the username of a user
        :type username: str

        :param password: the password of a user
        :type password: str

        :return: a valid access token if the login API call is a success.
        :rtype: str
        """
        params = {'username': username, 'password': password, 'accept_terms': True}
        return self.api_testee('login', params=params).get('token')

    def assert_discovered(self, token, web):
        """
        Used to check if the modules have been successfully discovered.
        :param token: an access token
        :type token: str

        :param web: the tester's webinterface
        :type web: WebInterface object

        :return: whether discovery have been successfully made
        :rtype: bool
        """
        if not self.discovery_success:
            self.api_testee(api='module_discover_start', token=token)
            time.sleep(0.3)
            response_json = self.api_testee(api='module_discover_status', token=token)
            if response_json.get('running'):
                self.human_click(DISCOVER_TESTEE_INPUT_ID, True, web)
                self.human_click(DISCOVER_TESTEE_OUTPUT_ID, True, web)

            self.api_testee(api='module_discover_stop', token=token)
            response_json = self.api_testee(api='get_modules', token=token)
            if not response_json.get('outputs', []) or not response_json.get('inputs', []):
                return False
            return True

    @contextmanager
    def listen_for_events(self):
        with EventListener(self.TIMEOUT) as event_listener:
            yield event_listener

    def configure_thermostat(self, thermostat_number, night_temp, day_block1_temp, day_block2_temp):
        """
        Configures a thermostat
        :param thermostat_number: the id of the thermostat to configure
        :type thermostat_number: int

        :param night_temp: the temperature setpoint at night
        :type night_temp: float

        :param day_block1_temp: the temperature setpoint for the first half of the daytime
        :type day_block1_temp: float

        :param day_block2_temp: the temperature setpoint for the second half of the daytime
        :type day_block2_temp: float
        """
        thermostat_config = {
            "auto_wed": [
                night_temp + 3,
                "08:00",
                "10:00",
                day_block1_temp + 3,
                "16:00",
                "20:00",
                day_block2_temp + 3
            ],
            "auto_mon": [
                night_temp,
                "08:00",
                "10:00",
                day_block1_temp,
                "16:00",
                "20:00",
                day_block2_temp
            ],
            "output0": 0,
            "output1": 255,
            "permanent_manual": False,
            "id": thermostat_number,
            "auto_sat": [
                night_temp + 7.5,
                "08:00",
                "10:00",
                day_block1_temp + 7.5,
                "16:00",
                "20:00",
                day_block2_temp + 7.5
            ],
            "name": "HT0",
            "sensor": 31,
            "auto_sun": [
                night_temp + 9,
                "08:00",
                "10:00",
                day_block1_temp + 9,
                "16:00",
                "20:00",
                day_block2_temp + 9
            ],
            "auto_thu": [
                night_temp + 4.5,
                "08:00",
                "10:00",
                day_block1_temp + 4.5,
                "16:00",
                "20:00",
                day_block2_temp + 4.5
            ],
            "pid_int": 255,
            "auto_tue": [
                night_temp + 1.5,
                "08:00",
                "10:00",
                day_block1_temp + 1.5,
                "16:00",
                "20:00",
                day_block2_temp + 1.5
            ],
            "setp0": night_temp + 10.5,
            "setp5": night_temp + 15,
            "setp4": night_temp + 13.5,
            "pid_p": 255,
            "setp1": day_block1_temp + 10.5,
            "room": 255,
            "setp3": night_temp + 12,
            "setp2": day_block2_temp + 10.5,
            "auto_fri": [
                night_temp + 6,
                "08:00",
                "10:00",
                day_block1_temp + 6,
                "16:00",
                "20:00",
                day_block2_temp + 6
            ],
            "pid_d": 255,
            "pid_i": 255
        }

        params = {'config': json.dumps(thermostat_config)}
        token = self.get_new_token(self.username, self.password)
        self.api_testee(api='set_thermostat_configuration', params=params, token=token)

    def unconfigure_thermostat(self, thermostat_number):
        """
        Restores the default configuration for a thermostat
        :param thermostat_number: the id of the thermostat to unconfigure
        :type thermostat_number: int
        """

        thermostat_config = {
            "auto_wed": [
                16,
                "42:30",
                "42:30",
                None,
                "42:30",
                "42:30",
                None
            ],
            "auto_mon": [
                16,
                "42:30",
                "42:30",
                None,
                "42:30",
                "42:30",
                None
            ],
            "output0": 255,
            "output1": 255,
            "permanent_manual": False,
            "id": thermostat_number,
            "auto_sat": [
                16,
                "42:30",
                "42:30",
                None,
                "42:30",
                "42:30",
                None
            ],
            "name": "",
            "sensor": 255,
            "auto_sun": [
                16,
                "42:30",
                "42:30",
                None,
                "42:30",
                "42:30",
                None
            ],
            "auto_thu": [
                16,
                "42:30",
                "42:30",
                None,
                "42:30",
                "42:30",
                None
            ],
            "pid_int": 255,
            "auto_tue": [
                16,
                "42:30",
                "42:30",
                None,
                "42:30",
                "42:30",
                None
            ],
            "setp0": None,
            "setp5": None,
            "setp4": None,
            "pid_p": 255,
            "setp1": None,
            "room": 255,
            "setp3": None,
            "setp2": None,
            "auto_fri": [
                16,
                "42:30",
                "42:30",
                None,
                "42:30",
                "42:30",
                None
            ],
            "pid_d": 255,
            "pid_i": 255
        }

        params = {'config': json.dumps(thermostat_config)}
        token = self.get_new_token(self.username, self.password)
        self.api_testee('set_thermostat_configuration', params=params, token=token)

    @staticmethod
    def is_not_empty(anything):
        return True if anything else False


class EventListener(object):
    def __init__(self, timeout, hostname='localhost', port=6666):
        self.timeout = timeout
        self.address = (hostname, port)
        self.conn = None
        self.received_events = []

    def __enter__(self):
        self.conn = Client(self.address)
        return self

    def __exit__(self, *args):
        self.conn.close()

    def wait_for_event(self, *event_id):
        """
        Capture events until the given event_id has occurred. Multiple event_id
        can be provided and all should occur. This happens until
        EventListener.timeout.

        :param event_id: One or more event IDs to wait for
        :type event_id: int or list of int

        :return: Whether or not the event_id has been received before timeout
        :type: bool
        """
        if len(event_id) == 1 and isinstance(event_id[0], list):
            remaining_events = event_id[0]
        else:
            remaining_events = list(event_id)
        start_time = time.time()
        max_time = start_time + self.timeout
        while self.conn.poll(max(0, math.ceil(max_time - time.time()))):
            event = self.conn.recv()
            self.received_events.append({'value': event, 'timestamp': time.time()})
            try:
                remaining_events.remove(event)
            except ValueError:
                pass
            if not remaining_events:
                return True
        return False

    def wait_for_output(self, *args):
        """
        Capture output events until the given output_id reaches a given status.
        Multiple output_id, value pairs can be provided and all should occur.
        This happens until EventListener.timeout.

        :param args: multiple formats are allowed:
                        - output_id, status
                        - output_id, status, output_id, status, ...
                        - [(output_id, status), (output_id, status), ...]
        :type args: tuple of int or list of tuple of int

        :return: Whether or not the output_id/status has been received before timeout
        :type: bool
        """
        if len(args) == 1 and isinstance(args[0], list):
            expected_events = [10*output_id + status
                               for output_id, status in args[0]]
        elif not len(args) % 2 and all(isinstance(arg, int) for arg in args):
            expected_events = [10*output_id + status
                               for output_id, status
                               in zip(args[::2], args[1::2])]
        else:
            raise ValueError('Invalid arguments for wait_for_output: {}'.format(args))
        return self.wait_for_event(expected_events)

    @property
    def received_outputs(self):
        received_outputs = [
            {
                'output_id': event['value'] // 10,
                'status': event['value'] % 10,
                'timestamp': event['timestamp'],
            }
            for event in self.received_events
        ]
        return received_outputs


class OMTestCase(unittest.TestCase):
    webinterface = None
    tools = None
    token = ''

    @classmethod
    def setUpClass(cls):
        # TODO: move to some config
        cls.tools = Toolbox(
            testee_ip='gateway-testee-debian.qa.openmotics.com',
            timeout=10,
            healthy_status=True,
            discovery_success=True,
            initialisation_success=True,
            username='openmotics',
            password='123456',
        )
        cls.webinterface = WebInterfaceDispatcher(LOGGER.info)

        if not cls.tools.healthy_status:
            raise unittest.SkipTest('The Testee is showing an unhealthy status. All tests are skipped.')
        if not cls.tools.initialisation_success:
            raise unittest.SkipTest('Unable to initialise the Testee. All tests are skipped.')
        from random import randint
        i = randint(4, 36)
        cls.login = cls.tools.randomword(i)
        cls.password = cls.tools.randomword(i)

    def setUp(self):
        self.token = self.tools.get_new_token(self.tools.username, self.tools.password)
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools.assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: %s due to discovery failure.', self.id())
                self.skipTest('Failed to discover modules.')
        import os
        LOGGER.info('Running: %s', self.id())
        os.system(self.tools.SSH_LOGGER_COMMAND.format(self.tools.testee_ip, self.id()))


class APIFailedException(Exception):
    """Exception when the API call to the testee fails."""


def exception_handler(function):
    """Decorator that handles failed API calls to the Testee."""
    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except Exception as e:
            # Useful to get logs from the Testee gateway.
            # This will also be visible as fail logs in Jenkins.
            logs = subprocess.check_output("ssh root@gateway-testee-debian.qa.openmotics.com 'tail -170 /var/log/supervisor/openmotics_stderr.log'", shell=True)
            # TODO: the test id is not in the logs anymore, so we see all logs
            LOGGER.error('Testee logs: {0}'.format(logs))
            raise

    return wrapper
