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
Tests for the fields module
"""

import unittest
import xmlrunner
import logging
from mock import Mock
from master_core.fields import *


class APIFieldsTest(unittest.TestCase):
    """ Tests for fields """

    @classmethod
    def setUpClass(cls):
        logger = logging.getLogger('openmotics')
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

    def test_byte_field(self):
        self._test_field(ByteField('x'), [[-1, ValueError],
                                          [0, [0]],
                                          [5, [5]],
                                          [254, [254]],
                                          [255, [255]],
                                          [256, ValueError]])

    def test_char_field(self):
        self._test_field(CharField('x'), [[-1, ValueError],
                                          ['\x00', [0]],
                                          ['A', [65]],
                                          ['\xFF', [255]],
                                          ['\x00\x00', ValueError]])

    def test_temperature_field(self):
        self._test_field(TemperatureField('x'), [[-32.5, ValueError],
                                                 [-32, [0]],
                                                 [0, [64]],
                                                 [0.1, [64], 0],
                                                 [0.5, [65]],
                                                 [95, [254]],
                                                 [95.5, ValueError],
                                                 [None, [255]]])

    def test_humidity_field(self):
        self._test_field(HumidityField('x'), [[-1, ValueError],
                                              [0, [0]],
                                              [0.1, [0], 0],
                                              [0.5, [1]],
                                              [100, [200]],
                                              [101, ValueError],
                                              [None, [255]]])

    def test_word_field(self):
        self._test_field(WordField('x'), [[-1, ValueError],
                                          [0, [0, 0]],
                                          [255, [0, 255]],
                                          [256, [1, 0]],
                                          [65535, [255, 255]],
                                          [65536, ValueError]])

    def test_uint32_field(self):
        self._test_field(UInt32Field('x'), [[-1, ValueError],
                                            [0, [0, 0, 0, 0]],
                                            [256, [0, 0, 1, 0]],
                                            [4294967295, [255, 255, 255, 255]],
                                            [4294967296, ValueError]])

    def test_bytearray_field(self):
        self._test_field(ByteArrayField('x', 3), [[[-1, 0, 0], ValueError],
                                                  [[0, 0, 0], [0, 0, 0]],
                                                  [[255, 255, 1], [255, 255, 1]],
                                                  [[255, 255, 256], ValueError],
                                                  [[0, 0], ValueError]])

    def test_temperaturearray_field(self):
        self._test_field(TemperatureArrayField('x', 3), [[[-32.5, 0, 0], ValueError],
                                                         [[0, 0, 0.5], [64, 64, 65]],
                                                         [[95, None, 1], [254, 255, 66]],
                                                         [[0, 0], ValueError]])

    def test_humidityarray_field(self):
        self._test_field(HumidityArrayField('x', 3), [[[-1, 0, 0], ValueError],
                                                      [[0, 0, 0.5], [0, 0, 1]],
                                                      [[99, None, 1], [198, 255, 2]],
                                                      [[0, 0], ValueError]])

    def test_wordarray_field(self):
        self._test_field(WordArrayField('x', 3), [[[-1, 0, 0], ValueError],
                                                  [[0, 0, 256], [0, 0, 0, 0, 1, 0]],
                                                  [[65536, 0, 0], ValueError],
                                                  [[0, 0], ValueError]])

    def test_address_field(self):
        self._test_field(AddressField('x'), [['-1.0.0.0', ValueError],
                                             ['0.0.0.0', [0, 0, 0, 0], '000.000.000.000'],
                                             ['0.05.255.50', [0, 5, 255, 50], '000.005.255.050'],
                                             ['0.256.0.0', ValueError, '000.256.000.000'],
                                             ['0.0.0', ValueError],
                                             ['0,0,0,0', ValueError],
                                             ['0.0', ValueError],
                                             ['foobar', ValueError]])
        self._test_field(AddressField('x', 2), [['-1.0', ValueError],
                                                ['0.0', [0, 0, ], '000.000'],
                                                ['255.50', [255, 50], '255.050'],
                                                ['0.256', ValueError, '000.256'],
                                                ['0', ValueError],
                                                ['0,0', ValueError],
                                                ['foobar', ValueError]])

    def test_string_field(self):
        self._test_field(StringField('x'), [['abc', [97, 98, 99, 0]],
                                            ['', [0]],
                                            ['abc\x00d', [97, 98, 99, 0, 100, 0]]])

    def test_padding_field(self):
        field = PaddingField(3)
        self.assertEqual([0, 0, 0], field.encode_bytes(0))
        self.assertEqual([0, 0, 0], field.encode_bytes(5))
        self.assertEqual('...', field.decode_bytes([0]))
        self.assertEqual('...', field.decode_bytes([0, 0, 0]))
        self.assertEqual('...', field.decode_bytes([0, 0, 0, 0, 0]))

    def test_literalbytes_field(self):
        field = LiteralBytesField(0)
        with self.assertRaises(ValueError):
            field.encode_bytes(255)
        self.assertEqual([0], field.encode_bytes(None))
        field = LiteralBytesField(256)
        with self.assertRaises(ValueError):
            field.encode_bytes(None)
        field = LiteralBytesField(10, 10)
        self.assertEqual([10, 10], field.encode_bytes(None))
        with self.assertRaises(ValueError):
            field.decode_bytes([0])
        with self.assertRaises(ValueError):
            field.decode_bytes(None)

    def _test_field(self, field, scenario):
        for item in scenario:
            if len(item) == 2:
                value, expected_bytes = item
                expected_value = value
            else:
                value, expected_bytes, expected_value = item
            if expected_bytes == ValueError:
                with self.assertRaises(expected_bytes):
                    field.encode_bytes(value)
                continue
            result_bytes = field.encode_bytes(value)
            self.assertEqual(expected_bytes, result_bytes)
            result_value = field.decode_bytes(result_bytes)
            self.assertEqual(expected_value, result_value)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
