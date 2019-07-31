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
Contains the definition of the AIO API
"""

from aio_command import AIOCommandSpec, ByteField, WordField, ByteArrayField, LiteralBytesField, AddressField, CharField


class AIOAPI(object):

    @staticmethod
    def basic_action():
        """ Basic action spec """
        return AIOCommandSpec('BA',
                              [ByteField('type'), ByteField('action'), WordField('device_nr'), WordField('extra_parameter')],
                              [ByteField('type'), ByteField('action'), WordField('device_nr'), WordField('extra_parameter')])

    @staticmethod
    def event_information():
        """ Event information """
        return AIOCommandSpec('EV',
                              [],  # No request, only a response
                              [ByteField('type'), ByteField('action'), WordField('device_nr'), ByteArrayField('data', 4)])

    @staticmethod
    def error_information():
        """ Error information """
        return AIOCommandSpec('ER',
                              [],  # No request, only a response
                              [ByteField('type'), ByteField('parameter_a'), WordField('parameter_b'), WordField('parameter_c')])

    @staticmethod
    def device_information_list_outputs():
        """ Device information list for output """
        return AIOCommandSpec('DL',
                              [LiteralBytesField(0)],
                              [ByteField('type'), ByteArrayField('information', lambda length: length - 1)])

    @staticmethod
    def device_information_list_inputs():
        """ Device information list for inputs """
        return AIOCommandSpec('DL',
                              [LiteralBytesField(1)],
                              [ByteField('type'), ByteArrayField('information', lambda length: length - 1)])

    @staticmethod
    def general_configuration_number_of_modules():
        """ Receives general configuration regarding number of modules """
        return AIOCommandSpec('GC',
                              [LiteralBytesField(0)],
                              [ByteField('type'), ByteField('output'), ByteField('input'), ByteField('sensor'), ByteField('u_can'), ByteField('can_input'), ByteField('can_sensor')])

    @staticmethod
    def general_configuration_max_specs():
        """ Receives general configuration regarding maximum specifications (e.g. max number of input modules, max number of basic actions, ...) """
        return AIOCommandSpec('GC',
                              [LiteralBytesField(1)],
                              [ByteField('type'), ByteField('output'), ByteField('input'), ByteField('sensor'), ByteField('u_can'), WordField('groups'), WordField('basic_actions')])

    @staticmethod
    def module_information():
        """ Receives module information """
        return AIOCommandSpec('MC',
                              [ByteField('module_nr'), ByteField('module_type')],
                              [ByteField('module_nr'), ByteField('module_type'), AddressField('address'), WordField('bus_errors'), ByteField('module_status')])

    @staticmethod
    def memory_read():
        """ Reads memory """
        return AIOCommandSpec('MR',
                              [CharField('type'), WordField('page'), ByteField('start'), ByteField('length')],
                              [CharField('type'), WordField('page'), ByteField('start'), ByteArrayField('data', lambda length: length - 4)])

    @staticmethod
    def memory_write(length):
        """ Writes memory """
        return AIOCommandSpec('MW',
                              [CharField('type'), WordField('page'), ByteField('start'), ByteArrayField('data', length)],
                              [CharField('type'), WordField('page'), ByteField('start'), ByteField('length'), CharField('result')])
