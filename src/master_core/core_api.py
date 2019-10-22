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
Contains the definition of the Core API
"""

from master_core.core_command import CoreCommandSpec
from master_core.fields import ByteField, WordField, ByteArrayField, WordArrayField, LiteralBytesField, AddressField, CharField, PaddingField, VersionField


class CoreAPI(object):

    # Direct control
    # TODO: Use property

    @staticmethod
    def basic_action():
        """ Basic action spec """
        return CoreCommandSpec(instruction='BA',
                               request_fields=[ByteField('type'), ByteField('action'), WordField('device_nr'), WordField('extra_parameter')],
                               response_fields=[ByteField('type'), ByteField('action'), WordField('device_nr'), WordField('extra_parameter')])

    # Events and other messages from Core to Gateway

    @staticmethod
    def event_information():
        """ Event information """
        return CoreCommandSpec(instruction='EV',
                               response_fields=[ByteField('type'), ByteField('action'), WordField('device_nr'), ByteArrayField('data', 4)])

    @staticmethod
    def error_information():
        """ Error information """
        return CoreCommandSpec(instruction='ER',
                               response_fields=[ByteField('type'), ByteField('parameter_a'), WordField('parameter_b'), WordField('parameter_c')])

    # Generic information and configuration

    @staticmethod
    def device_information_list_outputs():
        """ Device information list for output """
        return CoreCommandSpec(instruction='DL',
                               request_fields=[LiteralBytesField(0)],
                               response_fields=[ByteField('type'), ByteArrayField('information', lambda length: length - 1)])

    @staticmethod
    def device_information_list_inputs():
        """ Device information list for inputs """
        return CoreCommandSpec(instruction='DL',
                               request_fields=[LiteralBytesField(1)],
                               response_fields=[ByteField('type'), ByteArrayField('information', lambda length: length - 1)])

    @staticmethod
    def general_configuration_number_of_modules():
        """ Receives general configuration regarding number of modules """
        return CoreCommandSpec(instruction='GC',
                               request_fields=[LiteralBytesField(0)],
                               response_fields=[ByteField('type'), ByteField('output'), ByteField('input'), ByteField('sensor'), ByteField('ucan'), ByteField('ucan_input'), ByteField('ucan_sensor')])

    @staticmethod
    def general_configuration_max_specs():
        """ Receives general configuration regarding maximum specifications (e.g. max number of input modules, max number of basic actions, ...) """
        return CoreCommandSpec(instruction='GC',
                               request_fields=[LiteralBytesField(1)],
                               response_fields=[ByteField('type'), ByteField('output'), ByteField('input'), ByteField('sensor'), ByteField('ucan'), WordField('groups'), WordField('basic_actions'), ByteField('shutters'), ByteField('shutter_groups')])

    @staticmethod
    def module_information():
        """ Receives module information """
        return CoreCommandSpec(instruction='MC',
                               request_fields=[ByteField('module_nr'), ByteField('module_family')],
                               response_fields=[ByteField('module_nr'), ByteField('module_family'), ByteField('module_type'), AddressField('address'), WordField('bus_errors'), ByteField('module_status')])

    # Memory (EEPROM/FRAM) actions

    @staticmethod
    def memory_read():
        """ Reads memory """
        return CoreCommandSpec(instruction='MR',
                               request_fields=[CharField('type'), WordField('page'), ByteField('start'), ByteField('length')],
                               response_fields=[CharField('type'), WordField('page'), ByteField('start'), ByteArrayField('data', lambda length: length - 4)])

    @staticmethod
    def memory_write(length):
        """ Writes memory """
        return CoreCommandSpec(instruction='MW',
                               request_fields=[CharField('type'), WordField('page'), ByteField('start'), ByteArrayField('data', length)],
                               response_fields=[CharField('type'), WordField('page'), ByteField('start'), ByteField('length'), CharField('result')])

    # CAN

    @staticmethod
    def get_amount_of_ucans():
        """ Receives amount of uCAN modules """
        return CoreCommandSpec(instruction='FS',
                               request_fields=[AddressField('cc_address'), LiteralBytesField(0), LiteralBytesField(0)],
                               response_fields=[AddressField('cc_address'), PaddingField(2), ByteField('amount'), PaddingField(2)])

    @staticmethod
    def get_ucan_address():
        """ Receives the uCAN address of a specific uCAN """
        return CoreCommandSpec(instruction='FS',
                               request_fields=[AddressField('cc_address'), LiteralBytesField(1), ByteField('ucan_nr')],
                               response_fields=[AddressField('cc_address'), PaddingField(2), AddressField('ucan_address', 3)])

    @staticmethod
    def ucan_tx_transport_message():
        """ uCAN transport layer packages """
        return CoreCommandSpec(instruction='FM',
                               request_fields=[AddressField('cc_address'), ByteField('nr_can_bytes'), ByteField('sid'), ByteArrayField('payload', 8)],
                               response_fields=[AddressField('cc_address')])

    @staticmethod
    def ucan_rx_transport_message():
        """ uCAN transport layer packages """
        return CoreCommandSpec(instruction='FM',
                               response_fields=[AddressField('cc_address'), ByteField('nr_can_bytes'), ByteField('sid'), ByteArrayField('payload', 8)])

    @staticmethod
    def ucan_module_information():
        """ Receives information from a uCAN module """
        return CoreCommandSpec(instruction='CD',
                               response_fields=[AddressField('ucan_address', 3), WordArrayField('input_links', 6), ByteArrayField('sensor_links', 2), ByteField('sensor_type'), VersionField('version'),
                                               ByteField('bootloader'), CharField('new_indicator'), ByteField('min_led_brightness'), ByteField('max_led_brightness')])
