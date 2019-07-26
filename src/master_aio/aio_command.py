# Copyright (C) 2016 OpenMotics BVBA
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
AIOCommandSpec defines payload handling; (de)serialization
"""
import logging
from serial_utils import printable


LOGGER = logging.getLogger('openmotics')


class AIOCommandSpec(object):
    """
    Defines payload handling and de(serialization)
    """

    # TODO: Add validation callback which is - if not None - is called when the response payload is processed. Arguments are request and response, and it should return a bool indicating whether the validation passed or not.

    def __init__(self, instruction, request_fields, response_fields, response_instruction=None):
        """
        Create a APICommandSpec.

        :param instruction: name of the instruction as described in the AIO api.
        :type instruction: str
        :param request_fields: Fields in this request
        :type request_fields: list of master_aio.aio_command.Field
        :param response_fields: Fields in the response
        :type response_fields: list of master_aio.aio_command.Field
        :param response_instruction: name of the instruction of the answer in case it would be different from the response
        :type response_instruction: str
        """
        self.instruction = instruction
        self.request_fields = request_fields
        self.response_fields = response_fields
        self.response_instruction = response_instruction if response_instruction is not None else instruction

    def create_request_payload(self, fields=None):
        """
        Create the request payload for the AIO using this spec and the provided fields.

        :param fields: dictionary with values for the fields
        :type fields: dict
        :rtype: string
        """
        if fields is None:
            fields = dict()

        payload = ''
        for field in self.request_fields:
            payload += field.encode(fields.get(field.name))
        return payload

    def create_response_payload(self, fields):
        """
        Create a response payload from the AIO using this spec and the provided fields.
        * Only used for testing

        :param fields: dictionary with values for the fields
        :type fields: dict
        :rtype: string
        """
        payload = ''
        for field in self.response_fields:
            payload += field.encode(fields.get(field.name))
        return payload

    def consume_response_payload(self, payload):
        """
        Consumes the payload bytes

        :param payload Payload from the AIO response
        :type payload: str
        :returns: Dictionary containing the parsed response
        :rtype: dict
        """

        result = {}
        for field in self.response_fields:
            if len(payload) < field.length:
                LOGGER.warning('Payload for instruction {0} did not contain all the expected data: {1}'.format(self.instruction, printable(payload)))
                break
            data = payload[:field.length]
            result[field.name] = field.decode(data)
            payload = payload[field.length:]
        if payload != '':
            LOGGER.warning('Payload for instruction {0} could not be consumed completely: {1}'.format(self.instruction, printable(payload)))
        return result


class Field(object):
    """
    Field of an AIO command
    """

    def __init__(self, name, length):
        self.name = name
        self.length = length

    @staticmethod
    def byte(name):
        """ Create 1-byte field with a certain name.
        The byte type takes an int as input. """
        return ByteField(name)

    def encode(self, value):
        """
        Generate an encoded field.
        :param value: the value of the field.
        """
        raise NotImplementedError()

    def decode(self, data):
        """
        Decodes bytes (string)

        :param data: bytes to decode
        """
        raise NotImplementedError()


class ByteField(Field):
    def __init__(self, name):
        super(ByteField, self).__init__(name, 1)

    def encode(self, value):
        if not (0 <= value <= 255):
            raise ValueError('Value out of limits: 0 <= value <= 255')
        return str(chr(value))

    def decode(self, data):
        return ord(data)


class WordField(Field):
    def __init__(self, name):
        super(WordField, self).__init__(name, 2)

    def encode(self, value):
        if not (0 <= value <= 65535):
            raise ValueError('Value out of limits: 0 <= value <= 65535')
        return str(chr(value / 256)) + str(chr(value % 256))

    def decode(self, data):
        return ord(data[0]) * 256 + ord(data[1])


class ByteArrayField(Field):
    def __init__(self, name, length):
        super(ByteArrayField, self).__init__(name, length)

    def encode(self, value):
        if len(value) != self.length:
            raise ValueError('Value should be an array of {0} items with 0 <= item <= 255'.format(self.length))
        data = ''
        for item in value:
            if not (0 <= item <= 255):
                raise ValueError('One of the items in value is out of limits: 0 <= item <= 255')
            data += str(chr(value))
        return data

    def decode(self, data):
        result = []
        for item in data:
            result.append(ord(item))
        return result
