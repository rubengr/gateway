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


class UCANCommandSpec(object):
    """
    Defines payload handling and de(serialization)
    """

    def __init__(self, request_fields, identifier, response_set):
        """
        Create a UCANCommandSpec.

        :param request_fields: Fields in this request
        :type request_fields: list of master_aio.fields.Field
        :param identifier: The field to be used as extra identifier
        :type identifier: str
        :param response_set: Fields in the response
        """
        self.request_fields = request_fields
        self.identifier = identifier
        self.response_set = response_set
        self._identifier_field = [ft for ft in request_fields if ft.name == identifier][0]
        self.header_length = 2 + self._identifier_field.length
        self.headers = {}

    def fill_headers(self, fields):
        self.headers = {}
        for entry in self.response_set:
            hash_value = UCANCommandSpec.hash(entry[0] + self._identifier_field.encode_bytes(fields[self.identifier]))
            self.headers[hash_value] = entry[1]

    def create_request_payload(self, fields):
        """
        Create the request payload for the uCAN using this spec and the provided fields.

        :param fields: dictionary with values for the fields
        :type fields: dict
        :rtype: list
        """
        payload = []
        for field in self.request_fields:
            payload += field.encode_bytes(fields.get(field.name))
        return payload

    def consume_response_payload(self, payload):
        """
        Consumes the payload bytes

        :param payload Payload from the uCAN responses
        :type payload: dict
        :returns: Dictionary containing the parsed response
        :rtype: dict
        """

        result = {}
        for response_hash, fields in self.headers.iteritems():
            if response_hash not in payload:
                LOGGER.warning('Payload did not contain all the expected data: {0}'.format(payload))
                continue
            entry_payload = payload[response_hash]
            entry_payload_length = len(entry_payload)
            for field in fields:
                field_length = field.length
                if callable(field_length):
                    field_length = field_length(entry_payload_length)
                if len(entry_payload) < field_length:
                    LOGGER.warning('Payload did not contain all the expected data: {0}'.format(entry_payload))
                    break
                data = entry_payload[:field_length]
                if not isinstance(field, PaddingField):
                    result[field.name] = field.decode_bytes(data)
                entry_payload = entry_payload[field_length:]
        return result

    @staticmethod
    def hash(entries):
        times = 1
        result = 0
        for entry in entries:
            result += (entry * 256 * times)
            times += 1
        return result
