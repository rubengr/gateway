import unittest
import time
import urllib
import logging
import simplejson as json
from toolbox import exception_handler

LOGGER = logging.getLogger('openmotics')
#                                            _   _
#                                           | | (_)
#    ___  _ __   ___ _ __    _ __ ___   ___ | |_ _  ___ ___
#   / _ \| '_ \ / _ \ '_ \  | '_ ` _ \ / _ \| __| |/ __/ __|
#  | (_) | |_) |  __/ | | | | | | | | | (_) | |_| | (__\__ \
#   \___/| .__/ \___|_| |_| |_| |_| |_|\___/ \__|_|\___|___/
#        | |
#        |_|


class ThermostatsTest(unittest.TestCase):
    webinterface = None
    tools = None
    token = ''
    TESTEE_POWER = 8
    NIGHT_TEMP_INIT, DAY_BLOCK1_INIT, DAY_BLOCK2_INIT = 10.0, 10.5, 11.0  # Values from 10.0 to 20.0 represent values from Monday till Sunday.

    @classmethod
    def setUpClass(cls):
        if not cls.tools.healthy_status:
            raise unittest.SkipTest('The Testee is showing an unhealthy status. All tests are skipped.')
        cls.token = cls.tools._get_new_token('openmotics', '123456')

    def setUp(self):
        if not self.tools.discovery_success:
            self.tools.discovery_success = self.tools._assert_discovered(self.token, self.webinterface)
            if not self.tools.discovery_success:
                LOGGER.error('Skipped: {} due to discovery failure.'.format(self.id()))
                self.skipTest('Failed to discover modules.')
        LOGGER.info('Running: {}'.format(self.id()))

    @exception_handler
    def test_thermostat_config_after_reset(self):
        """ Testing whether or not the thermostat configuration will be kept after resetting and power cycle. """
        sensor_config = {'id': 31, 'name': 'v_sensor', 'virtual': True, 'room': 255}
        url_params = urllib.urlencode({'config': json.dumps(sensor_config)})
        self.tools._api_testee('set_sensor_configuration?{0}'.format(url_params), self.token, expected_failure=False)

        sensor_31_config = {'sensor_id': 31, 'temperature': 1, 'humidity': None, 'brightness': None}
        url_params = urllib.urlencode(sensor_31_config)
        self.tools._api_testee('set_virtual_sensor?{0}'.format(url_params), self.token, expected_failure=False)

        thermostat_config = {
            "auto_wed": [
                self.NIGHT_TEMP_INIT + 3,
                "08:00",
                "10:00",
                self.DAY_BLOCK1_INIT + 3,
                "16:00",
                "20:00",
                self.DAY_BLOCK2_INIT + 3
            ],
            "auto_mon": [
                self.NIGHT_TEMP_INIT,
                "08:00",
                "10:00",
                self.DAY_BLOCK1_INIT,
                "16:00",
                "20:00",
                self.DAY_BLOCK2_INIT
            ],
            "output0": 0,
            "output1": 255,
            "permanent_manual": False,
            "id": 0,
            "auto_sat": [
                self.NIGHT_TEMP_INIT + 7.5,
                "08:00",
                "10:00",
                self.DAY_BLOCK1_INIT + 7.5,
                "16:00",
                "20:00",
                self.DAY_BLOCK2_INIT + 7.5
            ],
            "name": "HT0",
            "sensor": 31,
            "auto_sun": [
                self.NIGHT_TEMP_INIT + 9,
                "08:00",
                "10:00",
                self.DAY_BLOCK1_INIT + 9,
                "16:00",
                "20:00",
                self.DAY_BLOCK2_INIT + 9
            ],
            "auto_thu": [
                self.NIGHT_TEMP_INIT + 4.5,
                "08:00",
                "10:00",
                self.DAY_BLOCK1_INIT + 4.5,
                "16:00",
                "20:00",
                self.DAY_BLOCK2_INIT + 4.5
            ],
            "pid_int": 255,
            "auto_tue": [
                self.NIGHT_TEMP_INIT + 1.5,
                "08:00",
                "10:00",
                self.DAY_BLOCK1_INIT + 1.5,
                "16:00",
                "20:00",
                self.DAY_BLOCK2_INIT + 1.5
            ],
            "setp0": self.NIGHT_TEMP_INIT + 10.5,  # Auto night
            "setp5": self.NIGHT_TEMP_INIT + 15,  # Party
            "setp4": self.NIGHT_TEMP_INIT + 13.5,  # Vacation
            "pid_p": 255,
            "setp1": self.DAY_BLOCK1_INIT + 10.5,  # Auto day block 1
            "room": 255,
            "setp3": self.NIGHT_TEMP_INIT + 12,  # Away
            "setp2": self.DAY_BLOCK2_INIT + 10.5,  # Auto day block 2
            "auto_fri": [
                self.NIGHT_TEMP_INIT + 6,
                "08:00",
                "10:00",
                self.DAY_BLOCK1_INIT + 6,
                "16:00",
                "20:00",
                self.DAY_BLOCK2_INIT + 6
            ],
            "pid_d": 255,
            "pid_i": 255
        }

        url_params = urllib.urlencode({'config': json.dumps(thermostat_config)})
        self.tools._api_testee('set_thermostat_configuration?{0}'.format(url_params), self.token, expected_failure=False)

        thermostat_auto_config = {'thermostat_on': True, 'automatic': True, 'setpoint': 0, 'cooling_mode': False,
                                  'cooling_on': True}
        url_params = urllib.urlencode(thermostat_auto_config)
        self.tools._api_testee('set_thermostat_mode?{0}'.format(url_params), self.token, expected_failure=False)

        setpoint_config = {'thermostat': 0, 'temperature': 9}
        url_params = urllib.urlencode(setpoint_config)
        self.tools._api_testee('set_current_setpoint?{0}'.format(url_params), self.token, expected_failure=False)

        response_json = self.tools._api_testee('get_thermostat_status', self.token, expected_failure=False)

        self.assertTrue(response_json.get('automatic', False) is True and response_json.get('setpoint', 99) == 0 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set. Got: {0}".format(response_json))

        response_json = self.tools._api_testee('reset_master', self.token, expected_failure=False)
        self.assertTrue(response_json.get('status', 'Failed') == 'OK', "Should successfully reset the master. Got: {0}".format(response_json))

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools._get_new_token('openmotics', '123456')
            response_json = self.tools._api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                    continue
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)
                continue

        self.assertTrue(response_json.get('automatic', False) is True and response_json.get('setpoint', 99) == 0 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set after resetting the master. Got: {0}".format(response_json))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools._get_new_token('openmotics', '123456')
            response_json = self.tools._api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                    continue
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)
                continue
        self.assertTrue(response_json.get('automatic', False) is True and response_json.get('setpoint', 99) == 0 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat auto config that has been set after a full power cycle. Got: {0}".format(response_json))

        # Testing the mode persistence after reset

        thermostat_auto_config = {'thermostat_on': True, 'automatic': False, 'setpoint': 5, 'cooling_mode': False, 'cooling_on': True}
        url_params = urllib.urlencode(thermostat_auto_config)
        self.tools._api_testee('set_thermostat_mode?{0}'.format(url_params), new_token, expected_failure=False)

        response_json = self.tools._api_testee('get_thermostat_status', new_token, expected_failure=False)

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config. Got: {0}".format(response_json))

        self.tools._api_testee('reset_master', new_token, expected_failure=False)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools._get_new_token('openmotics', '123456')
            response_json = self.tools._api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                    continue
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)
                continue

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config after resetting the master. Got: {0}".format(response_json))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools._get_new_token('openmotics', '123456')
            response_json = self.tools._api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                    continue
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)
                continue

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == self.NIGHT_TEMP_INIT + 15, "Should return a thermostat status according to the thermostat party config after a full power cycle. Got: {0}".format(response_json))

        setpoint_config = {'thermostat': 0, 'temperature': 9}
        url_params = urllib.urlencode(setpoint_config)
        self.tools._api_testee('set_current_setpoint?{0}'.format(url_params), self.token, expected_failure=False)

        self.tools._api_testee('reset_master', new_token, expected_failure=False)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools._get_new_token('openmotics', '123456')
            response_json = self.tools._api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                    continue
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)
                continue

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat configuration with the new settings after resetting the master. Got: {0}".format(response_json))

        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=False)
        time.sleep(0.5)
        self.webinterface.set_output(id=self.TESTEE_POWER, is_on=True)

        start = time.time()
        while time.time() - start < self.tools.TIMEOUT:
            new_token = self.tools._get_new_token('openmotics', '123456')
            response_json = self.tools._api_testee('get_thermostat_status', new_token, expected_failure=True)
            if response_json != "invalid_token":
                if response_json.get('success') is False:
                    time.sleep(0.3)
                    continue
                elif response_json.get('success') is True:
                    break
            else:
                time.sleep(0.3)
                continue

        self.assertTrue(response_json.get('automatic', True) is False and response_json.get('setpoint', 99) == 5 and response_json.get('status')[0].get('csetp') == 9, "Should return a thermostat status according to the thermostat configuration with the new settings after a full power cycle. Got: {0}".format(response_json))
