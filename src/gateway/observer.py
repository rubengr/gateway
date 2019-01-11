# Copyright (C) 2018 OpenMotics BVBA
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
The observer module contains logic to observe various states of the system. It keeps track of what is changing
"""

import time
import logging
try:
    import json
except ImportError:
    import simplejson as json
from threading import Thread
from master.master_communicator import BackgroundConsumer, CommunicationTimedOutException
from master.outputs import OutputStatus
from master.shutters import ShutterStatus
from master.thermostats import ThermostatStatus
from master.inputs import InputStatus
from master import master_api
from bus.dbus_events import DBusEvents

LOGGER = logging.getLogger("openmotics")


class Observer(object):
    """
    The Observer gets various (change) events and will also monitor certain datasets to manually detect changes
    """

    class Events(object):
        ON_OUTPUTS = 'ON_OUTPUTS'
        ON_SHUTTER_UPDATE = 'ON_SHUTTER_UPDATE'
        INPUT_TRIGGER = 'INPUT_TRIGGER'

    class Types(object):
        OUTPUTS = 'OUTPUTS'
        THERMOSTATS = 'THERMOSTATS'
        SHUTTERS = 'SHUTTERS'

    def __init__(self, master_communicator, dbus_service):
        """
        :param master_communicator: Master communicator
        :type master_communicator: master.master_communicator.MasterCommunicator
        :param dbus_service: DBusService instance
        :type dbus_service: bus.dbus_service.DBusService
        """
        self._master_communicator = master_communicator
        self._dbus_service = dbus_service
        self._gateway_api = None

        self._subscriptions = {Observer.Events.ON_OUTPUTS: [],
                               Observer.Events.ON_SHUTTER_UPDATE: [],
                               Observer.Events.INPUT_TRIGGER: []}

        self._input_status = InputStatus()
        self._output_status = OutputStatus(on_output_change=self._output_changed)
        self._thermostat_status = ThermostatStatus(on_thermostat_change=self._thermostat_changed)
        self._shutter_status = ShutterStatus()

        self._output_interval = 600
        self._output_last_updated = 0
        self._thermostats_original_interval = 30
        self._thermostats_interval = self._thermostats_original_interval
        self._thermostats_last_updated = 0
        self._thermostats_restore = 0
        self._shutters_interval = 600
        self._shutters_last_updated = 0

        self._thread = Thread(target=self._monitor)
        self._thread.daemon = True

        self._master_communicator.register_consumer(BackgroundConsumer(master_api.output_list(), 0, self._on_output, True))
        self._master_communicator.register_consumer(BackgroundConsumer(master_api.input_list(), 0, self._on_input))
        self._master_communicator.register_consumer(BackgroundConsumer(master_api.shutter_status(), 0, self._on_shutter_update))

    def set_gateway_api(self, gateway_api):
        """
        Sets the Gateway API instance
        :param gateway_api: Gateway API (business logic)
        :type gateway_api: gateway.gateway_api.GatewayApi
        """
        self._gateway_api = gateway_api

    def subscribe(self, event, callback):
        """
        Subscribes a callback to a certain event
        :param event: The event on which to call the callback
        :param callback: The callback to call
        """
        self._subscriptions[event].append(callback)

    def start(self):
        """ Starts the monitoring thread """
        self._ensure_gateway_api()
        self._thread.start()

    def invalidate_cache(self, object_type=None):
        """
        Triggered when an external service knows certain settings might be changed in the background.
        For example: maintenance mode or module discovery
        """
        if object_type is None or object_type == Observer.Types.OUTPUTS:
            self._output_last_updated = 0
        if object_type is None or object_type == Observer.Types.THERMOSTATS:
            self._thermostats_last_updated = 0
        if object_type is None or object_type == Observer.Types.SHUTTERS:
            self._shutters_last_updated = 0

    def increase_interval(self, object_type, interval, window):
        """ Increases a certain interval to a new setting for a given amount of time """
        if object_type == Observer.Types.THERMOSTATS:
            self._thermostats_interval = interval
            self._thermostats_restore = time.time() + window

    def _monitor(self):
        """ Monitors certain system states to detect changes without events """
        while True:
            try:
                # Refresh if required
                if self._thermostats_last_updated + self._thermostats_interval < time.time():
                    self._refresh_thermostats()
                if self._output_last_updated + self._output_interval < time.time():
                    self._refresh_outputs()
                if self._shutters_last_updated + self._shutters_interval < time.time():
                    self._refresh_shutters()
                # Restore interval if required
                if self._thermostats_restore < time.time():
                    self._thermostats_interval = self._thermostats_original_interval
                time.sleep(1)
            except CommunicationTimedOutException:
                LOGGER.error('Got communication timeout during monitoring, waiting 10 seconds.')
                time.sleep(10)
            except Exception as ex:
                LOGGER.exception('Unexpected error during monitoring: {0}'.format(ex))
                time.sleep(10)

    def _ensure_gateway_api(self):
        if self._gateway_api is None:
            raise RuntimeError('The observer has no access to the Gateway API yet')

    # Handle master "events"

    def _on_output(self, data):
        """ Triggers when the master informs us of an Output state change """
        on_outputs = data['outputs']
        # Notify subscribers
        for callback in self._subscriptions[Observer.Events.ON_OUTPUTS]:
            callback(on_outputs)
        # Update status tracker
        self._output_status.partial_update(on_outputs)

    def _on_input(self, data):
        """ Triggers when the master informs us of an Input press """
        # Notify subscribers
        for callback in self._subscriptions[Observer.Events.INPUT_TRIGGER]:
            callback(data)
        # Update status tracker
        self._input_status.add_data((data['input'], data['output']))

    def _on_shutter_update(self, data):
        """ Triggers when the master informs us of an Shutter state change """
        # Update status tracker
        self._shutter_status.update_states(data)
        # Notify subscribers
        for callback in self._subscriptions[Observer.Events.ON_SHUTTER_UPDATE]:
            callback(self._shutter_status.get_states())

    # Outputs

    def get_outputs(self):
        """ Returns a list of Outputs with their status """
        self._ensure_gateway_api()
        return self._output_status.get_outputs()

    def _output_changed(self, output_id):
        """ Executed by the Output Status tracker when an output changed state """
        self._dbus_service.send_event(DBusEvents.OUTPUT_CHANGE, {'id': output_id})

    def _refresh_outputs(self):
        """ Refreshes the Output Status tracker """
        number_of_outputs = self._master_communicator.do_command(master_api.number_of_io_modules())['out'] * 8
        outputs = []
        for i in xrange(number_of_outputs):
            outputs.append(self._master_communicator.do_command(master_api.read_output(), {'id': i}))
        self._output_status.full_update(outputs)
        self._output_last_updated = time.time()

    # Inputs

    def get_input_status(self):
        self._ensure_gateway_api()
        return self._input_status.get_status()

    # Shutters

    def get_shutter_status(self):
        return self._shutter_status.get_states()

    def _refresh_shutters(self):
        """ Refreshes the Shutter status tracker """
        number_of_shutter_modules = self._master_communicator.do_command(master_api.number_of_io_modules())['shutter']
        self._shutter_status.update_config(self._gateway_api.get_shutter_configurations())
        for module_id in xrange(number_of_shutter_modules):
            self._shutter_status.update_states(
                {'module_nr': module_id,
                 'status': self._master_communicator.do_command(master_api.shutter_status(),
                                                                {'module_nr': module_id})['status']}
            )
        self._shutters_last_updated = time.time()

    # Thermostats

    def get_thermostats(self):
        """ Returns thermostat information """
        self._ensure_gateway_api()
        self._refresh_thermostats()  # Always return the latest information
        return self._thermostat_status.get_thermostats()

    def _thermostat_changed(self, thermostat_id):
        """ Executed by the Thermostat Status tracker when an output changed state """
        self._dbus_service.send_event(DBusEvents.THERMOSTAT_CHANGE, {'id': thermostat_id})

    def _refresh_thermostats(self):
        """
        Get basic information about all thermostats and pushes it in to the Thermostat Status tracker
        """
        def get_automatic_setpoint(_mode):
            _automatic = bool(_mode & 1 << 3)
            return _automatic, 0 if _automatic else (_mode & 0b00000111)

        thermostat_info = self._master_communicator.do_command(master_api.thermostat_list())
        thermostat_mode = self._master_communicator.do_command(master_api.thermostat_mode_list())
        aircos = self._master_communicator.do_command(master_api.read_airco_status_bits())
        outputs = self.get_outputs()

        mode = thermostat_info['mode']
        thermostats_on = bool(mode & 1 << 7)
        cooling = bool(mode & 1 << 4)
        automatic, setpoint = get_automatic_setpoint(thermostat_mode['mode0'])

        fields = ['sensor', 'output0', 'output1', 'name']
        if cooling:
            thermostats_config = self._gateway_api.get_cooling_configurations(fields=fields)
        else:
            thermostats_config = self._gateway_api.get_thermostat_configurations(fields=fields)

        thermostats = []
        for thermostat_id in xrange(32):
            config = thermostats_config[thermostat_id]
            if (config['sensor'] <= 31 or config['sensor'] == 240) and config['output0'] <= 240:
                t_mode = thermostat_mode['mode{0}'.format(thermostat_id)]
                t_automatic, t_setpoint = get_automatic_setpoint(t_mode)
                thermostat = {'id': thermostat_id,
                              'act': thermostat_info['tmp{0}'.format(thermostat_id)].get_temperature(),
                              'csetp': thermostat_info['setp{0}'.format(thermostat_id)].get_temperature(),
                              'outside': thermostat_info['outside'].get_temperature(),
                              'mode': t_mode,
                              'automatic': t_automatic,
                              'setpoint': t_setpoint,
                              'name': config['name'],
                              'sensor_nr': config['sensor'],
                              'airco': aircos['ASB{0}'.format(thermostat_id)]}
                for output in [0, 1]:
                    output_nr = config['output{0}'.format(output)]
                    if output_nr < len(outputs) and outputs[output_nr]['status']:
                        thermostat['output{0}'.format(output)] = outputs[output_nr]['dimmer']
                    else:
                        thermostat['output{0}'.format(output)] = 0
                thermostats.append(thermostat)

        self._thermostat_status.full_update({'thermostats_on': thermostats_on,
                                             'automatic': automatic,
                                             'setpoint': setpoint,
                                             'cooling': cooling,
                                             'status': thermostats})
        self._thermostats_last_updated = time.time()