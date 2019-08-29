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

from master_aio.ucan_command import UCANCommandSpec
from master_aio.fields import LiteralBytesField, AddressField, PaddingField, ByteField, WordField


class UCANAPI(object):

    @staticmethod
    def ping():
        """ Basic action spec """
        return UCANCommandSpec([LiteralBytesField(0, 96), AddressField('ucan_address', 3), LiteralBytesField(0)],
                               'ucan_address',
                               [[[1, 96], [AddressField('ucan_address', 3), PaddingField(1)]]])

    @staticmethod
    def read_ucan_config():
        """ Reads the full uCAN config """
        return UCANCommandSpec([LiteralBytesField(0, 199), AddressField('ucan_address', 3)],
                               'ucan_address',
                               [[[1, 199], [AddressField('ucan_address', 3), ByteField('input_link_0'), ByteField('input_link_1')]],
                                [[2, 199], [AddressField('ucan_address', 3), ByteField('input_link_2'), ByteField('input_link_3')]],
                                [[3, 199], [AddressField('ucan_address', 3), ByteField('input_link_4'), ByteField('input_link_5')]],
                                [[4, 199], [AddressField('ucan_address', 3), ByteField('sensor_link_0'), ByteField('sensor_link_1')]],
                                [[5, 199], [AddressField('ucan_address', 3), ByteField('sensor_type'), ByteField('f1')]],
                                [[6, 199], [AddressField('ucan_address', 3), ByteField('f2'), ByteField('f3')]],
                                [[7, 199], [AddressField('ucan_address', 3), ByteField('bootloader'), ByteField('new_indicator')]],
                                [[8, 199], [AddressField('ucan_address', 3), ByteField('min_led_brightness'), ByteField('max_led_brightness')]],
                                [[9, 199], [AddressField('ucan_address', 3), WordField('adc_input_2')]],
                                [[10, 199], [AddressField('ucan_address', 3), WordField('adc_input_3')]],
                                [[11, 199], [AddressField('ucan_address', 3), WordField('adc_input_4')]],
                                [[12, 199], [AddressField('ucan_address', 3), WordField('adc_input_5')]],
                                [[13, 199], [AddressField('ucan_address', 3), WordField('adc_dc_input')]]])

    @staticmethod
    def set_min_led_brightness():
        """ Sets the minimum brightness for a uCAN led """
        return UCANCommandSpec([LiteralBytesField(0, 246), AddressField('ucan_address', 3), ByteField('brightness')],
                               'ucan_address',
                               [])

    @staticmethod
    def set_max_led_brightness():
        """ Sets the maximum brightness for a uCAN led """
        return UCANCommandSpec([LiteralBytesField(0, 247), AddressField('ucan_address', 3), ByteField('brightness')],
                               'ucan_address',
                               [])
