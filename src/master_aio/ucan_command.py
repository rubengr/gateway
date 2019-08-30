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
from serial_utils import printable
from master_aio.fields import PaddingField


LOGGER = logging.getLogger('openmotics')


class SID(object):
    NORMAL_COMMAND = 5
    BOOTLOADER_COMMAND = 1
    BOOTLOADER_PALLET = 0


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

    def fill_headers(self, identifier):
        self.headers = []
        self._response_instruction_by_hash = {}
        for instruction in self.response_instructions:
            hash_value = UCANCommandSpec.hash(instruction.instruction + self._identifier.encode_bytes(identifier))
            self.headers.append(hash_value)
            self._response_instruction_by_hash[hash_value] = instruction

    def create_request_payload(self, identifier, fields):
        """
        Create the request payload for the uCAN using this spec and the provided fields.

        :param identifier: The actual identifier
        :type identifier: str
        :param fields: dictionary with values for the fields
        :type fields: dict
        :rtype: list
        """
        payload = self.instruction.instruction + self._identifier.encode_bytes(identifier)
        for field in self._request_fields:
            payload += field.encode_bytes(fields.get(field.name))
        return payload

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
                LOGGER.warning('Payload did not contain all the expected data: {0}'.format(payload))
                return None
            response_instruction = self._response_instruction_by_hash[response_hash]
            payload_entry = payload[response_hash]
            crc = payload_entry[response_instruction.checksum_byte]
            expected_crc = UCANCommandSpec.calculate_crc(payload_entry[:response_instruction.checksum_byte])
            if crc != expected_crc:
                LOGGER.info('Unexpected CRC ({0} vs expected {1}): {2}'.format(crc, expected_crc, payload_entry))
            usefull_payload = payload_entry[self.header_length:response_instruction.checksum_byte]
            payload_data += usefull_payload

        result = {}
        payload_length = len(payload_data)
        for field in self._response_fields:
            field_length = field.length
            if callable(field_length):
                field_length = field_length(payload_length)
            if len(payload_data) < field_length:
                LOGGER.warning('Payload did not contain all the expected data: {0}'.format(payload_data))
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
