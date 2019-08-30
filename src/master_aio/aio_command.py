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
AIOCommandSpec defines payload handling; (de)serialization
"""
import logging
from serial_utils import printable
from master_aio.fields import PaddingField


LOGGER = logging.getLogger('openmotics')


class AIOCommandSpec(object):
    """
    Defines payload handling and de(serialization)
    """

    # TODO: Add validation callback which is - if not None - is called when the response payload is processed. Arguments are request and response, and it should return a bool indicating whether the validation passed or not.
    # TODO: Add some kind of byte bit field where that byte is represented as a dict or class where every bit can be named and get/set

    def __init__(self, instruction, request_fields=None, response_fields=None, response_instruction=None):
        """
        Create a APICommandSpec.

        :param instruction: name of the instruction as described in the AIO api.
        :type instruction: str
        :param request_fields: Fields in this request
        :type request_fields: list of master_aio.fields.Field
        :param response_fields: Fields in the response
        :type response_fields: list of master_aio.fields.Field
        :param response_instruction: name of the instruction of the answer in case it would be different from the response
        :type response_instruction: str
        """
        self.instruction = instruction
        self.request_fields = [] if request_fields is None else request_fields
        self.response_fields = [] if response_fields is None else response_fields
        self.response_instruction = response_instruction if response_instruction is not None else instruction

    def create_request_payload(self, fields):
        """
        Create the request payload for the AIO using this spec and the provided fields.

        :param fields: dictionary with values for the fields
        :type fields: dict
        :rtype: string
        """
        payload = ''
        for field in self.request_fields:
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
        payload_length = len(payload)
        result = {}
        for field in self.response_fields:
            field_length = field.length
            if callable(field_length):
                field_length = field_length(payload_length)
            if len(payload) < field_length:
                LOGGER.warning('Payload for instruction {0} did not contain all the expected data: {1}'.format(self.instruction, printable(payload)))
                break
            data = payload[:field_length]
            if not isinstance(field, PaddingField):
                result[field.name] = field.decode(data)
            payload = payload[field_length:]
        if payload != '':
            LOGGER.warning('Payload for instruction {0} could not be consumed completely: {1}'.format(self.instruction, printable(payload)))
        return result

