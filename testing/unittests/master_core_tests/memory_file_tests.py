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
Tests for the memory_file module
"""

import unittest
import xmlrunner
import logging
from mock import Mock
from master_core.memory_file import MemoryTypes, MemoryFile
from master_core.memory_types import MemoryAddress


class MemoryFileTest(unittest.TestCase):
    """ Tests for MemoryFile """

    @classmethod
    def setUpClass(cls):
        logger = logging.getLogger('openmotics')
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

    def test_data_consistency(self):
        memory = {}

        def _do_command(api, payload):
            if api.instruction == 'MR':
                page = payload['page']
                start = payload['start']
                length = payload['length']
                return {'data': memory.get(page, [255] * 256)[start:start + length]}
            if api.instruction == 'MW':
                page = payload['page']
                start = payload['start']
                page_data = memory.setdefault(page, [255] * 256)
                for index, data_byte in enumerate(payload['data']):
                    page_data[start + index] = data_byte

        master_communicator = Mock()
        master_communicator.do_command = _do_command

        memory_file = MemoryFile(MemoryTypes.EEPROM, master_communicator)

        memory[5] = [255] * 256
        memory[5][10] = 1
        memory[5][11] = 2
        memory[5][12] = 3
        address = MemoryAddress(memory_type=MemoryTypes.EEPROM, page=5, offset=10, length=3)

        data = memory_file.read([address])[address]
        self.assertEqual([1, 2, 3], data)
        memory_file.write({address: [6, 7, 8]})
        self.assertEqual([6, 7, 8], memory[5][10:13])


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
