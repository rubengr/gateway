# Copyright (C) 2016 OpenMotics BVBA
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
The vpn_service asks the OpenMotics cloud it a vpn tunnel should be opened. It starts openvpn
if required. On each check the vpn_service sends some status information about the outputs and
thermostats to the cloud, to keep the status information in the cloud in sync.
"""

from platform_utils import System
System.import_eggs()

import os
import glob
import gobject
import sys
import requests
import time
import subprocess
import traceback
import constants
import threading

from collections import deque
from ConfigParser import ConfigParser
from datetime import datetime
from bus.dbus_service import DBusService
from bus.dbus_events import DBusEvents
from gateway.config import ConfigurationController

try:
    import json
except ImportError:
    import simplejson as json

REBOOT_TIMEOUT = 900
DEFAULT_SLEEP_TIME = 30


class LOGGER(object):
    @staticmethod
    def log(line):
        sys.stdout.write('{0}: {1}\n'.format(datetime.now(), line))
        sys.stdout.flush()


def reboot_gateway():
    """ Reboot the gateway. """
    subprocess.call('sync && reboot', shell=True)


class VpnController(object):
    """ Contains methods to check the vpn status, start and stop the vpn. """

    vpn_service = System.get_vpn_service()
    start_cmd = "systemctl start " + vpn_service + " > /dev/null"
    stop_cmd = "systemctl stop " + vpn_service + " > /dev/null"
    check_cmd = "systemctl is-active " + vpn_service + " > /dev/null"

    def __init__(self):
        self.vpn_connected = False
        gobject.timeout_add_seconds(5, self._vpn_connected)

    @staticmethod
    def start_vpn():
        """ Start openvpn """
        LOGGER.log('Starting VPN')
        return subprocess.call(VpnController.start_cmd, shell=True) == 0

    @staticmethod
    def stop_vpn():
        """ Stop openvpn """
        LOGGER.log('Stopping VPN')
        return subprocess.call(VpnController.stop_cmd, shell=True) == 0

    @staticmethod
    def check_vpn():
        """ Check if openvpn is running """
        return subprocess.call(VpnController.check_cmd, shell=True) == 0

    def _vpn_connected(self):
        """ Checks if the VPN tunnel is connected """
        try:
            route = subprocess.check_output('ip r | grep tun | grep via || true', shell=True).strip()
            if not route:
                return False
            vpn_server = route.split(' ')[0]
            self.vpn_connected = VPNService.ping(vpn_server, verbose=False)
        except Exception as ex:
            LOGGER.log('Exception occured during vpn connectivity test: {0}'.format(ex))
            self.vpn_connected = False
        gobject.timeout_add_seconds(5, self._vpn_connected)


class Cloud(object):
    """ Connects to the cloud """

    def __init__(self, url, dbus_service, config, sleep_time=DEFAULT_SLEEP_TIME):
        self.__url = url
        self.__dbus_service = dbus_service
        self.__last_connect = time.time()
        self.__sleep_time = sleep_time
        self.__config = config

    def call_home(self, extra_data):
        """ Call home reporting our state, and optionally get new settings or other stuff """
        try:
            request = requests.post(self.__url,
                                    data={'extra_data': json.dumps(extra_data)},
                                    timeout=10.0)
            data = json.loads(request.text)

            if 'sleep_time' in data:
                self.__sleep_time = data['sleep_time']
            else:
                self.__sleep_time = DEFAULT_SLEEP_TIME

            if 'configuration' in data:
                for setting, value in data['configuration'].iteritems():
                    self.__config.set_setting(setting, value)

            self.__last_connect = time.time()
            self.__dbus_service.send_event(DBusEvents.CLOUD_REACHABLE, True)
            return {'open_vpn': data['open_vpn'],
                    'success': True}
        except Exception as ex:
            LOGGER.log('Exception occured during check: {0}'.format(ex))
            self.__dbus_service.send_event(DBusEvents.CLOUD_REACHABLE, False)
            return {'open_vpn': True,
                    'success': False}

    def get_sleep_time(self):
        """ Get the time to sleep between two cloud checks. """
        return self.__sleep_time

    def get_last_connect(self):
        """ Get the timestamp of the last connection with the cloud. """
        return self.__last_connect


class Gateway(object):
    """ Class to get the current status of the gateway. """

    def __init__(self, host="127.0.0.1"):
        self.__host = host
        self.__last_pulse_counters = None

    def do_call(self, uri):
        """ Do a call to the webservice, returns a dict parsed from the json returned by the webserver. """
        try:
            request = requests.get("http://" + self.__host + "/" + uri, timeout=15.0)
            return json.loads(request.text)
        except Exception as ex:
            LOGGER.log('Exception during Gateway call: {0}'.format(ex))
            return

    def get_real_time_power(self):
        """ Get the real time power measurements. """
        data = self.do_call("get_realtime_power?token=None")
        if data is not None and data['success']:
            del data['success']
            return data
        return

    def get_pulse_counter_diff(self):
        """ Get the pulse counter differences. """
        data = self.do_call("get_pulse_counter_status?token=None")
        if data is not None and data['success']:
            counters = data['counters']

            if self.__last_pulse_counters is None:
                ret = [0 for _ in xrange(0, 24)]
            else:
                ret = [Gateway.__counter_diff(counters[i], self.__last_pulse_counters[i])
                       for i in xrange(0, 24)]

            self.__last_pulse_counters = counters
            return ret
        return

    @staticmethod
    def __counter_diff(current, previous):
        """ Calculate the diff between two counter values. """
        diff = current - previous
        return diff if diff >= 0 else 65536 - previous + current

    def get_errors(self):
        """ Get the errors on the gateway. """
        data = self.do_call("get_errors?token=None")
        if data:
            if data['errors'] is not None:
                master_errors = sum([error[1] for error in data['errors']])
            else:
                master_errors = 0

            return {'master_errors': master_errors,
                    'master_last_success': data['master_last_success'],
                    'power_last_success': data['power_last_success']}
        return

    def get_local_ip_address(self):
        """ Get the local ip address. """
        _ = self  # Needs to be an instance method
        return System.get_ip_address()


class DataCollector(object):
    """ Defines a function to retrieve data, the period between two collections """

    def __init__(self, fct, period=0):
        """
        Create a collector with a function to call and a period.
        If the period is 0, the collector will be executed on each call.
        """
        self.__function = fct
        self.__period = period
        self.__last_collect = 0

    def __should_collect(self):
        """ Should we execute the collect? """

        return self.__period == 0 or time.time() >= self.__last_collect + self.__period

    def collect(self):
        """ Execute the collect if required, return None otherwise. """
        try:
            if self.__should_collect():
                if self.__period != 0:
                    self.__last_collect = time.time()
                return self.__function()
            else:
                return
        except Exception as ex:
            LOGGER.log('Error while collecting data: {0}'.format(ex))
            traceback.print_exc()
            return


class VPNService(object):
    """ The VPNService contains all logic to be able to send the heartbeat and check whether the VPN should be opened """

    def __init__(self):
        config = ConfigParser()
        config.read(constants.get_config_file())

        self._iterations = 0
        self._last_cycle = 0
        self._cloud_enabled = True
        self._sleep_time = 0
        self._previous_sleep_time = 0
        self._vpn_open = False
        self._debug_data = {}
        self._eeprom_events = deque()
        self._gateway = Gateway()
        self._vpn_controller = VpnController()
        self._config_controller = ConfigurationController(constants.get_config_database_file(), threading.Lock())
        self._dbus_service = DBusService('vpn_service',
                                         event_receiver=self._event_receiver,
                                         get_state=self._check_state)
        self._cloud = Cloud(config.get('OpenMotics', 'vpn_check_url') % config.get('OpenMotics', 'uuid'),
                            self._dbus_service,
                            self._config_controller)

        self._collectors = {'pulses': DataCollector(self._gateway.get_pulse_counter_diff, 60),
                            'power': DataCollector(self._gateway.get_real_time_power),
                            'errors': DataCollector(self._gateway.get_errors, 600),
                            'local_ip': DataCollector(self._gateway.get_local_ip_address, 1800)}

    @staticmethod
    def ping(target, verbose=True):
        """ Check if the target can be pinged. Returns True if at least 1/4 pings was successful. """
        if target is None:
            return False

        # The popen_timeout has been added as a workaround for the hanging subprocess
        # If NTP date changes the time during a execution of a sub process this hangs forever.
        def popen_timeout(command, timeout):
            p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in xrange(timeout):
                time.sleep(1)
                if p.poll() is not None:
                    stdout_data, stderr_data = p.communicate()
                    if p.returncode == 0:
                        return True
                    raise Exception('stdout: {0}, stderr: {1}'.format(stdout_data, stderr_data))
            p.kill()
            return False

        if verbose is True:
            LOGGER.log("Testing ping to {0}".format(target))
        try:
            # Ping returns status code 0 if at least 1 ping is successful
            return popen_timeout(["ping", "-c", "3", target], 10)
        except Exception as ex:
            LOGGER.log("Error during ping: {0}".format(ex))
            return False

    def _get_debug_dumps(self):
        if not self._config_controller.get_setting('cloud_support', False):
            return {}
        found_timestamps = []
        for filename in glob.glob('/tmp/debug_*.json'):
            timestamp = int(filename.replace('/tmp/debug_', '').replace('.json', ''))
            if timestamp not in self._debug_data:
                with open(filename, 'r') as debug_file:
                    self._debug_data[timestamp] = json.load(debug_file)
            found_timestamps.append(timestamp)
        for timestamp in self._debug_data:
            if timestamp not in found_timestamps:
                del self._debug_data[timestamp]
        return self._debug_data

    def _clean_debug_dumps(self):
        for timestamp in self._debug_data:
            filename = '/tmp/debug_{0}.json'.format(timestamp)
            try:
                os.remove(filename)
            except Exception as ex:
                LOGGER.log('Could not remove debug file {0}: {1}'.format(filename, ex))

    @staticmethod
    def _get_gateway():
        """ Get the default gateway. """
        try:
            return subprocess.check_output("ip r | grep '^default via' | awk '{ print $3; }'", shell=True)
        except Exception as ex:
            LOGGER.log("Error during get_gateway: {0}".format(ex))
            return

    def _check_state(self):
        return {'cloud_disabled': not self._cloud_enabled,
                'sleep_time': self._sleep_time,
                'cloud_last_connect': None if self._cloud is None else self._cloud.get_last_connect(),
                'vpn_open': self._vpn_open,
                'last_cycle': self._last_cycle}

    def _event_receiver(self, event, payload):
        _ = payload
        if event == DBusEvents.DIRTY_EEPROM:
            self._eeprom_events.appendleft(True)

    @staticmethod
    def _unload_queue(queue):
        events = []
        try:
            while True:
                events.append(queue.pop())
        except IndexError:
            pass
        return events

    def _set_vpn(self, should_open):
        is_running = VpnController.check_vpn()
        if should_open and not is_running:
            LOGGER.log("opening vpn")
            VpnController.start_vpn()
        elif not should_open and is_running:
            LOGGER.log("closing vpn")
            VpnController.stop_vpn()
        is_running = VpnController.check_vpn()
        self._vpn_open = is_running and self._vpn_controller.vpn_connected
        self._dbus_service.send_event(DBusEvents.VPN_OPEN, self._vpn_open)

    def start(self):
        mainloop = gobject.MainLoop()
        gobject.timeout_add(250, self._check_vpn)
        mainloop.run()

    def _check_vpn(self):
        self._last_cycle = time.time()
        try:
            start_time = time.time()

            # Check whether connection to the Cloud is enabled/disabled
            cloud_enabled = self._config_controller.get_setting('cloud_enabled')
            if cloud_enabled is False:
                self._sleep_time = None
                self._set_vpn(False)
                self._dbus_service.send_event(DBusEvents.VPN_OPEN, False)
                self._dbus_service.send_event(DBusEvents.CLOUD_REACHABLE, False)

                gobject.timeout_add_seconds(DEFAULT_SLEEP_TIME, self._check_vpn)
                return

            call_data = {'events': {}}

            # Events  # TODO: Replace this by websocket events in the future
            dirty_events = VPNService._unload_queue(self._eeprom_events)
            if dirty_events:
                call_data['events']['DIRTY_EEPROM'] = True

            # Collect data to be send to the Cloud
            for collector_name in self._collectors:
                collector = self._collectors[collector_name]
                data = collector.collect()
                if data is not None:
                    call_data[collector_name] = data
            call_data['debug'] = {'dumps': self._get_debug_dumps()}

            # Send data to the cloud and see if the VPN should be opened
            feedback = self._cloud.call_home(call_data)

            if feedback['success']:
                self._clean_debug_dumps()

            if self._iterations > 20 and self._cloud.get_last_connect() < time.time() - REBOOT_TIMEOUT:
                # The cloud is not responding for a while.
                if not VPNService.ping('cloud.openmotics.com') and not VPNService.ping('8.8.8.8') and not VPNService.ping(VPNService._get_gateway()):
                    # Perhaps the BeagleBone network stack is hanging, reboot the gateway
                    # to reset the BeagleBone.
                    reboot_gateway()
            self._iterations += 1
            # Open or close the VPN
            self._set_vpn(feedback['open_vpn'])

            # Getting some sleep
            exec_time = time.time() - start_time
            if exec_time > 1:
                LOGGER.log('Heartbeat took more than 1s to complete: {0:.2f}s'.format(exec_time))
            sleep_time = self._cloud.get_sleep_time()
            if self._previous_sleep_time != sleep_time:
                LOGGER.log('Set sleep interval to {0}s'.format(sleep_time))
                self._previous_sleep_time = sleep_time
            gobject.timeout_add_seconds(sleep_time, self._check_vpn)
        except Exception as ex:
            LOGGER.log("Error during vpn check loop: {0}".format(ex))
            gobject.timeout_add_seconds(1, self._check_vpn)


if __name__ == '__main__':
    LOGGER.log("Starting VPN service")
    vpn_service = VPNService()
    vpn_service.start()
