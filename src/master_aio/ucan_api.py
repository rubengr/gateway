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

from master_aio.ucan_command import UCANCommandSpec, UCANPalletCommandSpec, SID, PalletType, Instruction
from master_aio.fields import AddressField, ByteField, WordField, VersionField, StringField, Int32Field, ByteArrayField


class UCANAPI(object):

    @staticmethod
    def ping(sid=SID.NORMAL_COMMAND):
        """ Basic action spec """
        return UCANCommandSpec(sid=sid,
                               instruction=Instruction(instruction=[0, 96]),
                               identifier=AddressField('ucan_address', 3),
                               request_fields=[ByteField('data')],
                               response_instructions=[Instruction(instruction=[1, 96], checksum_byte=6)],
                               response_fields=[ByteField('data')])

    @staticmethod
    def read_ucan_config():
        """ Reads the full uCAN config """
        return UCANCommandSpec(sid=SID.NORMAL_COMMAND,
                               instruction=Instruction(instruction=[0, 199]),
                               identifier=AddressField('ucan_address', 3),
                               response_instructions=[Instruction(instruction=[i, 199], checksum_byte=7) for i in xrange(1, 14)],
                               response_fields=[ByteField('input_link_0'), ByteField('input_link_1'), ByteField('input_link_2'),
                                                ByteField('input_link_3'), ByteField('input_link_4'), ByteField('input_link_5'),
                                                ByteField('sensor_link_0'), ByteField('sensor_link_1'), ByteField('sensor_type'),
                                                VersionField('firmware_version'), ByteField('bootloader'), ByteField('new_indicator'),
                                                ByteField('min_led_brightness'), ByteField('max_led_brightness'),
                                                WordField('adc_input_2'), WordField('adc_input_3'), WordField('adc_input_4'),
                                                WordField('adc_input_5'), WordField('adc_dc_input')])

    @staticmethod
    def set_min_led_brightness():
        """ Sets the minimum brightness for a uCAN led """
        return UCANCommandSpec(sid=SID.NORMAL_COMMAND,
                               instruction=Instruction(instruction=[0, 246]),
                               identifier=AddressField('ucan_address', 3),
                               request_fields=[ByteField('brightness')])

    @staticmethod
    def set_max_led_brightness():
        """ Sets the maximum brightness for a uCAN led """
        return UCANCommandSpec(sid=SID.NORMAL_COMMAND,
                               instruction=Instruction(instruction=[0, 247]),
                               identifier=AddressField('ucan_address', 3),
                               request_fields=[ByteField('brightness')])

    @staticmethod
    def set_bootloader_timeout(sid=SID.NORMAL_COMMAND):
        """ Sets the bootloader timeout """
        return UCANCommandSpec(sid=sid,
                               instruction=Instruction(instruction=[0, 123]),
                               identifier=AddressField('ucan_address', 3),
                               request_fields=[ByteField('timeout')],
                               response_instructions=[Instruction(instruction=[123, 123], checksum_byte=6)],
                               response_fields=[ByteField('timeout')])

    @staticmethod
    def reset(sid=SID.NORMAL_COMMAND):
        """ Resets the uCAN """
        return UCANCommandSpec(sid=sid,
                               instruction=Instruction(instruction=[0, 94]),
                               identifier=AddressField('ucan_address', 3),
                               response_instructions=[Instruction(instruction=[94, 94], checksum_byte=6)],
                               response_fields=[ByteField('application_mode')])

    @staticmethod
    def set_bootloader_safety_flag():
        """ Sets the bootloader's safety flag """
        return UCANCommandSpec(sid=SID.BOOTLOADER_COMMAND,
                               instruction=Instruction(instruction=[0, 125]),
                               identifier=AddressField('ucan_address', 3),
                               request_fields=[ByteField('safety_flag')],
                               response_instructions=[Instruction(instruction=[125, 125], checksum_byte=6)],
                               response_fields=[ByteField('safety_flag')])

    @staticmethod
    def get_mcu_id():
        """
        Gets the uCAN mcu ID
        Note: uCAN needs to be in bootloader
        """
        return UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                     pallet_type=PalletType.MCU_ID_REQUEST,
                                     response_fields=[StringField('mcu_id')])

    @staticmethod
    def get_bootloader_id():
        """
        Gets the uCAN bootloader ID
        Note: uCAN needs to be in bootloader
        """
        return UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                     pallet_type=PalletType.BOOTLOADER_ID_REQUEST,
                                     response_fields=[StringField('bootloader_id')])

    @staticmethod
    def write_flash(data_length):
        """
        Writes uCAN flash
        Note: uCAN needs to be in bootloader
        """
        return UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                     pallet_type=PalletType.FLASH_WRITE_REQUEST,
                                     request_fields=[Int32Field('start_address'), ByteArrayField('data', data_length)])

    @staticmethod
    def read_flash(data_length):
        """
        Reads uCAN flash
        Note: uCAN needs to be in bootloader
        """
        return UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                     pallet_type=PalletType.FLASH_READ_REQUEST,
                                     request_fields=[Int32Field('start_address'), ByteField('data_length')],
                                     response_fields=[ByteArrayField('data', data_length)])

    @staticmethod
    def erase_flash():
        """
        Erases uCAN flash
        Note: uCAN needs to be in bootloader
        """
        return UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                     pallet_type=PalletType.FLASH_ERASE_REQUEST)
