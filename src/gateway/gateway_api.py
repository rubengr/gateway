# Copyright (C) 2016 OpenMotics BV
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
The GatewayApi defines high level functions, these are used by the interface
and call the master_api to complete the actions.
"""

import os
import time
import threading
import datetime
import math
import sqlite3
import constants
import logging
import glob
import shutil
import subprocess
import tempfile
import ConfigParser
import ujson as json
from ioc import Injectable, Inject, INJECTED, Singleton
from subprocess import check_output
from threading import Timer, Thread
from platform_utils import Platform
from serial_utils import CommunicationTimedOutException
from gateway.observer import Observer
from gateway.maintenance_communicator import InMaintenanceModeException
from master import master_api
from power import power_api
from master.eeprom_controller import EepromAddress
from master.eeprom_models import SensorConfiguration, GroupActionConfiguration, \
    ScheduledActionConfiguration, StartupActionConfiguration, \
    ShutterConfiguration, ShutterGroupConfiguration, DimmerConfiguration, \
    CanLedConfiguration, RoomConfiguration
from bus.om_bus_events import OMBusEvents

logger = logging.getLogger('openmotics')


def convert_nan(number):
    """ Convert nan to 0. """
    if math.isnan(number):
        logger.warning('Got an unexpected NaN')
    return 0.0 if math.isnan(number) else number


def check_basic_action(ret_dict):
    """ Checks if the response is 'OK', throws a ValueError otherwise. """
    if ret_dict['resp'] != 'OK':
        raise ValueError('Basic action did not return OK.')


@Injectable.named('gateway_api')
@Singleton
class GatewayApi(object):
    """ The GatewayApi combines master_api functions into high level functions. """

    @Inject
    def __init__(self,
                 master_communicator=INJECTED, master_controller=INJECTED, power_communicator=INJECTED,
                 power_controller=INJECTED, eeprom_controller=INJECTED, pulse_controller=INJECTED,
                 message_client=INJECTED, observer=INJECTED, configuration_controller=INJECTED, shutter_controller=INJECTED):
        """
        :param master_communicator: Master communicator
        :type master_communicator: master.master_communicator.MasterCommunicator
        :param master_controller: Master controller
        :type master_controller: gateway.hal.master_controller.MasterController
        :param power_communicator: Power communicator
        :type power_communicator: power.power_communicator.PowerCommunicator
        :param power_controller: Power controller
        :type power_controller: power.power_controller.PowerController
        :param eeprom_controller: EEPROM controller
        :type eeprom_controller: master.eeprom_controller.EepromController
        :param pulse_controller: Pulse controller
        :type pulse_controller: gateway.pulses.PulseCounterController
        :param message_client: Om Message Client
        :type message_client: bus.om_bus_client.MessageClient
        :param observer: Observer
        :type observer: gateway.observer.Observer
        :param configuration_controller: Configuration controller
        :type configuration_controller: gateway.config.ConfigurationController
        :param shutter_controller: Shutter Controller
        :type shutter_controller: gateway.shutters.ShutterController
        """
        self.__master_communicator = master_communicator
        self.__master_controller = master_controller
        self.__config_controller = configuration_controller
        self.__eeprom_controller = eeprom_controller
        self.__power_communicator = power_communicator
        self.__power_controller = power_controller
        self.__pulse_controller = pulse_controller
        self.__plugin_controller = None
        self.__message_client = message_client
        self.__observer = observer
        self.__shutter_controller = shutter_controller

        self.__discover_mode_timer = None

        self.__module_log = []

        self.__previous_on_outputs = set()

        if Platform.get_platform() == Platform.Type.CLASSIC:
            from master.master_communicator import BackgroundConsumer
            self.__master_communicator.register_consumer(
                BackgroundConsumer(master_api.module_initialize(), 0, self.__update_modules)
            )
            self.__master_communicator.register_consumer(
                BackgroundConsumer(master_api.event_triggered(), 0, self.__event_triggered, True)
            )

        self.__master_checker_thread = Thread(target=self.__master_checker)
        self.__master_checker_thread.daemon = True

    def start(self):
        if Platform.get_platform() == Platform.Type.CLASSIC:
            self.__master_checker_thread.start()

    def set_plugin_controller(self, plugin_controller):
        """
        Set the plugin controller.
        :param plugin_controller: Plugin controller
        :type plugin_controller: plugins.base.PluginController
        """
        self.__plugin_controller = plugin_controller

    def master_online_event(self, online):
        if online:
            self.__shutter_controller.update_config(self.get_shutter_configurations())

    def __master_checker(self):
        """
        Validates certain master settings such as time and whether e.g. events are enabled. It will try to correct all
        unexpected values
        """
        last_communication_check = 0
        last_master_time_check = 0
        last_master_settings_check = 0
        while True:
            try:
                now = time.time()
                if last_communication_check < now - 60:
                    self.__check_master_communications()
                    last_communication_check = now
                if last_master_time_check < now - 300:
                    self.__validate_master_time()
                    last_master_time_check = now
                if last_master_settings_check < now - 900:
                    self.__check_master_settings()
                    last_master_settings_check = now
                time.sleep(5)
            except CommunicationTimedOutException:
                logger.error('Got communication timeout while checking the master.')
                time.sleep(60)
            except InMaintenanceModeException:
                # This is an expected situation
                time.sleep(10)
            except Exception as ex:
                logger.exception('Got unexpected exception while checking the master: {0}'.format(ex))
                time.sleep(60)

    def __check_master_communications(self):
        communication_recovery = self.__config_controller.get_setting('communication_recovery', {})
        calls_timedout = self.__master_communicator.get_communication_statistics()['calls_timedout']
        calls_succeeded = self.__master_communicator.get_communication_statistics()['calls_succeeded']
        all_calls = sorted(calls_timedout + calls_succeeded)

        if len(calls_timedout) == 0:
            # If there are no timeouts at all
            if len(calls_succeeded) > 30:
                self.__config_controller.remove_setting('communication_recovery')
            return
        if len(all_calls) <= 10:
            # Not enough calls made to have a decent view on what's going on
            return
        if not any(t in calls_timedout for t in all_calls[-10:]):
            # The last X calls are successfull
            return
        calls_last_x_minutes = [t for t in all_calls if t > time.time() - 180]
        ratio = len([t for t in calls_last_x_minutes if t in calls_timedout]) / float(len(calls_last_x_minutes))
        if ratio < 0.25:
            # Less than 25% of the calls fail, let's assume everything is just "fine"
            logger.warning('Noticed communication timeouts with the master, but there\'s only a failure ratio of {0:.2f}%.'.format(ratio * 100))
            return

        service_restart = None
        master_reset = None
        backoff = 300
        # There's no successful communication.
        if len(communication_recovery) == 0:
            service_restart = 'communication_errors'
        else:
            last_service_restart = communication_recovery.get('service_restart')
            if last_service_restart is None:
                service_restart = 'communication_errors'
            else:
                backoff = last_service_restart['backoff']
                if last_service_restart['time'] < time.time() - backoff:
                    service_restart = 'communication_errors'
                    backoff = min(1200, backoff * 2)
                else:
                    last_master_reset = communication_recovery.get('master_reset')
                    if last_master_reset is None or last_master_reset['time'] < last_service_restart['time']:
                        master_reset = 'communication_errors'

        if service_restart is not None or master_reset is not None:
            # Log debug information
            try:
                debug_buffer = self.__master_communicator.get_debug_buffer()
                debug_data = {'type': 'communication_recovery',
                              'data': {'buffer': debug_buffer,
                                       'calls': {'timedout': calls_timedout,
                                                 'succeeded': calls_succeeded},
                                       'action': 'service_restart' if service_restart is not None else 'master_reset'}}
                with open('/tmp/debug_{0}.json'.format(int(time.time())), 'w') as recovery_file:
                    json.dump(debug_data, fp=recovery_file, indent=4, sort_keys=True)
                check_output("ls -tp /tmp/ | grep 'debug_.*json' | tail -n +10 | while read file; do rm -r /tmp/$file; done", shell=True)
            except Exception as ex:
                logger.error('Could not store debug file: {0}'.format(ex))

        if service_restart is not None:
            logger.fatal('Major issues in communication with master. Restarting service...')
            communication_recovery['service_restart'] = {'reason': service_restart,
                                                         'time': time.time(),
                                                         'backoff': backoff}
            self.__config_controller.set_setting('communication_recovery', communication_recovery)
            time.sleep(15)  # Wait a tad for the I/O to complete (both for DB changes as log flushing)
            os._exit(1)
        if master_reset is not None:
            logger.fatal('Major issues in communication with master. Resetting master & service')
            communication_recovery['master_reset'] = {'reason': master_reset,
                                                      'time': time.time()}
            self.__config_controller.set_setting('communication_recovery', communication_recovery)
            self.reset_master()
            time.sleep(5)  # Waiting for the master to come back online before restarting the service
            os._exit(1)  # TODO: This can be removed once the master communicator can recover "alignment issues"

    def __check_master_settings(self):
        """
        Checks master settings such as:
        * Enable async messages
        * Enable multi-tenancy
        * Enable 32 thermostats
        * Turn on all leds
        """
        eeprom_data = self.__master_communicator.do_command(master_api.eeprom_list(),
                                                            {'bank': 0})['data']
        write = False

        if eeprom_data[11] != chr(255):
            logger.info('Disabling async RO messages.')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 11, 'data': chr(255)}
            )
            write = True

        if eeprom_data[18] != chr(0):
            logger.info('Enabling async OL messages.')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 18, 'data': chr(0)}
            )
            write = True

        if eeprom_data[20] != chr(0):
            logger.info('Enabling async IL messages.')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 20, 'data': chr(0)}
            )
            write = True

        if eeprom_data[28] != chr(0):
            logger.info('Enabling async SO messages.')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 28, 'data': chr(0)}
            )
            write = True

        thermostat_mode = ord(eeprom_data[14])
        if thermostat_mode & 64 == 0:
            logger.info('Enabling multi-tenant thermostats.')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 14, 'data': chr(thermostat_mode | 64)}
            )
            write = True

        if eeprom_data[59] != chr(32):
            logger.info('Enabling 32 thermostats.')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 59, 'data': chr(32)}
            )
            write = True

        if eeprom_data[24] != chr(0):
            logger.info('Disable auto-reset thermostat setpoint')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 24, 'data': chr(0)}
            )
            write = True

        if eeprom_data[13] != chr(0):
            logger.info('Configure master startup mode to: API')
            self.__master_communicator.do_command(
                master_api.write_eeprom(),
                {'bank': 0, 'address': 13, 'data': chr(0)}
            )
            write = True

        if write:
            self.__master_communicator.do_command(master_api.activate_eeprom(), {'eep': 0})
        self.set_master_status_leds(True)

    def __validate_master_time(self):
        """
        Validates the master's time with the Gateway time
        """
        status = self.__master_communicator.do_command(master_api.status())
        master_time = datetime.datetime(1, 1, 1, status['hours'], status['minutes'], status['seconds'])

        now = datetime.datetime.now()
        expected_weekday = now.weekday() + 1
        expected_time = now.replace(year=1, month=1, day=1, microsecond=0)

        sync = False
        if abs((master_time - expected_time).total_seconds()) > 180:  # Allow 3 minutes difference
            sync = True
        if status['weekday'] != expected_weekday:
            sync = True

        if sync is True:
            logger.info('Time - master: {0} ({1}) - gateway: {2} ({3})'.format(
                master_time, status['weekday'], expected_time, expected_weekday)
            )
            if expected_time.hour == 0 and expected_time.minute < 15:
                logger.info('Skip setting time between 00:00 and 00:15')
            else:
                self.sync_master_time()

    def sync_master_time(self):
        """ Set the time on the master. """
        logger.info('Setting the time on the master.')
        now = datetime.datetime.now()
        self.__master_communicator.do_command(
            master_api.set_time(),
            {'sec': now.second, 'min': now.minute, 'hours': now.hour,
             'weekday': now.isoweekday(), 'day': now.day, 'month': now.month,
             'year': now.year % 100}
        )

    def set_timezone(self, timezone):
        _ = self  # Not static for consistency
        timezone_file_path = '/usr/share/zoneinfo/' + timezone
        if not os.path.isfile(timezone_file_path):
            raise RuntimeError('Could not find timezone \'' + timezone + '\'')
        if os.path.exists(constants.get_timezone_file()):
            os.remove(constants.get_timezone_file())
        os.symlink(timezone_file_path, constants.get_timezone_file())

    def get_timezone(self):
        try:
            path = os.path.realpath(constants.get_timezone_file())
            if not path.startswith('/usr/share/zoneinfo/'):
                # Reset timezone to default setting
                self.set_timezone('UTC')
                return 'UTC'
            return path[20:]
        except Exception:
            return 'UTC'

    def __event_triggered(self, ev_output):
        """ Handle an event triggered by the master. """
        code = ev_output['code']

        if self.__plugin_controller is not None:
            self.__plugin_controller.process_event(code)

    def maintenance_mode_stopped(self):
        """ Called when maintenance mode is stopped """
        self.__observer.invalidate_cache()
        self.__eeprom_controller.invalidate_cache()  # Eeprom can be changed in maintenance mode.
        self.__eeprom_controller.dirty = True
        self.__message_client.send_event(OMBusEvents.DIRTY_EEPROM, None)

    def get_status(self):
        # TODO: implement gateway status too (e.g. plugin status)
        return self.__master_controller.get_status()

    def get_master_version(self):
        return self.__master_controller.get_version()

    def get_gateway_version(self):
        """ Gets reported main version """
        _ = self
        config = ConfigParser.ConfigParser()
        config.read(constants.get_config_file())
        return str(config.get('OpenMotics', 'version'))

    def reset_master(self):
        return self.__master_controller.cold_reset()

    # Master module functions

    def __update_modules(self, api_data):
        """ Create a log entry when the MI message is received. """
        module_map = {'O': 'output', 'I': 'input', 'T': 'temperature', 'D': 'dimmer'}
        message_map = {'N': 'New %s module found.',
                       'E': 'Existing %s module found.',
                       'D': 'The %s module tried to register but the registration failed, '
                            'please presse the init button again.'}
        log_level_map = {'N': 'INFO', 'E': 'WARN', 'D': 'ERROR'}

        module_type = module_map.get(api_data['id'][0])
        message = message_map.get(api_data['instr']) % module_type
        log_level = log_level_map.get(api_data['instr'])

        self.__module_log.append((log_level, message))

    def module_discover_start(self, timeout=900):
        """ Start the module discover mode on the master.

        :returns: dict with 'status' ('OK').
        """
        ret = self.__master_communicator.do_command(master_api.module_discover_start())

        if self.__discover_mode_timer is not None:
            self.__discover_mode_timer.cancel()

        self.__discover_mode_timer = Timer(timeout, self.module_discover_stop)
        self.__discover_mode_timer.start()

        self.__module_log = []

        return {'status': ret['resp']}

    def module_discover_stop(self):
        """ Stop the module discover mode on the master.

        :returns: dict with 'status' ('OK').
        """
        if self.__discover_mode_timer is not None:
            self.__discover_mode_timer.cancel()
            self.__discover_mode_timer = None

        ret = self.__master_communicator.do_command(master_api.module_discover_stop())

        self.__module_log = []
        self.__eeprom_controller.invalidate_cache()
        self.__eeprom_controller.dirty = True
        self.__message_client.send_event(OMBusEvents.DIRTY_EEPROM, None)
        self.__observer.invalidate_cache()

        return {'status': ret['resp']}

    def module_discover_status(self):
        """ Gets the status of the module discover mode on the master.

        :returns dict with 'running': True|False
        """
        return {'running': self.__discover_mode_timer is not None}

    def get_module_log(self):
        """ Get the log messages from the module discovery mode. This returns the current log
        messages and clear the log messages.

        :returns: dict with 'log' (list of tuples (log_level, message)).
        """
        (module_log, self.__module_log) = (self.__module_log, [])
        return {'log': module_log}

    def get_modules(self):
        # TODO: do we want to include non-master managed "modules" ? e.g. plugin outputs
        return self.__master_controller.get_modules()

    def get_master_modules_information(self):
        return self.__master_controller.get_modules_information()

    def get_energy_modules_information(self):
        information = {}

        def get_energy_module_type(version):
            if version == power_api.ENERGY_MODULE:
                return 'E'
            if version == power_api.POWER_MODULE:
                return 'P'
            if version == power_api.P1_CONCENTRATOR:
                return 'C'
            return 'U'

        # Energy/power modules
        if self.__power_communicator is not None and self.__power_controller is not None:
            modules = self.__power_controller.get_power_modules().values()
            for module in modules:
                module_address = module['address']
                module_version = module['version']
                raw_version = self.__power_communicator.do_command(module_address, power_api.get_version(module_version))[0]
                version_info = raw_version.split('\x00', 1)[0].split('_')
                firmware_version = '{0}.{1}.{2}'.format(version_info[1], version_info[2], version_info[3])
                information[module_address] = {'type': get_energy_module_type(module['version']),
                                               'firmware': firmware_version,
                                               'address': module_address}
        return information

    def get_modules_information(self):
        """ Gets module information """
        information = {'master': self.get_master_modules_information(),
                       'energy': self.get_energy_modules_information()}
        return information

    def flash_leds(self, led_type, led_id):
        return self.__master_controller.flash_leds(led_type, led_id)

    # Output functions

    def get_outputs_status(self):
        """
        Get a list containing the status of the Outputs.

        :returns: A list is a dicts containing the following keys: id, status, ctimer and dimmer.
        """
        # TODO: work with output controller
        # TODO: implement output controller and let her handle routing to either master or e.g. plugin based outputs
        outputs = self.__observer.get_outputs()
        return [{'id': output['id'],
                 'status': output['status'],
                 'ctimer': output['ctimer'],
                 'dimmer': output['dimmer']}
                for output in outputs]

    def get_output_status(self, output_id):
        """
        Get a list containing the status of the Outputs.

        :returns: A list is a dicts containing the following keys: id, status, ctimer and dimmer.
        """
        # TODO: work with output controller
        # TODO: implement output controller and let her handle routing to either master or e.g. plugin based outputs
        output = self.__observer.get_output(output_id)
        if output is None:
            raise ValueError('Output with id {} does not exist'.format(output_id))
        else:
            return {'id': output['id'],
                    'status': output['status'],
                    'ctimer': output['ctimer'],
                    'dimmer': output['dimmer']}

    def set_output_status(self, output_id, is_on, dimmer=None, timer=None):
        """ Set the status, dimmer and timer of an output.

        :param output_id: The id of the output to set
        :type output_id: int
        :param is_on: Whether the output should be on
        :type is_on: bool
        :param dimmer: The dimmer value to set, None if unchanged
        :type dimmer: int | None
        :param timer: The timer value to set, None if unchanged
        :type timer: int | None
        :returns: emtpy dict.
        """
        # TODO: work with output controller
        # TODO: implement output controller and let her handle routing to either master or e.g. plugin based outputs
        self.__master_controller.set_output(output_id=output_id, state=is_on, dimmer=dimmer, timer=timer)
        return {}

    def set_all_lights_off(self):
        # TODO: work with output controller
        # TODO: also switch other lights (e.g. from plugins)
        return self.__master_controller.set_all_lights_off()

    def set_all_lights_floor_off(self, floor):
        # TODO: work with output controller
        # TODO: also switch other lights (e.g. from plugins)
        return self.__master_controller.set_all_lights_floor_off(floor)

    def set_all_lights_floor_on(self, floor):
        # TODO: work with output controller
        # TODO: also switch other lights (e.g. from plugins)
        return self.__master_controller.set_all_lights_floor_on(floor)

    # Shutter functions

    def get_shutter_status(self):
        """ Get a list containing the status of the Shutters.

        :returns: A list is a dicts containing the following keys: id, status.
        """
        # TODO: work with shutter controller
        return self.__observer.get_shutter_status()

    def do_shutter_down(self, shutter_id, position):
        """
        Make a shutter go down. The shutter stops automatically when the down or specified position is reached

        :param shutter_id: The id of the shutter.
        :type shutter_id: int
        :param position: The desired end position
        :type position: int
        :returns:'status': 'OK'.
        :rtype: dict
        """
        self.__shutter_controller.shutter_down(shutter_id, position)
        return {'status': 'OK'}

    def do_shutter_up(self, shutter_id, position):
        """
        Make a shutter go up. The shutter stops automatically when the up or specified position is reached

        :param shutter_id: The id of the shutter.
        :type shutter_id: int
        :param position: The desired end position
        :type position: int
        :returns:'status': 'OK'.
        :rtype: dict
        """
        self.__shutter_controller.shutter_up(shutter_id, position)
        return {'status': 'OK'}

    def do_shutter_stop(self, shutter_id):
        """
        Make a shutter stop.

        :param shutter_id: The id of the shutter.
        :type shutter_id: Byte
        :returns:'status': 'OK'.
        """
        self.__shutter_controller.shutter_stop(shutter_id)
        return {'status': 'OK'}

    def do_shutter_goto(self, shutter_id, position):
        """
        Make a shutter go to the desired position

        :param shutter_id: The id of the shutter.
        :type shutter_id: int
        :param position: The desired end position
        :type position: int
        :returns:'status': 'OK'.
        :rtype: dict
        """
        self.__shutter_controller.shutter_goto(shutter_id, position)
        return {'status': 'OK'}

    def shutter_report_position(self, shutter_id, position, direction=None):
        """
        Report the actual position of a shutter

        :param shutter_id: The id of the shutter.
        :type shutter_id: int
        :param position: The actual position
        :type position: int
        :param direction: The direction
        :type direction: str
        :returns:'status': 'OK'.
        :rtype: dict
        """
        self.__shutter_controller.report_shutter_position(shutter_id, position, direction)
        return {'status': 'OK'}

    def do_shutter_group_down(self, group_id):
        """ Make a shutter group go down. The shutters stop automatically when the down position is
        reached (after the predefined number of seconds).

        :param group_id: The id of the shutter group.
        :type group_id: Byte
        :returns:'status': 'OK'.
        """
        return self.__shutter_controller.shutter_group_down(group_id)

    def do_shutter_group_up(self, group_id):
        """ Make a shutter group go up. The shutters stop automatically when the up position is
        reached (after the predefined number of seconds).

        :param group_id: The id of the shutter group.
        :type group_id: Byte
        :returns:'status': 'OK'.
        """
        return self.__shutter_controller.shutter_group_up(group_id)

    def do_shutter_group_stop(self, group_id):
        """ Make a shutter group stop.

        :param group_id: The id of the shutter group.
        :type group_id: Byte
        :returns:'status': 'OK'.
        """
        return self.__shutter_controller.shutter_group_stop(group_id)

    # Input functions

    def get_input_status(self):
        """
        Get a list containing the status of the Inputs.
        :returns: A list is a dicts containing the following keys: id, status.
        """
        # TODO: work with input controller
        inputs = self.__observer.get_inputs()
        return [{'id': input_port['id'], 'status': input_port['status']} for input_port in inputs]

    def get_last_inputs(self):
        """ Get the X last pressed inputs during the last Y seconds.
        :returns: a list of tuples (input, output).
        """
        # TODO: work with input controller
        return self.__observer.get_recent()

    # Sensors

    def get_sensor_configuration(self, sensor_id, fields=None):
        """
        Get a specific sensor_configuration defined by its id.

        :param sensor_id: The id of the sensor_configuration
        :type sensor_id: Id
        :param fields: The field of the sensor_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        return self.__master_controller.load_sensor(sensor_id, fields=fields)

    def get_sensor_configurations(self, fields=None):
        """
        Get all sensor_configurations.

        :param fields: The field of the sensor_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        return self.__master_controller.load_sensors(fields=fields)

    def set_sensor_configuration(self, config):
        """
        Set one sensor_configuration.

        :param config: The sensor_configuration to set
        :type config: sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        return self.__master_controller.save_sensor([config])

    def set_sensor_configurations(self, config):
        """
        Set multiple sensor_configurations.

        :param config: The list of sensor_configurations to set
        :type config: list of sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        return self.__master_controller.save_sensors(config)

    def get_sensors_temperature_status(self):
        """ Get the current temperature of all sensors.

        :returns: list with 32 temperatures, 1 for each sensor. None/null if not connected
        """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        values = self.__master_controller.get_sensors_temperature()[:32]
        if len(values) < 32:
            values += [None] * (32 - len(values))
        return values

    def get_sensor_temperature_status(self, sensor_id):
        """ Get the current temperature of all sensors. """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        return self.__master_controller.get_sensor_temperature(sensor_id)

    def get_sensors_humidity_status(self):
        """ Get the current humidity of all sensors. """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        values = self.__master_controller.get_sensors_humidity()[:32]
        if len(values) < 32:
            values += [None] * (32 - len(values))
        return values

    def get_sensors_brightness_status(self):
        """ Get the current brightness of all sensors. """
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        values = self.__master_controller.get_sensors_brightness()[:32]
        if len(values) < 32:
            values += [None] * (32 - len(values))
        return values

    def set_virtual_sensor(self, sensor_id, temperature, humidity, brightness):
        # TODO: work with sensor controller
        # TODO: add other sensors too (e.g. from database <-- plugins)
        """ Set the temperature, humidity and brightness value of a virtual sensor. """
        return self.__master_controller.set_virtual_sensor(sensor_id, temperature, humidity, brightness)

    def add_virtual_output_module(self):
        # TODO: work with output controller
        return self.__master_controller.add_virtual_output_module()

    def add_virtual_dim_module(self):
        # TODO: work with output controller
        return self.__master_controller.add_virtual_dim_module()

    def add_virtual_input_module(self):
        # TODO: work with input controller
        return self.__master_controller.add_virtual_input_module()

    # Basic and group actions

    def do_basic_action(self, action_type, action_number):
        return self.__master_controller.do_basic_action(action_type, action_number)

    def do_group_action(self, group_action_id):
        # TODO: do we need more group actions than just with the master?
        return self.__master_controller.do_group_action(group_action_id)

    # Backup and restore functions

    def get_full_backup(self):
        """
        Get a backup (tar) of the master eeprom, the sqlite databases and the plugins

        :returns: Tar containing multiple files: master.eep, config.db, scheduled.db, power.db,
        eeprom_extensions.db, metrics.db and plugins as a string of bytes.
        """
        _ = self  # Not static for consistency

        def backup_sqlite_db(input_db_path, backup_db_path):
            """ Backup an sqlite db provided the path to the db to backup and the backup db. """
            # Connect to database
            connection = sqlite3.connect(input_db_path)
            cursor = connection.cursor()

            # Lock database before making a backup
            cursor.execute('begin immediate')

            # Make new backup file
            shutil.copyfile(input_db_path, backup_db_path)

            # Unlock database
            connection.rollback()

        tmp_dir = tempfile.mkdtemp()
        tmp_sqlite_dir = '{0}/sqlite'.format(tmp_dir)
        os.mkdir(tmp_sqlite_dir)

        try:
            with open('{0}/master.eep'.format(tmp_sqlite_dir), 'w') as eeprom_file:
                eeprom_file.write(self.get_master_backup())

            for filename, source in {'config.db': constants.get_config_database_file(),
                                     'scheduled.db': constants.get_scheduling_database_file(),
                                     'power.db': constants.get_power_database_file(),
                                     'eeprom_extensions.db': constants.get_eeprom_extension_database_file(),
                                     'metrics.db': constants.get_metrics_database_file(),
                                     'pulse.db': constants.get_pulse_counter_database_file()}.iteritems():
                target = '{0}/{1}'.format(tmp_sqlite_dir, filename)
                backup_sqlite_db(source, target)

            # Backup plugins
            tmp_plugin_dir = '{0}/{1}'.format(tmp_dir, 'plugins')
            tmp_plugin_content_dir = '{0}/{1}'.format(tmp_plugin_dir, 'content')
            tmp_plugin_config_dir = '{0}/{1}'.format(tmp_plugin_dir, 'config')
            os.mkdir(tmp_plugin_dir)
            os.mkdir(tmp_plugin_content_dir)
            os.mkdir(tmp_plugin_config_dir)

            plugin_dir = constants.get_plugin_dir()
            plugins = [name for name in os.listdir(plugin_dir) if os.path.isdir(os.path.join(plugin_dir, name))]
            for plugin in plugins:
                shutil.copytree(plugin_dir + plugin, '{0}/{1}/'.format(tmp_plugin_content_dir, plugin))

            config_files = constants.get_plugin_configfiles()
            for config_file in glob.glob(config_files):
                shutil.copy(config_file, '{0}/'.format(tmp_plugin_config_dir))

            retcode = subprocess.call('cd {0}; tar cf backup.tar *'.format(tmp_dir), shell=True)
            if retcode != 0:
                raise Exception('The backup tar could not be created.')

            with open('{0}/backup.tar'.format(tmp_dir), 'r') as backup_file:
                return backup_file.read()

        finally:
            shutil.rmtree(tmp_dir)

    def restore_full_backup(self, data):
        """
        Restore a full backup containing the master eeprom and the sqlite databases.

        :param data: The backup to restore.
        :type data: Tar containing multiple files: master.eep, config.db, scheduled.db, power.db,
        eeprom_extensions.db, metrics.db and plugins as a string of bytes.
        :returns: dict with 'output' key.
        """
        import glob
        import shutil
        import tempfile
        import subprocess

        tmp_dir = tempfile.mkdtemp()
        tmp_sqlite_dir = '{0}/sqlite'.format(tmp_dir)
        try:
            with open('{0}/backup.tar'.format(tmp_dir), 'wb') as backup_file:
                backup_file.write(data)

            retcode = subprocess.call('cd {0}; tar xf backup.tar'.format(tmp_dir), shell=True)
            if retcode != 0:
                raise Exception('The backup tar could not be extracted.')

            # Check if the sqlite db's are in a folder or not for backwards compatibility
            src_dir = tmp_sqlite_dir if os.path.isdir(tmp_sqlite_dir) else tmp_dir

            with open('{0}/master.eep'.format(src_dir), 'r') as eeprom_file:
                eeprom_content = eeprom_file.read()
                self.master_restore(eeprom_content)

            for filename, target in {'config.db': constants.get_config_database_file(),
                                     'users.db': constants.get_config_database_file(),
                                     'scheduled.db': constants.get_scheduling_database_file(),
                                     'power.db': constants.get_power_database_file(),
                                     'eeprom_extensions.db': constants.get_eeprom_extension_database_file(),
                                     'metrics.db': constants.get_metrics_database_file(),
                                     'pulse.db': constants.get_pulse_counter_database_file()}.iteritems():
                source = '{0}/{1}'.format(src_dir, filename)
                if os.path.exists(source):
                    shutil.copyfile(source, target)

            # Restore the plugins if there are any
            backup_plugin_dir = '{0}/plugins'.format(tmp_dir)
            backup_plugin_content_dir = '{0}/content'.format(backup_plugin_dir)
            backup_plugin_config_files = '{0}/config/pi_*'.format(backup_plugin_dir)

            if os.path.isdir(backup_plugin_dir):
                plugin_dir = constants.get_plugin_dir()
                plugins = [name for name in os.listdir(backup_plugin_content_dir) if os.path.isdir(os.path.join(backup_plugin_content_dir, name))]
                for plugin in plugins:
                    dest_dir = '{0}{1}'.format(plugin_dir, plugin)
                    if os.path.isdir(dest_dir):
                        shutil.rmtree(dest_dir)
                    shutil.copytree('{0}/{1}/'.format(backup_plugin_content_dir, plugin), '{0}{1}'.format(plugin_dir, plugin))

                config_files = constants.get_plugin_config_dir()
                for config_file in glob.glob(backup_plugin_config_files):
                    shutil.copy(config_file, '{0}/'.format(config_files))

            return {'output': 'Restore complete'}

        finally:
            shutil.rmtree(tmp_dir)
            # Restart the Cherrypy server after 1 second. Lets the current request terminate.
            threading.Timer(1, lambda: os._exit(0)).start()

    def factory_reset(self):
        """ Perform a factory reset deleting all sql lite databases and wiping the master eeprom

        :returns: dict with 'output' key.
        """
        import glob
        import shutil
        try:
            self.__master_controller.factory_reset()

            # Delete sql lite databases
            filenames = [constants.get_config_database_file(),
                         constants.get_scheduling_database_file(),
                         constants.get_power_database_file(),
                         constants.get_eeprom_extension_database_file(),
                         constants.get_metrics_database_file(),
                         constants.get_pulse_counter_database_file()]

            for filename in filenames:
                if os.path.exists(filename):
                    os.remove(filename)

            # Delete plugins
            plugin_dir = constants.get_plugin_dir()
            plugins = [name for name in os.listdir(plugin_dir) if os.path.isdir(os.path.join(plugin_dir, name))]
            for plugin in plugins:
                shutil.rmtree(plugin_dir + plugin)

            config_files = constants.get_plugin_configfiles()
            for config_file in glob.glob(config_files):
                os.remove(config_file)

            # reset the master
            self.__master_controller.reset()

            return {'output': 'Factory reset complete'}

        finally:
            # Restart the Cherrypy server after 1 second. Lets the current request terminate.
            threading.Timer(1, lambda: os._exit(0)).start()

    def get_master_backup(self):
        return self.__master_controller.get_backup()

    def master_restore(self, data):
        return self.__master_controller.restore(data)

    # Error functions

    def master_error_list(self):
        """ Get the error list per module (input and output modules). The modules are identified by
        O1, O2, I1, I2, ...

        :returns: dict with 'errors' key, it contains list of tuples (module, nr_errors).
        """
        return self.__master_controller.error_list()

    def master_last_success(self):
        """ Get the number of seconds since the last successful communication with the master.
        """
        return self.__master_controller.last_success()

    def master_clear_error_list(self):
        return self.__master_controller.master_clear_error_list()

    def power_last_success(self):
        """ Get the number of seconds since the last successful communication with the power
        modules.
        """
        if self.__power_communicator is None:
            return 0
        return self.__power_communicator.get_seconds_since_last_success()

    # Status led functions

    def set_master_status_leds(self, status):
        self.__master_controller.set_status_leds(status)

    # Pulse counter functions

    def set_pulse_counter_amount(self, amount):
        """
        Set the number of pulse counters.

        :param amount: The number of pulse counters.
        :type amount: int
        :returns: the number of pulse counters.
        """
        return self.__pulse_controller.set_pulse_counter_amount(amount)

    def get_pulse_counter_status(self):
        """
        Get the pulse counter values.

        :returns: array with the pulse counter values.
        """
        return self.__pulse_controller.get_pulse_counter_status()

    def set_pulse_counter_status(self, pulse_counter_id, value):
        """
        Sets a pulse counter to a value.

        :returns: the updated value of the pulse counter.
        """
        return self.__pulse_controller.set_pulse_counter_status(pulse_counter_id, value)

    def get_pulse_counter_configuration(self, pulse_counter_id, fields=None):
        """
        Get a specific pulse_counter_configuration defined by its id.

        :param pulse_counter_id: The id of the pulse_counter_configuration
        :type pulse_counter_id: Id
        :param fields: The field of the pulse_counter_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: pulse_counter_configuration dict: contains 'id' (Id), 'input' (Byte), 'name' (String[16]), 'room' (Byte)
        """
        return self.__pulse_controller.get_configuration(pulse_counter_id, fields)

    def get_pulse_counter_configurations(self, fields=None):
        """
        Get all pulse_counter_configurations.

        :param fields: The field of the pulse_counter_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of pulse_counter_configuration dict: contains 'id' (Id), 'input' (Byte), 'name' (String[16]), 'room' (Byte)
        """
        return self.__pulse_controller.get_configurations(fields)

    def set_pulse_counter_configuration(self, config):
        """
        Set one pulse_counter_configuration.

        :param config: The pulse_counter_configuration to set
        :type config: pulse_counter_configuration dict: contains 'id' (Id), 'input' (Byte), 'name' (String[16]), 'room' (Byte)
        """
        self.__pulse_controller.set_configuration(config)

    def set_pulse_counter_configurations(self, config):
        """
        Set multiple pulse_counter_configurations.

        :param config: The list of pulse_counter_configurations to set
        :type config: list of pulse_counter_configuration dict: contains 'id' (Id), 'input' (Byte), 'name' (String[16]), 'room' (Byte)
        """
        self.__pulse_controller.set_configurations(config)

    # Below are the auto generated master configuration functions

    def get_output_configuration(self, output_id, fields=None):
        """ Get a specific output_configuration defined by its id. """
        # TODO: work with output controller
        return self.__master_controller.load_output(output_id, fields)

    def get_output_configurations(self, fields=None):
        """ Get all output_configurations. """
        # TODO: work with output controller
        return self.__master_controller.load_outputs(fields)

    def set_output_configuration(self, config):
        """ Set one output_configuration. """
        # TODO: work with output controller
        self.__master_controller.save_outputs([config])

    def set_output_configurations(self, config):
        """ Set multiple output_configurations. """
        # TODO: work with output controller
        self.__master_controller.save_outputs(config)

    def get_shutter_configuration(self, shutter_id, fields=None):
        """
        Get a specific shutter_configuration defined by its id.

        :param shutter_id: The id of the shutter_configuration
        :type shutter_id: Id
        :param fields: The field of the shutter_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: shutter_configuration dict: contains 'id' (Id), 'group_1' (Byte), 'group_2' (Byte), 'name' (String[16]), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte), 'up_down_config' (Byte)
        """
        # TODO: work with shutter controller
        return self.__eeprom_controller.read(ShutterConfiguration, shutter_id, fields).serialize()

    def get_shutter_configurations(self, fields=None):
        """
        Get all shutter_configurations.

        :param fields: The field of the shutter_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of shutter_configuration dict: contains 'id' (Id), 'group_1' (Byte), 'group_2' (Byte), 'name' (String[16]), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte), 'up_down_config' (Byte)
        """
        # TODO: work with shutter controller
        return [o.serialize() for o in self.__eeprom_controller.read_all(ShutterConfiguration, fields)]

    def set_shutter_configuration(self, config):
        """
        Set one shutter_configuration.

        :param config: The shutter_configuration to set
        :type config: shutter_configuration dict: contains 'id' (Id), 'group_1' (Byte), 'group_2' (Byte), 'name' (String[16]), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte), 'up_down_config' (Byte)
        """
        # TODO: work with shutter controller
        self.__eeprom_controller.write(ShutterConfiguration.deserialize(config))
        self.__observer.invalidate_cache(Observer.Types.SHUTTERS)
        self.__shutter_controller.update_config(self.get_shutter_configurations())

    def set_shutter_configurations(self, config):
        """
        Set multiple shutter_configurations.

        :param config: The list of shutter_configurations to set
        :type config: list of shutter_configuration dict: contains 'id' (Id), 'group_1' (Byte), 'group_2' (Byte), 'name' (String[16]), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte), 'up_down_config' (Byte)
        """
        # TODO: work with shutter controller
        self.__eeprom_controller.write_batch([ShutterConfiguration.deserialize(o) for o in config])
        self.__observer.invalidate_cache(Observer.Types.SHUTTERS)
        self.__shutter_controller.update_config(self.get_shutter_configurations())

    def get_shutter_group_configuration(self, group_id, fields=None):
        """
        Get a specific shutter_group_configuration defined by its id.

        :param group_id: The id of the shutter_group_configuration
        :type group_id: Id
        :param fields: The field of the shutter_group_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: shutter_group_configuration dict: contains 'id' (Id), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte)
        """
        # TODO: work with shutter controller
        return self.__eeprom_controller.read(ShutterGroupConfiguration, group_id, fields).serialize()

    def get_shutter_group_configurations(self, fields=None):
        """
        Get all shutter_group_configurations.

        :param fields: The field of the shutter_group_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of shutter_group_configuration dict: contains 'id' (Id), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte)
        """
        # TODO: work with shutter controller
        return [o.serialize() for o in self.__eeprom_controller.read_all(ShutterGroupConfiguration, fields)]

    def set_shutter_group_configuration(self, config):
        """
        Set one shutter_group_configuration.

        :param config: The shutter_group_configuration to set
        :type config: shutter_group_configuration dict: contains 'id' (Id), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte)
        """
        # TODO: work with shutter controller
        self.__eeprom_controller.write(ShutterGroupConfiguration.deserialize(config))

    def set_shutter_group_configurations(self, config):
        """
        Set multiple shutter_group_configurations.

        :param config: The list of shutter_group_configurations to set
        :type config: list of shutter_group_configuration dict: contains 'id' (Id), 'room' (Byte), 'timer_down' (Byte), 'timer_up' (Byte)
        """
        # TODO: work with shutter controller
        self.__eeprom_controller.write_batch([ShutterGroupConfiguration.deserialize(o) for o in config])

    def get_input_configuration(self, input_id, fields=None):
        """ Get a specific input_configuration defined by its id. """
        return self.__master_controller.load_input(input_id, fields)

    def get_input_module_type(self, input_module_id):
        """ Gets the module type for a given Input Module ID """
        return self.__master_controller.get_input_module_type(input_module_id)

    def get_input_configurations(self, fields=None):
        """ Get all input_configurations. """
        return self.__master_controller.load_inputs(fields)

    def set_input_configuration(self, config):
        """ Set one input_configuration. """
        self.__master_controller.save_inputs([config])

    def set_input_configurations(self, config):
        """ Set multiple input_configurations. """
        self.__master_controller.save_inputs(config)

    def get_group_action_configuration(self, group_action_id, fields=None):
        """
        Get a specific group_action_configuration defined by its id.

        :param group_action_id: The id of the group_action_configuration
        :type group_action_id: Id
        :param fields: The field of the group_action_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: group_action_configuration dict: contains 'id' (Id), 'actions' (Actions[16]), 'name' (String[16])
        """
        return self.__eeprom_controller.read(GroupActionConfiguration, group_action_id, fields).serialize()

    def get_group_action_configurations(self, fields=None):
        """
        Get all group_action_configurations.

        :param fields: The field of the group_action_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of group_action_configuration dict: contains 'id' (Id), 'actions' (Actions[16]), 'name' (String[16])
        """
        return [o.serialize() for o in self.__eeprom_controller.read_all(GroupActionConfiguration, fields)]

    def set_group_action_configuration(self, config):
        """
        Set one group_action_configuration.

        :param config: The group_action_configuration to set
        :type config: group_action_configuration dict: contains 'id' (Id), 'actions' (Actions[16]), 'name' (String[16])
        """
        self.__eeprom_controller.write(GroupActionConfiguration.deserialize(config))

    def set_group_action_configurations(self, config):
        """
        Set multiple group_action_configurations.

        :param config: The list of group_action_configurations to set
        :type config: list of group_action_configuration dict: contains 'id' (Id), 'actions' (Actions[16]), 'name' (String[16])
        """
        self.__eeprom_controller.write_batch([GroupActionConfiguration.deserialize(o) for o in config])

    def get_scheduled_action_configuration(self, scheduled_action_id, fields=None):
        """
        Get a specific scheduled_action_configuration defined by its id.

        :param scheduled_action_id: The id of the scheduled_action_configuration
        :type scheduled_action_id: Id
        :param fields: The field of the scheduled_action_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: scheduled_action_configuration dict: contains 'id' (Id), 'action' (Actions[1]), 'day' (Byte), 'hour' (Byte), 'minute' (Byte)
        """
        return self.__eeprom_controller.read(ScheduledActionConfiguration, scheduled_action_id, fields).serialize()

    def get_scheduled_action_configurations(self, fields=None):
        """
        Get all scheduled_action_configurations.

        :param fields: The field of the scheduled_action_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of scheduled_action_configuration dict: contains 'id' (Id), 'action' (Actions[1]), 'day' (Byte), 'hour' (Byte), 'minute' (Byte)
        """
        return [o.serialize() for o in self.__eeprom_controller.read_all(ScheduledActionConfiguration, fields)]

    def set_scheduled_action_configuration(self, config):
        """
        Set one scheduled_action_configuration.

        :param config: The scheduled_action_configuration to set
        :type config: scheduled_action_configuration dict: contains 'id' (Id), 'action' (Actions[1]), 'day' (Byte), 'hour' (Byte), 'minute' (Byte)
        """
        self.__eeprom_controller.write(ScheduledActionConfiguration.deserialize(config))

    def set_scheduled_action_configurations(self, config):
        """
        Set multiple scheduled_action_configurations.

        :param config: The list of scheduled_action_configurations to set
        :type config: list of scheduled_action_configuration dict: contains 'id' (Id), 'action' (Actions[1]), 'day' (Byte), 'hour' (Byte), 'minute' (Byte)
        """
        self.__eeprom_controller.write_batch([ScheduledActionConfiguration.deserialize(o) for o in config])

    def get_startup_action_configuration(self, fields=None):
        """
        Get the startup_action_configuration.

        :param fields: The field of the startup_action_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: startup_action_configuration dict: contains 'actions' (Actions[100])
        """
        return self.__eeprom_controller.read(StartupActionConfiguration, fields).serialize()

    def set_startup_action_configuration(self, config):
        """
        Set the startup_action_configuration.

        :param config: The startup_action_configuration to set
        :type config: startup_action_configuration dict: contains 'actions' (Actions[100])
        """
        self.__eeprom_controller.write(StartupActionConfiguration.deserialize(config))

    def get_dimmer_configuration(self, fields=None):
        """
        Get the dimmer_configuration.

        :param fields: The field of the dimmer_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: dimmer_configuration dict: contains 'dim_memory' (Byte), 'dim_step' (Byte), 'dim_wait_cycle' (Byte), 'min_dim_level' (Byte)
        """
        return self.__eeprom_controller.read(DimmerConfiguration, fields).serialize()

    def set_dimmer_configuration(self, config):
        """
        Set the dimmer_configuration.

        :param config: The dimmer_configuration to set
        :type config: dimmer_configuration dict: contains 'dim_memory' (Byte), 'dim_step' (Byte), 'dim_wait_cycle' (Byte), 'min_dim_level' (Byte)
        """
        self.__eeprom_controller.write(DimmerConfiguration.deserialize(config))

    def get_can_led_configuration(self, can_led_id, fields=None):
        """
        Get a specific can_led_configuration defined by its id.

        :param can_led_id: The id of the can_led_configuration
        :type can_led_id: Id
        :param fields: The field of the can_led_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: can_led_configuration dict: contains 'id' (Id), 'can_led_1_function' (Enum), 'can_led_1_id' (Byte), 'can_led_2_function' (Enum), 'can_led_2_id' (Byte), 'can_led_3_function' (Enum), 'can_led_3_id' (Byte), 'can_led_4_function' (Enum), 'can_led_4_id' (Byte), 'room' (Byte)
        """
        return self.__eeprom_controller.read(CanLedConfiguration, can_led_id, fields).serialize()

    def get_can_led_configurations(self, fields=None):
        """
        Get all can_led_configurations.

        :param fields: The field of the can_led_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of can_led_configuration dict: contains 'id' (Id), 'can_led_1_function' (Enum), 'can_led_1_id' (Byte), 'can_led_2_function' (Enum), 'can_led_2_id' (Byte), 'can_led_3_function' (Enum), 'can_led_3_id' (Byte), 'can_led_4_function' (Enum), 'can_led_4_id' (Byte), 'room' (Byte)
        """
        return [o.serialize() for o in self.__eeprom_controller.read_all(CanLedConfiguration, fields)]

    def set_can_led_configuration(self, config):
        """
        Set one can_led_configuration.

        :param config: The can_led_configuration to set
        :type config: can_led_configuration dict: contains 'id' (Id), 'can_led_1_function' (Enum), 'can_led_1_id' (Byte), 'can_led_2_function' (Enum), 'can_led_2_id' (Byte), 'can_led_3_function' (Enum), 'can_led_3_id' (Byte), 'can_led_4_function' (Enum), 'can_led_4_id' (Byte), 'room' (Byte)
        """
        self.__eeprom_controller.write(CanLedConfiguration.deserialize(config))

    def set_can_led_configurations(self, config):
        """
        Set multiple can_led_configurations.

        :param config: The list of can_led_configurations to set
        :type config: list of can_led_configuration dict: contains 'id' (Id), 'can_led_1_function' (Enum), 'can_led_1_id' (Byte), 'can_led_2_function' (Enum), 'can_led_2_id' (Byte), 'can_led_3_function' (Enum), 'can_led_3_id' (Byte), 'can_led_4_function' (Enum), 'can_led_4_id' (Byte), 'room' (Byte)
        """
        self.__eeprom_controller.write_batch([CanLedConfiguration.deserialize(o) for o in config])

    def get_room_configuration(self, room_id, fields=None):
        """
        Get a specific room_configuration defined by its id.

        :param room_id: The id of the room_configuration
        :type room_id: Id
        :param fields: The field of the room_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: room_configuration dict: contains 'id' (Id), 'floor' (Byte), 'name' (String)
        """
        return self.__eeprom_controller.read(RoomConfiguration, room_id, fields).serialize()

    def get_room_configurations(self, fields=None):
        """
        Get all room_configurations.

        :param fields: The field of the room_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of room_configuration dict: contains 'id' (Id), 'floor' (Byte), 'name' (String)
        """
        return [o.serialize() for o in self.__eeprom_controller.read_all(RoomConfiguration, fields)]

    def set_room_configuration(self, config):
        """
        Set one room_configuration.

        :param config: The room_configuration to set
        :type config: room_configuration dict: contains 'id' (Id), 'floor' (Byte), 'name' (String)
        """
        self.__eeprom_controller.write(RoomConfiguration.deserialize(config))

    def set_room_configurations(self, config):
        """
        Set multiple room_configurations.

        :param config: The list of room_configurations to set
        :type config: list of room_configuration dict: contains 'id' (Id), 'floor' (Byte), 'name' (String)
        """
        self.__eeprom_controller.write_batch([RoomConfiguration.deserialize(o) for o in config])

    # End of auto generated functions

    def get_reset_eeprom_dirty_flag(self):
        dirty = self.__eeprom_controller.dirty
        self.__eeprom_controller.dirty = False
        return dirty

    # Power functions

    def get_power_modules(self):
        """ Get information on the power modules.

        :returns: List of dict depending on the version of the power module. All versions \
        contain 'id', 'name', 'input0', 'input1', 'input2', 'input3', 'input4', 'input5', \
        'input6', 'input7', 'times0', 'times1', 'times2', 'times3', 'times4', 'times5', 'times6', \
        'times7'. For the 8-port power it also contains 'sensor0', 'sensor1', 'sensor2', \
        'sensor3', 'sensor4', 'sensor5', 'sensor6', 'sensor7'. For the 12-port power module also \
        contains 'input8', 'input9', 'input10', 'input11', 'times8', 'times9', 'times10', \
        'times11'.
        """
        if self.__power_controller is None:
            return []

        modules = self.__power_controller.get_power_modules().values()

        def translate_address(_module):
            """ Translate the address from an integer to the external address format (eg. E1). """
            _module['address'] = 'E' + str(_module['address'])
            return _module

        return [translate_address(mod) for mod in modules]

    def set_power_modules(self, modules):
        """ Set information for the power modules.

        :param modules: list of dict depending on the version of the power module. All versions \
        contain 'id', 'name', 'input0', 'input1', 'input2', 'input3', 'input4', 'input5', \
        'input6', 'input7', 'times0', 'times1', 'times2', 'times3', 'times4', 'times5', 'times6', \
        'times7'. For the 8-port power it also contains 'sensor0', 'sensor1', 'sensor2', \
        'sensor3', 'sensor4', 'sensor5', 'sensor6', 'sensor7'. For the 12-port power module also \
        contains 'input8', 'input9', 'input10', 'input11', 'times8', 'times9', 'times10', \
        'times11'.
        :returns: empty dict.
        """
        if self.__power_communicator is None or self.__power_controller is None:
            return {}

        for mod in modules:
            self.__power_controller.update_power_module(mod)

            version = self.__power_controller.get_version(mod['id'])
            addr = self.__power_controller.get_address(mod['id'])
            if version == power_api.POWER_MODULE:
                def _check_sid(key):
                    # 2 = 25A, 3 = 50A
                    if mod[key] in [2, 3]:
                        return mod[key]
                    return 2
                self.__power_communicator.do_command(
                    addr, power_api.set_sensor_types(version),
                    *[_check_sid('sensor{0}'.format(i)) for i in xrange(power_api.NUM_PORTS[version])]
                )
            elif version == power_api.ENERGY_MODULE:
                def _convert_ccf(key):
                    try:
                        if mod[key] == 2:  # 12.5 A
                            return 0.5
                        if mod[key] in [3, 4, 5, 6]:  # 25 A, 50 A, 100 A, 200 A
                            return int(math.pow(2, mod[key] - 3))
                        return mod[key] / 25.0
                    except Exception:
                        # In case of calculation errors, default to 12.5 A
                        return 0.5
                self.__power_communicator.do_command(
                    addr, power_api.set_current_clamp_factor(version),
                    *[_convert_ccf('sensor{0}'.format(i)) for i in xrange(power_api.NUM_PORTS[version])]
                )

                def _convert_sci(key):
                    if key not in mod:
                        return 0
                    return 1 if mod[key] in [True, 1] else 0
                self.__power_communicator.do_command(
                    addr, power_api.set_current_inverse(version),
                    *[_convert_sci('inverted{0}'.format(i)) for i in xrange(power_api.NUM_PORTS[version])]
                )
            else:
                raise ValueError('Unknown power api version')

        return dict()

    def get_realtime_power(self):
        """ Get the realtime power measurement values.

        :returns: dict with the module id as key and the following array as value: \
        [voltage, frequency, current, power].
        """
        output = {}
        if self.__power_communicator is None or self.__power_controller is None:
            return output

        modules = self.__power_controller.get_power_modules()
        for module_id in sorted(modules.keys()):
            try:
                addr = modules[module_id]['address']
                version = modules[module_id]['version']
                num_ports = power_api.NUM_PORTS[version]

                if version == power_api.POWER_MODULE:
                    raw_volt = self.__power_communicator.do_command(addr,
                                                                    power_api.get_voltage(version))
                    raw_freq = self.__power_communicator.do_command(addr,
                                                                    power_api.get_frequency(version))

                    volt = [raw_volt[0] for _ in range(num_ports)]
                    freq = [raw_freq[0] for _ in range(num_ports)]

                elif version == power_api.ENERGY_MODULE:
                    volt = self.__power_communicator.do_command(addr,
                                                                power_api.get_voltage(version))
                    freq = self.__power_communicator.do_command(addr,
                                                                power_api.get_frequency(version))
                else:
                    raise ValueError('Unknown power api version')

                current = self.__power_communicator.do_command(addr,
                                                               power_api.get_current(version))
                power = self.__power_communicator.do_command(addr,
                                                             power_api.get_power(version))

                out = []
                for i in range(num_ports):
                    out.append([convert_nan(volt[i]), convert_nan(freq[i]),
                                convert_nan(current[i]), convert_nan(power[i])])

                output[str(module_id)] = out
            except CommunicationTimedOutException:
                logger.error('Communication timeout while fetching realtime power from {0}: CommunicationTimedOutException'.format(module_id))
            except Exception as ex:
                logger.exception('Got exception while fetching realtime power from {0}: {1}'.format(module_id, ex))

        return output

    def get_total_energy(self):
        """ Get the total energy (kWh) consumed by the power modules.

        :returns: dict with the module id as key and the following array as value: [day, night].
        """
        output = {}
        if self.__power_communicator is None or self.__power_controller is None:
            return output

        modules = self.__power_controller.get_power_modules()
        for module_id in sorted(modules.keys()):
            try:
                addr = modules[module_id]['address']
                version = modules[module_id]['version']

                day = self.__power_communicator.do_command(addr,
                                                           power_api.get_day_energy(version))
                night = self.__power_communicator.do_command(addr,
                                                             power_api.get_night_energy(version))

                out = []
                for i in range(power_api.NUM_PORTS[version]):
                    out.append([convert_nan(day[i]), convert_nan(night[i])])

                output[str(module_id)] = out
            except CommunicationTimedOutException:
                logger.error('Communication timeout while fetching total energy from {0}: CommunicationTimedOutException'.format(module_id))
            except Exception as ex:
                logger.exception('Got exception while fetching total energy from {0}: {1}'.format(module_id, ex))

        return output

    def start_power_address_mode(self):
        """ Start the address mode on the power modules.

        :returns: empty dict.
        """
        if self.__power_communicator is not None:
            self.__power_communicator.start_address_mode()
        return {}

    def stop_power_address_mode(self):
        """ Stop the address mode on the power modules.

        :returns: empty dict
        """
        if self.__power_communicator is not None:
            self.__power_communicator.stop_address_mode()
        return dict()

    def in_power_address_mode(self):
        """ Check if the power modules are in address mode

        :returns: dict with key 'address_mode' and value True or False.
        """
        in_address_mode = False
        if self.__power_communicator is not None:
            in_address_mode = self.__power_communicator.in_address_mode()
        return {'address_mode': in_address_mode}

    def set_power_voltage(self, module_id, voltage):
        """ Set the voltage for a given module.

        :param module_id: The id of the power module.
        :param voltage: The voltage to set for the power module.
        :returns: empty dict
        """
        if self.__power_communicator is None or self.__power_controller is None:
            return {}

        addr = self.__power_controller.get_address(module_id)
        version = self.__power_controller.get_version(module_id)
        if version != power_api.ENERGY_MODULE:
            raise ValueError('Unknown power api version')
        self.__power_communicator.do_command(addr, power_api.set_voltage(), voltage)
        return dict()

    def get_energy_time(self, module_id, input_id=None):
        """ Get a 'time' sample of voltage and current

        :returns: dict with input_id and the voltage and cucrrent time samples
        """
        if self.__power_communicator is None or self.__power_controller is None:
            return {}

        addr = self.__power_controller.get_address(module_id)
        version = self.__power_controller.get_version(module_id)
        if version != power_api.ENERGY_MODULE:
            raise ValueError('Unknown power api version')
        if input_id is None:
            input_ids = range(12)
        else:
            input_id = int(input_id)
            if input_id < 0 or input_id > 11:
                raise ValueError('Invalid input_id (should be 0-11)')
            input_ids = [input_id]
        data = {}
        for input_id in input_ids:
            voltage = list(self.__power_communicator.do_command(addr, power_api.get_voltage_sample_time(version), input_id, 0))
            current = list(self.__power_communicator.do_command(addr, power_api.get_current_sample_time(version), input_id, 0))
            for entry in self.__power_communicator.do_command(addr, power_api.get_voltage_sample_time(version), input_id, 1):
                if entry == float('inf'):
                    break
                voltage.append(entry)
            for entry in self.__power_communicator.do_command(addr, power_api.get_current_sample_time(version), input_id, 1):
                if entry == float('inf'):
                    break
                current.append(entry)
            data[str(input_id)] = {'voltage': voltage,
                                   'current': current}
        return data

    def get_energy_frequency(self, module_id, input_id=None):
        """ Get a 'frequency' sample of voltage and current

        :returns: dict with input_id and the voltage and cucrrent frequency samples
        """
        if self.__power_communicator is None or self.__power_controller is None:
            return {}

        addr = self.__power_controller.get_address(module_id)
        version = self.__power_controller.get_version(module_id)
        if version != power_api.ENERGY_MODULE:
            raise ValueError('Unknown power api version')
        if input_id is None:
            input_ids = range(12)
        else:
            input_id = int(input_id)
            if input_id < 0 or input_id > 11:
                raise ValueError('Invalid input_id (should be 0-11)')
            input_ids = [input_id]
        data = {}
        for input_id in input_ids:
            voltage = self.__power_communicator.do_command(addr, power_api.get_voltage_sample_frequency(version), input_id, 20)
            current = self.__power_communicator.do_command(addr, power_api.get_current_sample_frequency(version), input_id, 20)
            # The received data has a length of 40; 20 harmonics entries, and 20 phase entries. For easier usage, the
            # API calls splits them into two parts so the customers doesn't have to do the splitting.
            data[str(input_id)] = {'voltage': [voltage[:20], voltage[20:]],
                                   'current': [current[:20], current[20:]]}
        return data

    def do_raw_energy_command(self, address, mode, command, data):
        """ Perform a raw energy module command, for debugging purposes.

        :param address: The address of the energy module
        :param mode: 1 char: S or G
        :param command: 3 char power command
        :param data: list of bytes
        :returns: list of bytes
        """
        if self.__power_communicator is None:
            return []

        return self.__power_communicator.do_command(address,
                                                    power_api.raw_command(mode, command, len(data)),
                                                    *data)

    def cleanup_eeprom(self):
        """
        Cleans up the EEPROM:
        * Removes 65536 second timeouts
        * Clean memory of non-existing modules
        """
        input_ids = []
        input_ids_can = []
        for config in self.get_input_configurations():
            input_ids.append(config['id'])
            if config['can'] == 'C':
                input_ids_can.append(config['id'])
        for id in xrange(240):
            if id not in input_ids:
                self.set_input_configuration({'id': id,
                                              'name': '',
                                              'basic_actions': '',
                                              'invert': 255,
                                              'module_type': '',
                                              'can': '',
                                              'action': 255,
                                              'room': 255})
        for config in self.get_output_configurations():
            change = False
            if config['timer'] == 65535:
                config['timer'] = 0
                change = True
            for i in [1, 2, 3, 4]:
                if config['can_led_{0}_id'.format(i)] not in input_ids_can and config['can_led_{0}_id'.format(i)] != 255:
                    config['can_led_{0}_id'.format(i)] = 255
                    config['can_led_{0}_function'.format(i)] = 'UNKNOWN'
            if change is True:
                self.set_output_configuration(config)
        for config in self.get_can_led_configurations():
            change = False
            for i in [1, 2, 3, 4]:
                if config['can_led_{0}_id'.format(i)] not in input_ids_can and config['can_led_{0}_id'.format(i)] != 255:
                    config['can_led_{0}_id'.format(i)] = 255
                    config['can_led_{0}_function'.format(i)] = 'UNKNOWN'
                    change = True
            if change is True:
                self.set_can_led_configuration(config)
