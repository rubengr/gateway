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
Contains a memory representation
"""
import logging
from wiring import provides, inject, SingletonScope, scope
from master_aio.aio_api import AIOAPI

LOGGER = logging.getLogger("openmotics")


class MemoryTypes(object):
    FRAM = 'F'
    EEPROM = 'E'


class MemoryFile(object):

    @provides('memory_file')
    @scope(SingletonScope)
    @inject(aio_communicator='master_communicator')
    def __init__(self, memory_type, aio_communicator):
        """
        Initializes the MemoryFile instance, reprensenting one of the supported memory types

        :type aio_communicator: master_aio.aio_communicator.AIOCommunicator
        """

        self._aio_communicator = aio_communicator
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
        :type addresses: list of master_aio.memory_types.MemoryAddress
        """
        data = {}
        for address in addresses:
            page_data = self.read_page(address.page)
            data[address] = page_data[address.offset:address.offset + address.length]
        return data

    def read_page(self, page):
        if page not in self._cache:
            page_data = []
            for i in xrange(self._page_length / 32):
                page_data += self._aio_communicator.do_command(
                    AIOAPI.memory_read(),
                    {'type': self.type, 'page': page, 'start': i * 32, 'length': 32}
                )['data']
            self._cache[page] = page_data
        return self._cache[page]

    def write_page(self, page, data):
        self._cache[page] = data
        for i in xrange(self._page_length / 32):
            self._aio_communicator.do_command(
                AIOAPI.memory_write(32),
                {'type': self.type, 'page': page, 'start': i * 32, 'data': data}
            )

    def invalidate_cache(self, page=None):
        pages = [page]
        if page is None:
            pages = range(self._pages)
        for page in pages:
            self._cache.pop(page, None)
