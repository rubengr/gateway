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
Module to work update an uCAN
"""

import logging
import os
import struct
from intelhex import IntelHex
from master_aio.ucan_api import UCANAPI
from master_aio.ucan_command import UCANPalletCommandSpec
from master_aio.fields import Int32Field

LOGGER = logging.getLogger('openmotics')


class UCANUpdater(object):
    """
    This is a class holding tools to execute uCAN updates
    """

    ADDRESS_START = 0x4
    ADDRESS_END = 0xCFFC  # Not including the end address. Technically the 4-byte CRC starts at this address.

    # There's a buffer of 8 segments on the uCAN. This means 7 data segments with a 1-byte header, so 49 bytes.
    # In this data stream is also the address (4 bytes) and the CRC (4 bytes) leaving 41 usefull bytes.
    MAX_FLASH_BYTES = 41

    @staticmethod
    def update(cc_address, ucan_address, ucan_communicator, hex_filename):
        """
        Flashes the content from an Intel HEX file to the specified uCAN
        :param cc_address: CC address
        :param ucan_address: uCAN address
        :param ucan_communicator: uCAN commnicator
        :type ucan_communicator: master_aio.ucan_communicator.UCANCommunicator
        :param hex_filename: The filename of the hex file to flash
        """

        # TODO: Check version and skip update if the version is already active

        LOGGER.info('Updating uCAN {0} at CC {1}'.format(ucan_address, cc_address))

        if not os.path.exists(hex_filename):
            raise RuntimeError('The given path does not point to an existing file')
        intel_hex = IntelHex(hex_filename)
        LOGGER.info('Flashing contents of {0}'.format(os.path.basename(hex_filename)))

        in_bootloader = ucan_communicator.is_ucan_in_bootloader(cc_address, ucan_address)
        if in_bootloader:
            LOGGER.info('Bootloader active')
        else:
            LOGGER.info('Bootloader not active, switching to bootloader')
            # TODO: Set bootloader timeout to large value
            # TODO: Switch to bootloader
            in_bootloader = ucan_communicator.is_ucan_in_bootloader(cc_address, ucan_address)
            if not in_bootloader:
                raise RuntimeError('Could not enter bootloader for uCAN {0} at CC {1}'.format(ucan_address, cc_address))

        LOGGER.info('Start flashing...')
        address_blocks = range(UCANUpdater.ADDRESS_START, UCANUpdater.ADDRESS_END, UCANUpdater.MAX_FLASH_BYTES)
        total_amount = float(len(address_blocks))
        crc = 0
        total_payload = []
        logged_percentage = -1
        for index, start_address in enumerate(address_blocks):
            end_address = min(UCANUpdater.ADDRESS_END, start_address + UCANUpdater.MAX_FLASH_BYTES)

            payload = []
            for i in xrange(start_address, end_address):
                payload.append(intel_hex[i])

            crc = UCANPalletCommandSpec.calculate_crc(payload, crc)
            if start_address == address_blocks[-1]:
                payload += Int32Field.encode_bytes(crc)

            little_start_address = struct.unpack('<I', struct.pack('>I', start_address))[0]  # TODO: Handle endianness in API definition using Field endianness
            ucan_communicator.do_command(cc_address, UCANAPI.write_flash(len(payload)), ucan_address, {'start_address': little_start_address,
                                                                                                       'data': payload})
            total_payload += payload

            percentage = int(index / total_amount * 100)
            if percentage > logged_percentage:
                LOGGER.info('* {0}%'.format(percentage))
                logged_percentage = percentage

        LOGGER.info('Flashing complete.')
        crc = UCANPalletCommandSpec.calculate_crc(total_payload)
        if crc != 0:
            message = 'Unexpected error in CRC calculation ({0})'.format(crc)
            LOGGER.info(message)
            raise RuntimeError(message)
        LOGGER.info('Flashing successful')

        # TODO: Reduce bootloader timeout
        # TODO: Switch to application
