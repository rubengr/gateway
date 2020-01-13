# Copyright (C) 2019 OpenMotics BV
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
Contains a memory representation
"""
import logging
from wiring import provides, inject, SingletonScope, scope
from master_core.core_api import CoreAPI

logger = logging.getLogger("openmotics")


class MemoryTypes(object):
    FRAM = 'F'
    EEPROM = 'E'


class MemoryFile(object):

    @provides('memory_file')
    @scope(SingletonScope)
    @inject(core_communicator='master_core_communicator')
    def __init__(self, memory_type, core_communicator):
        """
        Initializes the MemoryFile instance, reprensenting one of the supported memory types

        :type core_communicator: master_core.core_communicator.CoreCommunicator
        """

        self._core_communicator = core_communicator
        self.type = memory_type
        if memory_type == MemoryTypes.EEPROM:
            self._pages = 512
            self._page_length = 256
        elif memory_type == MemoryTypes.FRAM:
            self._pages = 128
            self._page_length = 256
        self._cache = {}

    def read(self, addresses):
        """
        :type addresses: list[master_core.memory_types.MemoryAddress]
        """
        data = {}
        for address in addresses:
            page_data = self.read_page(address.page)
            data[address] = page_data[address.offset:address.offset + address.length]
        return data

    def write(self, data_map):
        """
        :type data_map: dict[master_core.memory_types.MemoryAddress, list[int]]
        """
        for address, data in data_map.iteritems():
            page_data = self.read_page(address.page)
            for index, data_byte in enumerate(data):
                page_data[address.offset + index] = data_byte
            self.write_page(address.page, page_data)

    def read_page(self, page):
        if page not in self._cache:
            page_data = []
            for i in xrange(self._page_length / 32):
                page_data += self._core_communicator.do_command(
                    CoreAPI.memory_read(),
                    {'type': self.type, 'page': page, 'start': i * 32, 'length': 32}
                )['data']
            self._cache[page] = page_data
        return self._cache[page]

    def write_page(self, page, data):
        self._cache[page] = data
        length = 32
        for i in xrange(self._page_length / length):
            start = i * length
            self._core_communicator.do_command(
                CoreAPI.memory_write(length),
                {'type': self.type, 'page': page, 'start': start, 'data': data[start:start + length]}
            )

    def invalidate_cache(self, page=None):
        pages = [page]
        if page is None:
            pages = range(self._pages)
        for page in pages:
            self._cache.pop(page, None)
