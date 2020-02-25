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
from exceptions import NotImplementedError

import ujson as json

if False:  # MYPY
    from typing import Any, Callable, Dict, List


class MasterEvent(object):
    """
    MasterEvent object

    Data formats:
    * OUTPUT CHANGE
      {'id': int,                     # Output ID
       'status': {'on': bool,         # On/off
                  'value': int},      # Optional, dimmer value
       'location': {'room_id': int}}  # Room ID
    """

    class Types(object):
        INPUT_CHANGE = 'INPUT_CHANGE'
        OUTPUT_CHANGE = 'OUTPUT_CHANGE'

    def __init__(self, event_type, data):
        self.type = event_type
        self.data = data

    def serialize(self):
        return {'type': self.type,
                'data': self.data}

    def __eq__(self, other):
        # type: (Any) -> bool
        return self.type == other.type \
            and self.data == other.data

    def __repr__(self):
        # type: () -> str
        return '<MasterEvent {} {}>'.format(self.type, self.data)

    def __str__(self):
        return json.dumps(self.serialize())

    @staticmethod
    def deserialize(data):
        return MasterEvent(event_type=data['type'],
                           data=data['data'])


class MasterController(object):

    def __init__(self, master_communicator):
        self._master_communicator = master_communicator
        self._event_callbacks = []  # type: List[Callable[[MasterEvent],None]]

    #######################
    # Internal management #
    #######################

    def start(self):
        self._master_communicator.start()

    def stop(self):
        self._master_communicator.stop()

    def set_plugin_controller(self, plugin_controller):
        raise NotImplementedError()

    #################
    # Subscriptions #
    #################

    def subscribe_event(self, callback):
        self._event_callbacks.append(callback)

    ##############
    # Public API #
    ##############

    # TODO: Currently the objects returned here are classic-format dicts. This needs to be changed to intermediate transport objects

    def invalidate_caches(self):
        raise NotImplementedError()

    def get_firmware_version(self):
        raise NotImplementedError()

    # Memory (eeprom/fram)

    def eeprom_read_page(self, page):
        raise NotImplementedError()

    def fram_read_page(self, page):
        raise NotImplementedError()

    # Input

    def get_input_module_type(self, input_module_id):
        raise NotImplementedError()

    def load_input(self, input_id, fields=None):
        raise NotImplementedError()

    def load_inputs(self, fields=None):
        raise NotImplementedError()

    def save_inputs(self, inputs, fields=None):
        raise NotImplementedError()

    def get_inputs_with_status(self):
        # type: () -> List[Dict[str,Any]]
        raise NotImplementedError()

    def get_recent_inputs(self):
        # type: () -> List[int]
        raise NotImplementedError()

    # Outputs

    def set_output(self, output_id, state, dimmer=None, timer=None):
        raise NotImplementedError()

    def toggle_output(self, output_id):
        raise NotImplementedError()

    def load_output(self, output_id, fields=None):
        raise NotImplementedError()

    def load_outputs(self, fields=None):
        raise NotImplementedError()

    def save_outputs(self, outputs, fields=None):
        raise NotImplementedError()

    def get_output_status(self, output_id):
        raise NotImplementedError()

    def get_output_statuses(self):
        raise NotImplementedError()

    # Shutters

    def shutter_up(self, shutter_id):
        raise NotImplementedError()

    def shutter_down(self, shutter_id):
        raise NotImplementedError()

    def shutter_stop(self, shutter_id):
        raise NotImplementedError()

    def shutter_group_down(self, group_id):
        raise NotImplementedError()

    def shutter_group_up(self, group_id):
        raise NotImplementedError()

    def load_shutter_configuration(self, shutter_id, fields=None):
        # type: (int, Any) -> Dict[str,Any]
        raise NotImplementedError()

    def load_shutter_configurations(self, fields=None):
        # type: (Any) -> List[Dict[str,Any]]
        raise NotImplementedError()

    def save_shutter_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    def save_shutter_configurations(self, config):
        # type: (List[Dict[str,Any]]) -> None
        raise NotImplementedError()

    def load_shutter_group_configuration(self, group_id, fields=None):
        # type: (int, Any) -> Dict[str,Any]
        raise NotImplementedError()

    def load_shutter_group_configurations(self, fields=None):
        # type: (Any) -> List[Dict[str,Any]]
        raise NotImplementedError()

    def save_shutter_group_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    def save_shutter_group_configurations(self, config):
        # type: (List[Dict[str,Any]]) -> None
        raise NotImplementedError()

    # Sensors

    def get_sensor_temperature(self, sensor_id):
        raise NotImplementedError()

    def get_sensors_temperature(self):
        raise NotImplementedError()

    def get_sensor_humidity(self, sensor_id):
        raise NotImplementedError()

    def get_sensors_humidity(self):
        raise NotImplementedError()

    def get_sensor_brightness(self, sensor_id):
        raise NotImplementedError()

    def get_sensors_brightness(self):
        raise NotImplementedError()

    def set_virtual_sensor(self, sensor_id, temperature, humidity, brightness):
        raise NotImplementedError()

    def load_sensor(self, sensor_id, fields=None):
        raise NotImplementedError()

    def load_sensors(self, fields=None):
        raise NotImplementedError()

    def save_sensors(self, config):
        raise NotImplementedError()

    # Virtual modules

    def add_virtual_output_module(self):
        raise NotImplementedError()

    def add_virtual_dim_module(self):
        raise NotImplementedError()

    def add_virtual_input_module(self):
        raise NotImplementedError()

    # Generic

    def get_status(self):
        raise NotImplementedError()

    def reset(self):
        raise NotImplementedError()

    def cold_reset(self):
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

    def sync_time(self):
        # type: () -> None
        raise NotImplementedError()

    def get_configuration_dirty_flag(self):
        # type: () -> bool
        raise NotImplementedError()

    # Module functions

    def module_discover_start(self, timeout):
        # type: (int) -> Dict[str,Any]
        raise NotImplementedError()

    def module_discover_stop(self):
        # type: () -> Dict[str,Any]
        raise NotImplementedError()

    def module_discover_status(self):
        # type: () -> Dict[str,bool]
        raise NotImplementedError()

    def get_module_log(self):
        # type: () -> Dict[str,Any]
        raise NotImplementedError()

    # Error functions

    def error_list(self):
        raise NotImplementedError()

    def last_success(self):
        raise NotImplementedError()

    def clear_error_list(self):
        raise NotImplementedError()

    def set_status_leds(self, status):
        raise NotImplementedError()

    # Actions functions

    def do_basic_action(self, action_type, action_number):
        raise NotImplementedError()

    def do_group_action(self, group_action_id):
        raise NotImplementedError()

    def load_group_action_configuration(self, group_action_id, fields=None):
        # type: (int, Any) -> Dict[str,Any]
        raise NotImplementedError()

    def load_group_action_configurations(self, fields=None):
        # type: (Any) -> List[Dict[str,Any]]
        raise NotImplementedError()

    def save_group_action_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    def save_group_action_configurations(self, config):
        # type: (List[Dict[str,Any]]) -> None
        raise NotImplementedError()

    def load_scheduled_action_configuration(self, scheduled_action_id, fields=None):
        # type: (int, Any) -> Dict[str,Any]
        raise NotImplementedError()

    def load_scheduled_action_configurations(self, fields=None):
        # type: (Any) -> List[Dict[str,Any]]
        raise NotImplementedError()

    def save_scheduled_action_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    def save_scheduled_action_configurations(self, config):
        # type: (List[Dict[str,Any]]) -> None
        raise NotImplementedError()

    def load_startup_action_configuration(self, fields=None):
        # type: (Any) -> Dict[str,Any]
        raise NotImplementedError()

    def save_startup_action_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    # Dimmer functions

    def load_dimmer_configuration(self, fields=None):
        # type: (Any) -> Dict[str,Any]
        raise NotImplementedError()

    def save_dimmer_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    # Can Led functions

    def load_can_led_configuration(self, can_led_id, fields=None):
        # type: (int, Any) -> Dict[str,Any]
        raise NotImplementedError()

    def load_can_led_configurations(self, fields=None):
        # type: (Any) -> List[Dict[str,Any]]
        raise NotImplementedError()

    def save_can_led_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    def save_can_led_configurations(self, config):
        # type: (List[Dict[str,Any]]) -> None
        raise NotImplementedError()

    # Room functions

    def load_room_configuration(self, room_id, fields=None):
        # type: (int, Any) -> Dict[str,Any]
        raise NotImplementedError()

    def load_room_configurations(self, fields=None):
        # type: (Any) -> List[Dict[str,Any]]
        raise NotImplementedError()

    def save_room_configuration(self, config):
        # type: (Dict[str,Any]) -> None
        raise NotImplementedError()

    def save_room_configurations(self, config):
        # type: (List[Dict[str,Any]]) -> None
        raise NotImplementedError()

    # All lights off

    def set_all_lights_off(self):
        raise NotImplementedError()

    def set_all_lights_floor_off(self, floor):
        raise NotImplementedError()

    def set_all_lights_floor_on(self, floor):
        raise NotImplementedError()
