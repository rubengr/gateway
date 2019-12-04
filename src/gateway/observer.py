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
from wiring import provides, inject, SingletonScope, scope
from threading import Thread
from master.master_communicator import BackgroundConsumer, CommunicationTimedOutException
from gateway.outputs import OutputStatus
from master.thermostats import ThermostatStatus
from gateway.inputs import InputStatus
from master import master_api
from bus.om_bus_events import OMBusEvents


logger = logging.getLogger("openmotics")


class Event(object):
    """
    Event object
    """

    class Types(object):
        INPUT_CHANGE = 'INPUT_CHANGE'
        OUTPUT_CHANGE = 'OUTPUT_CHANGE'
        SHUTTER_CHANGE = 'SHUTTER_CHANGE'
        THERMOSTAT_CHANGE = 'THERMOSTAT_CHANGE'
        THERMOSTAT_GROUP_CHANGE = 'THERMOSTAT_GROUP_CHANGE'
        ACTION = 'ACTION'
        PING = 'PING'
        PONG = 'PONG'

    def __init__(self, event_type, data):
        self.type = event_type
        self.data = data

    def serialize(self):
        return {'type': self.type,
                'data': self.data,
                '_version': 1.0}  # Add version so that event processing code can handle multiple formats

    @staticmethod
    def deserialize(data):
        return Event(event_type=data['type'],
                     data=data['data'])


