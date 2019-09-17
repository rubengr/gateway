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
Tests for uCAN communicator module.
"""

import unittest
import xmlrunner
import logging
from mock import Mock
from master_aio.exceptions import BootloadingException
from master_aio.ucan_communicator import UCANCommunicator, SID
from master_aio.ucan_command import UCANCommandSpec, UCANPalletCommandSpec, PalletType, Instruction
from master_aio.fields import AddressField, ByteArrayField, ByteField, Int32Field, StringField


class UCANCommunicatorTest(unittest.TestCase):
    """ Tests for UCANCommunicator """

    @classmethod
    def setUpClass(cls):
        logger = logging.getLogger('openmotics')
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(handler)

    def test_pallet_reconstructing(self):
        received_commands = []

        def send_command(_cid, _command, _fields):
            received_commands.append(_fields)

        aio_communicator = Mock()
        aio_communicator.send_command = send_command
        ucan_communicator = UCANCommunicator(aio_communicator=aio_communicator, verbose=True)
        cc_address = '000.000.000.000'
        ucan_address = '000.000.000'
        pallet_type = PalletType.MCU_ID_REQUEST  # Not important for this test

        for length in [1, 3]:
            # Build command
            command = UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                            pallet_type=pallet_type,
                                            request_fields=[ByteField('foo'), ByteField('bar')],
                                            response_fields=[ByteArrayField('other', length)])

            # Send command to mocked AIO communicator
            received_commands = []
            ucan_communicator.do_command(cc_address, command, ucan_address, {'foo': 1, 'bar': 2}, timeout=None)

            # Validate whether the correct data was send to the AIO
            self.assertEqual(len(received_commands), 2)
            self.assertDictEqual(received_commands[0], {'cc_address': cc_address,
                                                        'nr_can_bytes': 8,
                                                        'payload': [129, 0, 0, 0, 0, 0, 0, pallet_type],
                                                        #                +--------------+ = source and destination uCAN address
                                                        'sid': SID.BOOTLOADER_PALLET})
            self.assertDictEqual(received_commands[1], {'cc_address': cc_address,
                                                        'nr_can_bytes': 7,
                                                        'payload': [0, 1, 2, 219, 155, 250, 178, 0],
                                                        #              |  |  +----------------+ = checksum
                                                        #              |  + = bar
                                                        #              + = foo
                                                        'sid': SID.BOOTLOADER_PALLET})

            # Build fake reply from AIO
            consumer = ucan_communicator._consumers[cc_address][0]
            fixed_payload = [0, 0, 0, 0, 0, 0, pallet_type]
            variable_payload = range(7, 7 + length)  # [7] or [7, 8, 9]
            crc_payload = Int32Field.encode_bytes(UCANPalletCommandSpec.calculate_crc(fixed_payload + variable_payload))
            ucan_communicator._process_transport_message({'cc_address': cc_address,
                                                          'nr_can_bytes': 8,
                                                          'payload': [129] + fixed_payload})
            ucan_communicator._process_transport_message({'cc_address': cc_address,
                                                          'nr_can_bytes': length + 5,
                                                          'payload': [0] + variable_payload + crc_payload})
            self.assertDictEqual(consumer.get(1), {'other': variable_payload})

    def test_string_parsing(self):
        aio_communicator = Mock()
        ucan_communicator = UCANCommunicator(aio_communicator=aio_communicator, verbose=True)
        cc_address = '000.000.000.000'
        ucan_address = '000.000.000'
        pallet_type = PalletType.MCU_ID_REQUEST  # Not important for this test
        foo = 'XY'  # 2 chars max, otherwise more segments are needed and the test might get too complex

        # Build response-only command
        command = UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                        pallet_type=pallet_type,
                                        response_fields=[StringField('foo')])
        ucan_communicator.do_command(cc_address, command, ucan_address, {}, timeout=None)
        consumer = ucan_communicator._consumers[cc_address][0]

        # Build and validate fake reply from AIO
        payload_segment_1 = [0, 0, 0, 0, 0, 0, PalletType.MCU_ID_REPLY]
        payload_segment_2 = [ord(x) for x in '{0}\x00'.format(foo)]
        crc_payload = Int32Field.encode_bytes(UCANPalletCommandSpec.calculate_crc(payload_segment_1 + payload_segment_2))
        payload_segment_2 += crc_payload
        ucan_communicator._process_transport_message({'cc_address': cc_address,
                                                      'nr_can_bytes': 8,
                                                      'payload': [129] + payload_segment_1})
        ucan_communicator._process_transport_message({'cc_address': cc_address,
                                                      'nr_can_bytes': 8,
                                                      'payload': [0] + payload_segment_2})
        self.assertDictEqual(consumer.get(1), {'foo': foo})

    def test_bootload_lock(self):
        aio_communicator = Mock()
        ucan_communicator = UCANCommunicator(aio_communicator=aio_communicator, verbose=True)
        cc_address = '000.000.000.000'
        ucan_address = '000.000.000'

        command = UCANCommandSpec(sid=SID.NORMAL_COMMAND,
                                  instruction=Instruction(instruction=[0, 0]),
                                  identifier=AddressField('ucan_address', 3))
        ucan_communicator.do_command(cc_address, command, ucan_address, {}, timeout=None)

        command = UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                        pallet_type=PalletType.MCU_ID_REPLY)
        ucan_communicator.do_command(cc_address, command, ucan_address, {}, timeout=None)
        pallet_consumer = ucan_communicator._consumers[cc_address][-1]  # Load last consumer

        command = UCANCommandSpec(sid=SID.NORMAL_COMMAND,
                                  instruction=Instruction(instruction=[0, 0]),
                                  identifier=AddressField('ucan_address', 3))
        with self.assertRaises(BootloadingException):
            ucan_communicator.do_command(cc_address, command, ucan_address, {}, timeout=None)

        command = UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                        pallet_type=PalletType.MCU_ID_REPLY)
        with self.assertRaises(BootloadingException):
            ucan_communicator.do_command(cc_address, command, ucan_address, {}, timeout=None)

        try:
            pallet_consumer.get(0.1)
        except Exception:
            pass  #

        command = UCANCommandSpec(sid=SID.NORMAL_COMMAND,
                                  instruction=Instruction(instruction=[0, 0]),
                                  identifier=AddressField('ucan_address', 3))
        ucan_communicator.do_command(cc_address, command, ucan_address, {}, timeout=None)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
