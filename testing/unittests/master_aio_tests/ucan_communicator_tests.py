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
from master_aio.ucan_communicator import UCANCommunicator, SID
from master_aio.ucan_command import UCANPalletCommandSpec
from master_aio.fields import AddressField, ByteArrayField, ByteField, Int32Field


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

        for length in [1, 3]:
            pallet_type = 1  # TODO: Use enum
            command = UCANPalletCommandSpec(identifier=AddressField('ucan_address', 3),
                                            pallet_type=pallet_type,
                                            request_fields=[ByteField('foo'), ByteField('bar')],
                                            response_fields=[ByteArrayField('other', length)])
            received_commands = []
            ucan_communicator.do_command(cc_address, command, ucan_address, {'foo': 1,
                                                                             'bar': 2}, timeout=None)
            self.assertEqual(len(received_commands), 2)
            self.assertDictEqual(received_commands[0], {'cc_address': cc_address,
                                                        'nr_can_bytes': 8,
                                                        'payload': [129, 0, 0, 0, 0, 0, 0, pallet_type],
                                                        'sid': SID.BOOTLOADER_PALLET})
            self.assertDictEqual(received_commands[1], {'cc_address': cc_address,
                                                        'nr_can_bytes': 7,
                                                        'payload': [0, 1, 2, 218, 67, 86, 53, 0],
                                                        #                    +-------------+ = checksum
                                                        'sid': SID.BOOTLOADER_PALLET})

            consumer = ucan_communicator._consumers[cc_address][0]
            payload = [0, 1, 2, 3, 4, 5, 6] + range(7, 7 + length)
            crc_payload = Int32Field.encode_bytes(UCANPalletCommandSpec.calculate_crc(payload))
            ucan_communicator._process_transport_message({'cc_address': cc_address,
                                                          'nr_can_bytes': 8,
                                                          'payload': [129, 0, 1, 2, 3, 4, 5, 6]})
            ucan_communicator._process_transport_message({'cc_address': cc_address,
                                                          'nr_can_bytes': length + 5,
                                                          'payload': [0] + range(7, 7 + length) + crc_payload})
            self.assertDictEqual(consumer.get(1), {'other': range(7, 7 + length)})


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
