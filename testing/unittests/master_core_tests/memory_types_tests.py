# Copyright (C) 2020 OpenMotics BV
#
# This program is free software, you can redistribute it and/or modify
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
Tests for the types module
"""

import unittest
import xmlrunner
import logging
from mock import Mock
from ioc import SetTestMode, SetUpTestInjections
from master_core.basic_action import BasicAction
from master_core.memory_file import MemoryTypes, MemoryFile
from master_core.memory_types import *

logger = logging.getLogger('openmotics')


class MemoryTypesTest(unittest.TestCase):
    """ Tests for types """

    @classmethod
    def setUpClass(cls):
        SetTestMode()
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

    def test_memory_field_addressing(self):
        for item in [[(0, 0), 0, TypeError],
                     [(0, 1), None, (0, 1)],
                     [lambda id: (id, 0), 1, (1, 0)],
                     [lambda id: (id, 0), None, TypeError],
                     [lambda id: (id, id), 2, (2, 2)]]:
            spec, object_id, expected_address = item
            field = MemoryField(MemoryTypes.EEPROM, address_spec=spec, length=1)
            if expected_address == TypeError:
                with self.assertRaises(expected_address):
                    field.get_address(object_id)
                continue
            self.assertEqual(MemoryAddress(MemoryTypes.EEPROM, expected_address[0], expected_address[1], 1), field.get_address(object_id))

    def test_string_field(self):
        self._test_field(MemoryStringField, [[[1], 'a', [97]],
                                             [[1], 'ab', ValueError],
                                             [[3], 'abc', [97, 98, 99]]])

    def test_byte_field(self):
        self._test_field(MemoryByteField, [[[], -1, ValueError],
                                           [[], 0, [0]],
                                           [[], 20, [20]],
                                           [[], 2 ** 8 - 1, [255]],
                                           [[], 2 ** 8, ValueError]])

    def test_word_field(self):
        self._test_field(MemoryWordField, [[[], -1, ValueError],
                                           [[], 0, [0, 0]],
                                           [[], 2 ** 8, [1, 0]],
                                           [[], 2 ** 16 - 1, [255, 255]],
                                           [[], 2 ** 16, ValueError]])

    def test_3bytes_field(self):
        self._test_field(Memory3BytesField, [[[], -1, ValueError],
                                             [[], 0, [0, 0, 0]],
                                             [[], 2 ** 8, [0, 1, 0]],
                                             [[], 2 ** 16 - 1, [0, 255, 255]],
                                             [[], 2 ** 16, [1, 0, 0]],
                                             [[], 2 ** 24 - 1, [255, 255, 255]],
                                             [[], 2 ** 24, ValueError]])

    def test_bytearray_field(self):
        self._test_field(MemoryByteArrayField, [[[1], [-1], ValueError],
                                                [[1], [0], [0]],
                                                [[2], [0], ValueError],
                                                [[2], [0, 0, 0], ValueError],
                                                [[2], [10, 0], [10, 0]],
                                                [[2], [10, 265], ValueError]])

    def test_basicaction_field(self):
        self._test_field(MemoryBasicActionField, [[[], BasicAction(10, 10, 0, 0), [10, 10, 0, 0, 0, 0]],
                                                  [[], BasicAction(10, 20, 256, 256), [10, 20, 1, 0, 1, 0]]])

    def test_address_field(self):
        self._test_field(MemoryAddressField, [[[], '0', ValueError],
                                              [[], '0.0.0.0', [0, 0, 0, 0], '000.000.000.000'],
                                              [[], '1.2.3.4', [1, 2, 3, 4], '001.002.003.004']])

    def test_version_field(self):
        self._test_field(MemoryVersionField, [[[], '0', ValueError],
                                              [[], '0.0.0', [0, 0, 0]],
                                              [[], '1.2.3', [1, 2, 3]]])

    def _test_field(self, field_type, scenario):
        for item in scenario:
            if len(item) == 3:
                args, value, expected_bytes = item
                expected_value = value
            else:
                args, value, expected_bytes, expected_value = item
            field = field_type(MemoryTypes.EEPROM, (None, None), *args)
            if expected_bytes == ValueError:
                with self.assertRaises(expected_bytes):
                    field.encode(value)
                continue
            result_bytes = field.encode(value)
            self.assertEqual(expected_bytes, result_bytes)
            result_value = field.decode(result_bytes)
            self.assertEqual(expected_value, result_value)

    def test_memory_field_container(self):
        address = MemoryAddress(MemoryTypes.EEPROM, 0, 1, 1)
        memory_file_mock = Mock(MemoryFile)
        memory_file_mock.read.return_value = {address: [1]}
        container = MemoryFieldContainer(memory_field=MemoryByteField(MemoryTypes.EEPROM, address_spec=(0, 1)),
                                         memory_address=address,
                                         memory_files={MemoryTypes.EEPROM: memory_file_mock})
        data = container.decode()
        self.assertEqual(1, data)
        memory_file_mock.read.assert_called_with([address])
        container.encode(2)
        data = container.decode()
        self.assertEqual(2, data)
        container.save()
        memory_file_mock.write.assert_called_with({address: [2]})

    def test_model_definition(self):
        memory_map = {0: [30, 31, 32],
                      1: [40, 0b0101],
                      2: [41, 0b1011],
                      3: [42, 0b1000],
                      4: [43, 0b0000]}

        def _read(addresses):
            data_ = {}
            for address in addresses:
                data_[address] = memory_map[address.page][address.offset:address.offset + address.length]
            return data_

        def _write(data_map):
            for address, data_ in data_map.iteritems():
                for index, data_byte in enumerate(data_):
                    memory_map[address.page][address.offset + index] = data_byte

        memory_file_mock = Mock(MemoryFile)
        memory_file_mock.read = _read
        memory_file_mock.write = _write

        SetUpTestInjections(memory_files={MemoryTypes.EEPROM: memory_file_mock})

        class Parent(MemoryModelDefinition):
            info = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (0, id))

        class Child(MemoryModelDefinition):
            class _Composed(CompositeMemoryModelDefinition):
                info = CompositeNumberField(start_bit=0, width=3, value_offset=2)
                bit = CompositeBitField(bit=3)

            parent = MemoryRelation(Parent, id_spec=lambda id: id / 2)
            info = MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (id, 0))
            composed = _Composed(field=MemoryByteField(MemoryTypes.EEPROM, address_spec=lambda id: (id, 1)))

        parent_0 = {'id': 0, 'info': 30}
        parent_1 = {'id': 1, 'info': 31}
        parent_2 = {'id': 2, 'info': 32}
        for entry in [[1, {'id': 1, 'info': 40, 'composed': {'bit': False, 'info': 3}}, parent_0],
                      [2, {'id': 2, 'info': 41, 'composed': {'bit': True, 'info': 1}}, parent_1],
                      [3, {'id': 3, 'info': 42, 'composed': {'bit': True, 'info': None}}, parent_1],
                      [4, {'id': 4, 'info': 43, 'composed': {'bit': False, 'info': None}}, parent_2]]:
            child_id, child_data, parent_data = entry
            child = Child(child_id)
            self.assertEqual(child_data, child.serialize())
            self.assertEqual(parent_data, child.parent.serialize())
            self.assertEqual(child_data['info'], child.info)
            self.assertEqual(child_data['composed']['bit'], child.composed.bit)
            self.assertEqual(child_data['composed']['info'], child.composed.info)

        parent = Parent(0)
        with self.assertRaises(ValueError):
            child.deserialize({'id': 1,
                               'foo': 2})
        child = Child.deserialize({'id': 4,
                                   'info': 10,
                                   'composed': {'bit': True},
                                   'parent': {'id': 0,
                                              'info': 5}})
        self.assertEqual({'id': 4,
                          'info': 10,
                          'composed': {'bit': True,
                                       'info': None}}, child.serialize())
        self.assertEqual({'id': 0,
                          'info': 5}, child.parent.serialize())
        with self.assertRaises(ValueError):
            child.info = 256
        child.info = 20
        with self.assertRaises(AttributeError):
            child.parent = parent
        child.save()
        self.assertEqual([20, 0b1000], memory_map[4])
        child.composed.bit = False
        child.composed.info = 4
        self.assertEqual({'id': 4,
                          'info': 20,
                          'composed': {'bit': False,
                                       'info': 4}}, child.serialize())
        child.save()
        self.assertEqual([20, 0b0110], memory_map[4])


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
