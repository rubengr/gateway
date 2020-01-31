# Copyright (C) 2019 OpenMotics BV
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
Module for communicating with the Master
"""
import logging
import time
from threading import Thread
from ioc import Injectable, Inject, INJECTED, Singleton
from gateway.hal.master_controller import MasterController, MasterEvent
from gateway.maintenance_communicator import InMaintenanceModeException
from master_core.core_api import CoreAPI
from master_core.core_communicator import BackgroundConsumer
from master_core.events import Event as MasterCoreEvent
from master_core.errors import Error
from master_core.memory_file import MemoryTypes
from master_core.memory_models import OutputConfiguration, SensorConfiguration
from serial_utils import CommunicationTimedOutException

logger = logging.getLogger("openmotics")


@Injectable.named('master_controller')
@Singleton
class MasterCoreController(MasterController):

    @Inject
    def __init__(self, master_communicator=INJECTED, ucan_communicator=INJECTED, memory_files=INJECTED):
        """
        :type master_communicator: master_core.core_communicator.CoreCommunicator
        :type ucan_communicator: master_core.ucan_communicator.UCANCommunicator
        :type memory_files: dict[master_core.memory_file.MemoryTypes, master_core.memory_file.MemoryFile]
        """
        super(MasterCoreController, self).__init__(master_communicator)
        self._ucan_communicator = ucan_communicator
        self._memory_files = memory_files
        self._synchronization_thread = Thread(target=self._synchronize, name='CoreMasterSynchronization')
        self._master_online = False
        self._output_interval = 600
        self._output_last_updated = 0
        self._output_states = {}
        self._sensor_interval = 300
        self._sensor_last_updated = 0
        self._sensor_states = {}

        self._master_communicator.register_consumer(
            BackgroundConsumer(CoreAPI.event_information(), 0, self._handle_event)
        )
        self._master_communicator.register_consumer(
            BackgroundConsumer(CoreAPI.error_information(), 0, lambda e: logger.info('Got master error: {0}'.format(Error(e))))
        )
        self._master_communicator.register_consumer(
            BackgroundConsumer(CoreAPI.ucan_module_information(), 0, lambda i: logger.info('Got ucan module information: {0}'.format(i)))
        )

    #################
    # Private stuff #
    #################

    def _handle_event(self, data):
        core_event = MasterCoreEvent(data)
        logger.info('Got master event: {0}'.format(core_event))
        if core_event.type == MasterCoreEvent.Types.OUTPUT:
            # Update internal state cache
            self._output_states[core_event.data['output']] = {'id': core_event.data['output'],
                                                              'status': 1 if core_event.data['status'] else 0,
                                                              'ctimer': core_event.data['timer_value'],
                                                              'dimmer': core_event.data['dimmer_value']}
            # Generate generic event
            event = MasterEvent(event_type=MasterEvent.Types.OUTPUT_CHANGE,
                                data={'id': core_event.data['output'],
                                      'status': {'on': core_event.data['status'],
                                                 'value': core_event.data['dimmer_value']},
                                      'location': {'room_id': 255}})  # TODO: Missing room
            for callback in self._event_callbacks:
                callback(event)
        elif core_event.type == MasterCoreEvent.Types.SENSOR:
            sensor_id = core_event.data['sensor']
            if sensor_id not in self._sensor_states:
                return
            self._sensor_states[sensor_id][core_event.data['type']] = core_event.data['value']

    def _synchronize(self):
        while True:
            try:
                # Refresh if required
                if self._output_last_updated + self._output_interval < time.time():
                    self._refresh_output_states()
                    self._set_master_state(True)
                if self._sensor_last_updated + self._sensor_interval < time.time():
                    self._refresh_sensor_states()
                    self._set_master_state(True)
                time.sleep(1)
            except CommunicationTimedOutException:
                logger.error('Got communication timeout during synchronization, waiting 10 seconds.')
                self._set_master_state(False)
                time.sleep(10)
            except InMaintenanceModeException:
                # This is an expected situation
                time.sleep(10)
            except Exception as ex:
                logger.exception('Unexpected error during synchronization: {0}'.format(ex))
                time.sleep(10)

    def _set_master_state(self, online):
        if online != self._master_online:
            self._master_online = online

    #######################
    # Internal management #
    #######################

    def start(self):
        super(MasterCoreController, self).start()
        self._synchronization_thread.start()

    ##############
    # Public API #
    ##############

    def invalidate_caches(self):
        self._output_last_updated = 0

    def get_firmware_version(self):
        return 0, 0, 0  # TODO

    # Memory (eeprom/fram)

    def eeprom_read_page(self, page):
        return self._memory_files[MemoryTypes.EEPROM].read_page(page)

    def fram_read_page(self, page):
        return self._memory_files[MemoryTypes.FRAM].read_page(page)

    # Input

    def get_input_module_type(self, input_module_id):
        return 'i'  # TODO

    def load_input(self, input_id, fields=None):
        return {}  # TODO

    def load_inputs(self, fields=None):
        return []  # TODO

    def save_inputs(self, inputs, fields=None):
        raise NotImplementedError()  # TODO

    # Outputs

    def set_output(self, output_id, state, dimmer=None, timer=None):
        # TODO: Use `dimmer` and `timer`
        _ = dimmer, timer
        action = 1 if state else 0
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 0, 'action': action,
                                                                      'device_nr': output_id,
                                                                      'extra_parameter': 0})

    def toggle_output(self, output_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 0, 'action': 16,
                                                                      'device_nr': output_id,
                                                                      'extra_parameter': 0})

    def load_output(self, output_id, fields=None):
        output = OutputConfiguration(output_id)
        timer = 0
        if output.timer_type == 2:
            timer = output.timer_value
        elif output.timer_type == 1:
            timer = output.timer_value / 10
        data = {'id': output.id,
                'module_type': output.module.device_type,  # TODO: Proper translation
                'name': output.name,
                'timer': timer,  # TODO: Proper calculation
                'floor': 255,
                'type': output.output_type,  # TODO: Proper translation
                'can_led_1_id': 255,
                'can_led_1_function': 'UNKNOWN',
                'can_led_2_id': 255,
                'can_led_2_function': 'UNKNOWN',
                'can_led_3_id': 255,
                'can_led_3_function': 'UNKNOWN',
                'can_led_4_id': 255,
                'can_led_4_function': 'UNKNOWN',
                'room': 255}
        if fields is None:
            return data
        return {field: data[field] for field in fields}

    def load_outputs(self, fields=None):
        amount_output_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['output']
        outputs = []
        for i in xrange(amount_output_modules * 8):
            outputs.append(self.load_output(i, fields))
        return outputs

    def save_outputs(self, outputs, fields=None):
        for output_data in outputs:
            new_data = {'id': output_data['id'],
                        'name': output_data['name']}  # TODO: Rest of the mapping
            output = OutputConfiguration.deserialize(new_data)
            output.save()  # TODO: Batch saving - postpone eeprom activate if relevant for the Core

    def get_output_status(self, output_id):
        return self._output_states.get(output_id)

    def get_output_statuses(self):
        return self._output_states.values()

    def _refresh_output_states(self):
        amount_output_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['output']
        for i in xrange(amount_output_modules * 8):
            state = self._master_communicator.do_command(CoreAPI.output_detail(), {'device_nr': i})
            self._output_states[i] = {'id': i,
                                      'status': state['status'],  # 1 or 0
                                      'ctimer': state['timer'],
                                      'dimmer': state['dimmer']}
        self._output_last_updated = time.time()

    # Shutters

    def shutter_up(self, shutter_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 10, 'action': 1,
                                                                      'device_nr': shutter_id,
                                                                      'extra_parameter': 0})

    def shutter_down(self, shutter_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 10, 'action': 2,
                                                                      'device_nr': shutter_id,
                                                                      'extra_parameter': 0})

    def shutter_stop(self, shutter_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 10, 'action': 0,
                                                                      'device_nr': shutter_id,
                                                                      'extra_parameter': 0})

    # Sensors

    def get_sensor_temperature(self, sensor_id):
        return self._sensor_states.get(sensor_id, {}).get('TEMPERATURE')

    def get_sensors_temperature(self):
        amount_sensor_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['sensor']
        temperatures = []
        for sensor_id in xrange(amount_sensor_modules * 8):
            temperatures.append(self.get_sensor_temperature(sensor_id))
        return temperatures

    def get_sensor_humidity(self, sensor_id):
        return self._sensor_states.get(sensor_id, {}).get('HUMIDITY')

    def get_sensors_humidity(self):
        amount_sensor_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['sensor']
        humidities = []
        for sensor_id in xrange(amount_sensor_modules * 8):
            humidities.append(self.get_sensor_humidity(sensor_id))
        return humidities

    def get_sensor_brightness(self, sensor_id):
        # TODO: This is a lux value and must somehow be converted to legacy percentage
        brightness = self._sensor_states.get(sensor_id, {}).get('BRIGHTNESS')
        if brightness in [None, 65535]:
            return None
        return int(float(brightness) / 65535.0 * 100)

    def get_sensors_brightness(self):
        amount_sensor_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['sensor']
        brightnesses = []
        for sensor_id in xrange(amount_sensor_modules * 8):
            brightnesses.append(self.get_sensor_brightness(sensor_id))
        return brightnesses

    def load_sensor(self, sensor_id, fields=None):
        sensor = SensorConfiguration(sensor_id)
        data = {'id': sensor.id,
                'name': sensor.name,
                'offset': 0,
                'virtual': False,
                'room': 255}
        if fields is None:
            return data
        return {field: data[field] for field in fields}

    def load_sensors(self, fields=None):
        amount_sensor_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['sensor']
        sensors = []
        for i in xrange(amount_sensor_modules * 8):
            sensors.append(self.load_sensor(i, fields))
        return sensors

    def save_sensors(self, sensors):
        for sensor_data in sensors:
            new_data = {'id': sensor_data['id'],
                        'name': sensor_data['name']}  # TODO: Rest of the mapping
            sensor = SensorConfiguration.deserialize(new_data)
            sensor.save()  # TODO: Batch saving - postpone eeprom activate if relevant for the Core

    def _refresh_sensor_states(self):
        amount_sensor_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['sensor']
        for module_nr in xrange(amount_sensor_modules):
            temperature_values = self._master_communicator.do_command(CoreAPI.sensor_temperature_values(), {'module_nr': module_nr})['values']
            brightness_values = self._master_communicator.do_command(CoreAPI.sensor_brightness_values(), {'module_nr': module_nr})['values']
            humidity_values = self._master_communicator.do_command(CoreAPI.sensor_humidity_values(), {'module_nr': module_nr})['values']
            for i in xrange(8):
                sensor_id = module_nr * 8 + i
                self._sensor_states[sensor_id] = {'TEMPERATURE': temperature_values[i],
                                                  'BRIGHTNESS': brightness_values[i],
                                                  'HUMIDITY': humidity_values[i]}
        self._sensor_last_updated = time.time()

    def set_virtual_sensor(self, sensor_id, temperature, humidity, brightness):
        raise NotImplementedError()

    def shutter_group_down(self, group_id):
        raise NotImplementedError()

    def shutter_group_up(self, group_id):
        raise NotImplementedError()

    def add_virtual_output_module(self):
        raise NotImplementedError()

    def add_virtual_dim_module(self):
        raise NotImplementedError()

    def add_virtual_input_module(self):
        raise NotImplementedError()

    def get_status(self):
        raise NotImplementedError()

    def get_version(self):
        raise NotImplementedError()

    def reset(self):
        raise NotImplementedError()

    def get_modules(self):
        raise NotImplementedError()

    def get_modules_information(self):
        raise NotImplementedError()

    def flash_leds(self, led_type, led_id):
        raise NotImplementedError()

    def get_backup(self):
        raise NotImplementedError()

    def restore(self, data):
        raise NotImplementedError()

    def factory_reset(self):
        raise NotImplementedError()

    def error_list(self):
        raise NotImplementedError()

    def last_success(self):
        raise NotImplementedError()

    def clear_error_list(self):
        raise NotImplementedError()

    def set_status_leds(self, status):
        raise NotImplementedError()

    def do_basic_action(self, action_type, action_number):
        raise NotImplementedError()

    def do_group_action(self, group_action_id):
        raise NotImplementedError()

    def set_all_lights_off(self):
        raise NotImplementedError()

    def set_all_lights_floor_off(self):
        raise NotImplementedError()

    def set_all_lights_floor_on(self):
        raise NotImplementedError()
