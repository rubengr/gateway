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
Memory models
"""
from master_core.memory_types import MemoryModelDefinition, GlobalMemoryModelDefinition, MemoryRelation, MemoryByteField, MemoryWordField, MemoryAddressField, MemoryStringField, MemoryVersionField
from master_core.memory_file import MemoryTypes


class GlobalConfiguration(GlobalMemoryModelDefinition):
    number_of_output_modules = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 1))
    number_of_input_modules = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 2))
    number_of_sensor_modules = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 3))
    scan_time_rs485_sensor_modules = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 4))
    number_of_can_inputs = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 5))
    number_of_can_sensors = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 6))
    number_of_ucan_modules = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 7))
    scan_time_rs485_bus = MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 8))
    groupaction_all_outputs_off = MemoryWordField(MemoryTypes.EEPROM, address_spec=(0, 50))
    groupaction_startup = MemoryWordField(MemoryTypes.EEPROM, address_spec=(0, 52))
    groupaction_minutes_changed = MemoryWordField(MemoryTypes.EEPROM, address_spec=(0, 54))
    groupaction_hours_changed = MemoryWordField(MemoryTypes.EEPROM, address_spec=(0, 56))
    groupaction_day_changed = MemoryWordField(MemoryTypes.EEPROM, address_spec=(0, 58))


class OutputModuleConfiguration(MemoryModelDefinition):
    device_type = MemoryStringField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id, 0), length=1)
    address = MemoryAddressField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id, 0))
    firmware_version = MemoryVersionField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id, 4))


class OutputConfiguration(MemoryModelDefinition):
    module = MemoryRelation(OutputModuleConfiguration, id_spec=lambda id: id / 8)
    timer_value = MemoryWordField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id / 8, 7 + id % 8))
    timer_type = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id / 8, 23 + id % 8))
    output_type = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id / 8, 31 + id % 8))
    min_output_level = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id / 8, 39 + id % 8))
    max_output_level = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id / 8, 47 + id % 8))
    output_groupaction_follow = MemoryWordField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id / 8, 55 + (id % 8) * 2))
    name = MemoryStringField(MemoryTypes.EEPROM, address_spec=lambda id: (1 + id / 8, 128 + (id % 8) * 16), length=16)


class InputModuleConfiguration(MemoryModelDefinition):
    device_type = MemoryStringField(MemoryTypes.EEPROM, address_spec=lambda id: (81 + id * 2, 0), length=1)
    address = MemoryAddressField(MemoryTypes.EEPROM, address_spec=lambda id: (81 + id * 2, 0))
    firmware_version = MemoryVersionField(MemoryTypes.EEPROM, address_spec=lambda id: (81 + id * 2, 4))


class InputConfiguration(MemoryModelDefinition):
    module = MemoryRelation(InputModuleConfiguration, id_spec=lambda id: id / 8)
    input_config = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (81 + id * 2, 7 + id))
    name = MemoryStringField(MemoryTypes.EEPROM, address_spec=lambda id: (81 + id * 2, 128 + id * 16), length=16)


class SensorModuleConfiguration(MemoryModelDefinition):
    device_type = MemoryStringField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id, 0), length=1)
    address = MemoryAddressField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id, 0))
    firmware_version = MemoryVersionField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id, 4))


class SensorConfiguration(MemoryModelDefinition):
    module = MemoryRelation(SensorModuleConfiguration, id_spec=lambda id: id / 8)
    temperature_groupaction_follow = MemoryWordField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id / 8, 8 + (id % 8) * 2))
    humidity_groupaction_follow = MemoryWordField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id / 8, 24 + (id % 8) * 2))
    brightness_groupaction_follow = MemoryWordField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id / 8, 40 + (id % 8) * 2))
    aqi_groupaction_follow = MemoryWordField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id / 8, 56 + (id % 8) * 2))
    dali_sensor_id = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id / 8, 72 + (id % 8)))
    name = MemoryStringField(MemoryTypes.EEPROM, address_spec=lambda id: (239 + id / 8, 128 + id * 16), length=16)