class Observer(object):
    """
    The Observer gets various (change) events and will also monitor certain datasets to manually detect changes
    """

    class MasterEvents(object):
        ON_OUTPUTS = 'ON_OUTPUTS'
        ON_SHUTTER_UPDATE = 'ON_SHUTTER_UPDATE'
        ON_INPUT_CHANGE = 'INPUT_CHANGE'
        ONLINE = 'ONLINE'

    class Types(object):
        OUTPUTS = 'OUTPUTS'
        THERMOSTATS = 'THERMOSTATS'
        SHUTTERS = 'SHUTTERS'

    @provides('observer')
    @scope(SingletonScope)
    @inject(master_communicator='master_communicator', message_client='message_client', shutter_controller='shutter_controller')
    def __init__(self, master_communicator, message_client, shutter_controller):
        """
        :param master_communicator: Master communicator
        :type master_communicator: master.master_communicator.MasterCommunicator
        :param message_client: MessageClient instance
        :type message_client: bus.om_bus_client.MessageClient
        :param shutter_controller: Shutter Controller
        :type shutter_controller: gateway.shutters.ShutterController
        """
        self._master_communicator = master_communicator
        self._message_client = message_client
        self._gateway_api = None

        self._master_subscriptions = {Observer.MasterEvents.ON_OUTPUTS: [],
                                      Observer.MasterEvents.ON_SHUTTER_UPDATE: [],
                                      Observer.MasterEvents.ON_INPUT_CHANGE: [],
                                      Observer.MasterEvents.ONLINE: []}
        self._event_subscriptions = []

        self._input_status = InputStatus(on_input_change=self._input_changed)
        self._output_status = OutputStatus(on_output_change=self._output_changed)
        self._thermostat_status = ThermostatStatus(on_thermostat_change=self._thermostat_changed,
                                                   on_thermostat_group_change=self._thermostat_group_changed)
        self._shutter_controller = shutter_controller
        self._shutter_controller.set_shutter_changed_callback(self._shutter_changed)

        self._input_interval = 300
        self._input_last_updated = 0
        self._input_config = {}
        self._output_interval = 600
        self._output_last_updated = 0
        self._output_config = {}
        self._thermostats_original_interval = 30
        self._thermostats_interval = self._thermostats_original_interval
        self._thermostats_last_updated = 0
        self._thermostats_restore = 0
        self._thermostats_config = {}
        self._shutters_interval = 600
        self._shutters_last_updated = 0
        self._master_online = False
        self._background_consumers_registered = False
        self._master_version = None

        self._thread = Thread(target=self._monitor)
        self._thread.daemon = True

        self._master_communicator.register_consumer(BackgroundConsumer(master_api.output_list(), 0, self._on_output, True))

    def set_gateway_api(self, gateway_api):
        """
        Sets the Gateway API instance
        :param gateway_api: Gateway API (business logic)
        :type gateway_api: gateway.gateway_api.GatewayApi
        """
        self._gateway_api = gateway_api

    def subscribe_master(self, event, callback):
        """
        Subscribes a callback to a certain event
        :param event: The event on which to call the callback
        :param callback: The callback to call
        """
        self._master_subscriptions[event].append(callback)

    def subscribe_events(self, callback):
        """
        Subscribes a callback to generic events
        :param callback: the callback to call
        """
        self._event_subscriptions.append(callback)

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
                self._check_master_version()
                # Refresh if required
                if self._thermostats_last_updated + self._thermostats_interval < time.time():
                    self._refresh_thermostats()
                    self._set_master_state(True)
                if self._output_last_updated + self._output_interval < time.time():
                    self._refresh_outputs()
                    self._set_master_state(True)
                if self._shutters_last_updated + self._shutters_interval < time.time():
                    self._refresh_shutters()
                    self._set_master_state(True)
                if self._input_last_updated + self._input_interval < time.time():
                    self._refresh_inputs()
                    self._set_master_state(True)
                # Restore interval if required
                if self._thermostats_restore < time.time():
                    self._thermostats_interval = self._thermostats_original_interval
                self._register_background_consumers()
                time.sleep(1)
            except CommunicationTimedOutException:
                logger.error('Got communication timeout during monitoring, waiting 10 seconds.')
                self._set_master_state(False)
                time.sleep(10)
            except Exception as ex:
                logger.exception('Unexpected error during monitoring: {0}'.format(ex))
                time.sleep(10)

    def _ensure_gateway_api(self):
        if self._gateway_api is None:
            raise RuntimeError('The observer has no access to the Gateway API yet')

    def _check_master_version(self):
        if self._master_version is None:
            self._master_version = self._gateway_api.get_master_version()
            self._set_master_state(True)

    def _set_master_state(self, online):
        if online != self._master_online:
            self._master_online = online
            # Notify subscribers
            for callback in self._master_subscriptions[Observer.MasterEvents.ONLINE]:
                callback(online)

    # Handle master "events"

    def _register_background_consumers(self):
        if self._master_version and not self._background_consumers_registered:
            self._master_communicator.register_consumer(BackgroundConsumer(master_api.input_list(self._master_version), 0, self._on_input))
            self._master_communicator.register_consumer(BackgroundConsumer(master_api.shutter_status(self._master_version), 0, self._on_shutter_update))
            self._background_consumers_registered = True

    # Handle master "events"

    def _on_output(self, data):
        """ Triggers when the master informs us of an Output state change """
        on_outputs = data['outputs']
        # Notify subscribers
        for callback in self._master_subscriptions[Observer.MasterEvents.ON_OUTPUTS]:
            callback(on_outputs)
        # Update status tracker
        self._output_status.partial_update(on_outputs)

    def _on_input(self, data):
        """ Triggers when the master informs us of an Input state change """
        # Update status tracker
        self._input_status.set_input(data)
        # Notify subscribers
        for callback in self._master_subscriptions[Observer.MasterEvents.ON_INPUT_CHANGE]:
            callback(data)

    def _on_shutter_update(self, data):
        """ Triggers when the master informs us of an Shutter state change """
        # Update status tracker
        self._shutter_controller.update_from_master_state(data)
        # Notify subscribers
        for callback in self._master_subscriptions[Observer.MasterEvents.ON_SHUTTER_UPDATE]:
            callback(self._shutter_controller.get_states())

    # Outputs

    def get_outputs(self):
        """ Returns a list of Outputs with their status """
        self._ensure_gateway_api()
        return self._output_status.get_outputs()

    def _output_changed(self, output_id, status):
        """ Executed by the Output Status tracker when an output changed state """
        self._message_client.send_event(OMBusEvents.OUTPUT_CHANGE, {'id': output_id})
        for callback in self._event_subscriptions:
            resp_status = {'on': status['on']}
            # 1. only add value to status when handling dimmers
            if self._output_config[output_id]['module_type'] in ['d', 'D']:
                resp_status['value'] = status['value']
            # 2. format response data
            resp_data = {'id': output_id,
                         'status': resp_status,
                         'location': {'room_id': self._output_config[output_id]['room']}}
            callback(Event(event_type=Event.Types.OUTPUT_CHANGE, data=resp_data))

    def _refresh_outputs(self):
        """ Refreshes the Output Status tracker """
        self._output_config = self._gateway_api.get_output_configurations()
        number_of_outputs = self._master_communicator.do_command(master_api.number_of_io_modules())['out'] * 8
        outputs = []
        for i in xrange(number_of_outputs):
            outputs.append(self._master_communicator.do_command(master_api.read_output(), {'id': i}))
        self._output_status.full_update(outputs)
        self._output_last_updated = time.time()

    # Inputs

    def get_inputs(self):
        """ Returns a list of Inputs with their status """
        self._ensure_gateway_api()
        return self._input_status.get_inputs()

    def get_recent(self):
        """ Returns a list of recently changed inputs """
        self._ensure_gateway_api()
        return self._input_status.get_recent()

    def _input_changed(self, input_id, status):
        """ Executed by the Input Status tracker when an input changed state """
        for callback in self._event_subscriptions:
            resp_data = {'id': input_id,
                         'status': status,
                         'location': {'room_id': self._input_config[input_id]['room']}}
            callback(Event(event_type=Event.Types.INPUT_CHANGE, data=resp_data))

    def _refresh_inputs(self):
        """ Refreshes the Input Status tracker """
        self._input_config = self._gateway_api.get_input_configurations()
        try:
            number_of_input_modules = self._master_communicator.do_command(master_api.number_of_io_modules())['in']
            inputs = []
            for i in xrange(number_of_input_modules):
                result = self._master_communicator.do_command(master_api.read_input_module(self._master_version), {'input_module_nr': i})
                module_status = result['input_status']
                # module_status byte contains bits for each individual input, use mask and bitshift to get status
                for n in xrange(8):
                    input_nr = i * 8 + n
                    input_status = module_status & (1 << n) != 0
                    data = {'input': input_nr, 'status': input_status}
                    inputs.append(data)
            self._input_status.full_update(inputs)
        except NotImplementedError as e:
            logger.error('Cannot refresh inputs: {}'.format(e))
        self._input_last_updated = time.time()

    # Shutters

    def get_shutter_status(self):
        return self._shutter_controller.get_states()

    def _shutter_changed(self, shutter_id, shutter_data, shutter_state):
        """ Executed by the Shutter Status tracker when a shutter changed state """
        for callback in self._event_subscriptions:
            callback(Event(event_type=Event.Types.SHUTTER_CHANGE,
                           data={'id': shutter_id,
                                 'status': {'state': shutter_state},
                                 'location': {'room_id': shutter_data['room']}}))

    def _refresh_shutters(self):
        """ Refreshes the Shutter status tracker """
        number_of_shutter_modules = self._master_communicator.do_command(master_api.number_of_io_modules())['shutter']
        self._shutter_controller.update_config(self._gateway_api.get_shutter_configurations())
        for module_id in xrange(number_of_shutter_modules):
            self._shutter_controller.update_from_master_state(
                {'module_nr': module_id,
                 'status': self._master_communicator.do_command(master_api.shutter_status(self._master_version),
                                                                {'module_nr': module_id})['status']}
            )
        self._shutters_last_updated = time.time()

    # Thermostats

    def get_thermostats(self):
        """ Returns thermostat information """
        self._ensure_gateway_api()
        self._refresh_thermostats()  # Always return the latest information
        return self._thermostat_status.get_thermostats()

    def _thermostat_changed(self, thermostat_id, status):
        """ Executed by the Thermostat Status tracker when an output changed state """
        self._message_client.send_event(OMBusEvents.THERMOSTAT_CHANGE, {'id': thermostat_id})
        location = {'room_id': self._thermostats_config[thermostat_id]['room']}
        for callback in self._event_subscriptions:
            callback(Event(event_type=Event.Types.THERMOSTAT_CHANGE,
                           data={'id': thermostat_id,
                                 'status': {'preset': status['preset'],
                                            'current_setpoint': status['current_setpoint'],
                                            'actual_temperature': status['actual_temperature'],
                                            'output_0': status['output_0'],
                                            'output_1': status['output_1']},
                                 'location': location}))

    def _thermostat_group_changed(self, status):
        self._message_client.send_event(OMBusEvents.THERMOSTAT_CHANGE, {'id': None})
        for callback in self._event_subscriptions:
            callback(Event(event_type=Event.Types.THERMOSTAT_GROUP_CHANGE,
                           data={'id': 0,
                                 'status': {'state': status['state'],
                                            'mode': status['mode']},
                                 'location': {}}))

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

        fields = ['sensor', 'output0', 'output1', 'name', 'room']
        if cooling:
            self._thermostats_config = self._gateway_api.get_cooling_configurations(fields=fields)
        else:
            self._thermostats_config = self._gateway_api.get_thermostat_configurations(fields=fields)

        thermostats = []
        for thermostat_id in xrange(32):
            config = self._thermostats_config[thermostat_id]
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
