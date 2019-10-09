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
    ADDRESS_END = 0xCFFB  # The 4-byte CRC is appended after this address

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

        if not os.path.exists(hex_filename):
            raise RuntimeError('The given path does not point to an existing file')
        intel_hex = IntelHex(hex_filename)

        address_blocks = range(UCANUpdater.ADDRESS_START, UCANUpdater.ADDRESS_END, UCANUpdater.MAX_FLASH_BYTES)
        crc = 0
        for start_address in address_blocks:
            end_address = min(UCANUpdater.ADDRESS_END, start_address + UCANUpdater.MAX_FLASH_BYTES)
            payload = []
            for i in xrange(start_address, end_address):
                payload.append(intel_hex[i])
            if start_address == address_blocks[-1]:
                payload += Int32Field.encode_bytes(crc)
            else:
                crc = UCANPalletCommandSpec.calculate_crc(payload, crc)

            little_start_address = struct.unpack('<I', struct.pack('>I', start_address))[0]  # TODO: Handle endianness in API definition using Field endianness
            ucan_communicator.do_command(cc_address, UCANAPI.write_flash(len(payload)), ucan_address, {'start_address': little_start_address,
                                                                                                       'data': payload})
