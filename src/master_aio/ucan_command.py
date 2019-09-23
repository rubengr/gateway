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
UCANCommandSpec defines payload handling; (de)serialization
"""
import logging
import math
from master_aio.fields import PaddingField, Int32Field, StringField
from serial_utils import printable


LOGGER = logging.getLogger('openmotics')


class SID(object):
    NORMAL_COMMAND = 5
    BOOTLOADER_COMMAND = 1
    BOOTLOADER_PALLET = 0


class PalletType(object):
    MCU_ID_REQUEST = 0x00
    MCU_ID_REPLY = 0x01
    BOOTLOADER_ID_REQUEST = 0x02
    BOOTLOADER_ID_REPLY = 0x03
    FLASH_WRITE_REQUEST = 0x04
    FLASH_WRITE_REPLY = 0x05
    FLASH_READ_REQUEST = 0x06
    FLASH_READ_REPLY = 0x07
    EEPROM_WRITE_REQUEST = 0x08
    EEPROM_WRITE_REPLY = 0x09
    EEPROM_READ_REQUEST = 0x0A
    EEPROM_READ_REPLY = 0x0B
    RESET_REQUEST = 0x0C
    RESET_REPLY = 0x0D


class Instruction(object):
    def __init__(self, instruction, checksum_byte=None):
        self.instruction = instruction
        self.checksum_byte = checksum_byte


class UCANCommandSpec(object):
    """
    Defines payload handling and de(serialization)
    """

    def __init__(self, sid, instruction, identifier, request_fields=None, response_instructions=None, response_fields=None):
        """
        Create a UCANCommandSpec.

        :param sid: SID
        :type sid: master_aio.ucan_command.UCANCommandSpec.SID
        :param instruction: Instruction object for this command
        :type instruction: master_aio.ucan_command.Instruction
        :param identifier: The field to be used as extra identifier
        :type identifier: master_aio.fields.Field
        :param request_fields: Fields in this request
        :type request_fields: list of master_aio.fields.Field
        :param response_instructions: List of all the response instruction bytes
        :type response_instructions: list of master_aio.ucan_command.Instruction
        :param response_fields: Fields in the response
        :type response_fields: list of master_aio.fields.Field
        """
        self.sid = sid
        self.instruction = instruction
        self._identifier = identifier

        self._request_fields = [] if request_fields is None else request_fields
        self._response_fields = [] if response_fields is None else response_fields
        self.response_instructions = [] if response_instructions is None else response_instructions

        self.header_length = 2 + self._identifier.length
        self.headers = []
        self._response_instruction_by_hash = {}

    def set_identity(self, identity):
        self.headers = []
        self._response_instruction_by_hash = {}
        for instruction in self.response_instructions:
            hash_value = UCANCommandSpec.hash(instruction.instruction + self._identifier.encode_bytes(identity))
            self.headers.append(hash_value)
            self._response_instruction_by_hash[hash_value] = instruction

    def create_request_payloads(self, identity, fields):
        """
        Create the request payloads for the uCAN using this spec and the provided fields.

        :param identity: The actual identity
        :type identity: str
        :param fields: dictionary with values for the fields
        :type fields: dict
        :rtype: generator of tuple(int, list)
        """
        destination_address = self._identifier.encode_bytes(identity)
        if self.sid == SID.BOOTLOADER_COMMAND:
            destination_address = list(reversed(destination_address))  # Little endian
        payload = self.instruction.instruction + destination_address
        for field in self._request_fields:
            payload += field.encode_bytes(fields.get(field.name))
        payload.append(UCANCommandSpec.calculate_crc(payload))
        yield payload

    def consume_response_payload(self, payload):
        """
        Consumes the payload bytes

        :param payload Payload from the uCAN responses
        :type payload: list of int
        :returns: Dictionary containing the parsed response
        :rtype: dict
        """
        payload_data = []
        for response_hash in self.headers:
            # Headers are ordered
            if response_hash not in payload:
                LOGGER.warning('Payload did not contain all the expected data: {0}'.format(printable(payload)))
                return None
            response_instruction = self._response_instruction_by_hash[response_hash]
            payload_entry = payload[response_hash]
            crc = payload_entry[response_instruction.checksum_byte]
            expected_crc = UCANCommandSpec.calculate_crc(payload_entry[:response_instruction.checksum_byte])
            if crc != expected_crc:
                LOGGER.info('Unexpected CRC ({0} vs expected {1}): {2}'.format(crc, expected_crc, printable(payload_entry)))
                return None
            usefull_payload = payload_entry[self.header_length:response_instruction.checksum_byte]
            payload_data += usefull_payload
        return self._parse_payload(payload_data)

    def _parse_payload(self, payload_data):
        result = {}
        payload_length = len(payload_data)
        for field in self._response_fields:
            if isinstance(field, StringField):
                field_length = payload_data.index(0) + 1
            else:
                field_length = field.length
            if callable(field_length):
                field_length = field_length(payload_length)
            if len(payload_data) < field_length:
                LOGGER.warning('Payload did not contain all the expected data: {0}'.format(printable(payload_data)))
                break
            data = payload_data[:field_length]
            if not isinstance(field, PaddingField):
                result[field.name] = field.decode_bytes(data)
            payload_data = payload_data[field_length:]
        return result

    @staticmethod
    def calculate_crc(data):
        """
        Calculate the CRC of the data.

        :param data: Data for which to calculate the CRC
        :returns: CRC
        """
        crc = 0
        for data_byte in data:
            crc += data_byte
        return crc % 256

    def extract_hash(self, payload):
        return UCANCommandSpec.hash(payload[0:self.header_length])

    @staticmethod
    def hash(entries):
        times = 1
        result = 0
        for entry in entries:
            result += (entry * 256 * times)
            times += 1
        return result


class UCANPalletCommandSpec(UCANCommandSpec):
    """
    Defines payload handling and de(serialization)
    """

    def __init__(self, identifier, pallet_type, request_fields=None, response_fields=None):
        """
        Create a UCANCommandSpec.

        :param identifier: The field to be used as extra identifier
        :type identifier: master_aio.fields.Field
        :param pallet_type: The type of the pallet
        :type pallet_type: int
        :param request_fields: Fields in this request
        :type request_fields: list of master_aio.fields.Field
        :param response_fields: Fields in the response
        :type response_fields: list of master_aio.fields.Field
        """
        super(UCANPalletCommandSpec, self).__init__(sid=SID.BOOTLOADER_PALLET,
                                                    instruction=None,
                                                    identifier=identifier,
                                                    request_fields=request_fields,
                                                    response_instructions=[],
                                                    response_fields=response_fields)
        self._pallet_type = pallet_type

    def set_identity(self, identity):
        _ = identity  # Not used for pallet communications
        pass

    def create_request_payloads(self, identity, fields):
        """
        Create the request payloads for the uCAN using this spec and the provided fields.

        :param identity: The actual identity
        :type identity: str
        :param fields: dictionary with values for the fields
        :type fields: dict
        :rtype: generator of tuple(int, list)
        """
        destination_address = list(reversed(self._identifier.encode_bytes(identity)))  # Little endian
        source_address = self._identifier.encode_bytes('000.000.000')  # Little endian, but doesn't matter here
        payload = source_address  + destination_address + [self._pallet_type]
        for field in self._request_fields:
            payload += field.encode_bytes(fields.get(field.name))
        payload += Int32Field.encode_bytes(UCANPalletCommandSpec.calculate_crc(payload))
        segments = int(math.ceil(len(payload) / 7.0))
        first = True
        while len(payload) > 0:
            header = ((1 if first else 0) << 7) + (segments - 1)
            sub_payload = [header] + payload[:7]
            payload = payload[7:]
            yield sub_payload
            first = False
            segments -= 1

    def consume_response_payload(self, payload):
        """
        Consumes the payload bytes

        :param payload Payload from the uCAN responses
        :type payload: list of int
        :returns: Dictionary containing the parsed response
        :rtype: dict
        """
        crc = UCANPalletCommandSpec.calculate_crc(payload)
        if crc != 0:
            LOGGER.info('Unexpected pallet CRC ({0} != 0): {1}'.format(crc, printable(payload)))
            return None
        return self._parse_payload(payload[7:-4])

    @staticmethod
    def calculate_crc(data):
        """
        Calculates the CRC of data. The algorithm is designed to make sure flowing statement is True:
        > crc(data + crc(data)) == 0

        :param data: Data for which to calculate the CRC
        :returns: CRC
        """
        width = 32
        topbit = 1 << (width - 1)
        polynomial = 0x04C11DB7
        remainder = 0
        for i in xrange(len(data)):
            remainder ^= data[i] << (width - 8)
            remainder &= 0xFFFFFFFF
            for _ in xrange(7, -1, -1):
                if remainder & topbit:
                    remainder = (remainder << 1) ^ polynomial
                    remainder &= 0xFFFFFFFF
                else:
                    remainder = (remainder << 1)
                    remainder &= 0xFFFFFFFF
        return remainder
