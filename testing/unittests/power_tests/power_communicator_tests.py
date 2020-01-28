# Copyright (C) 2016 OpenMotics BV
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
Tests for PowerCommunicator module.
"""

import unittest
import xmlrunner
import os
import time
from ioc import SetTestMode, SetUpTestInjections
import power.power_api as power_api
from power.power_controller import PowerController
from power.power_communicator import PowerCommunicator, InAddressModeException

from serial_tests import SerialMock, sin, sout
from serial_utils import CommunicationTimedOutException, RS485


class PowerCommunicatorTest(unittest.TestCase):
    """ Tests for PowerCommunicator class """

    FILE = "test.db"

    @classmethod
    def setUpClass(cls):
        SetTestMode()

    def setUp(self):
        """ Run before each test. """
        if os.path.exists(PowerCommunicatorTest.FILE):
            os.remove(PowerCommunicatorTest.FILE)

    def tearDown(self):
        """ Run after each test. """
        if os.path.exists(PowerCommunicatorTest.FILE):
            os.remove(PowerCommunicatorTest.FILE)

    @staticmethod
    def _get_communicator(serial_mock, time_keeper_period=0, address_mode_timeout=60, power_controller=None):
        """ Get a PowerCommunicator. """
        SetUpTestInjections(power_db=PowerCommunicatorTest.FILE,
                            power_serial=serial_mock)
        if power_controller is not None:
            SetUpTestInjections(power_controller=power_controller)
        return PowerCommunicator(time_keeper_period=time_keeper_period,
                                 address_mode_timeout=address_mode_timeout)

    def test_do_command(self):
        """ Test for standard behavior PowerCommunicator.do_command. """
        action = power_api.get_voltage(power_api.POWER_MODULE)

        serial_mock = RS485(SerialMock(
                        [sin(action.create_input(1, 1)),
                         sout(action.create_output(1, 1, 49.5))]))

        comm = PowerCommunicatorTest._get_communicator(serial_mock)
        comm.start()

        output = comm.do_command(1, action)

        self.assertEquals((49.5, ), output)

        self.assertEquals(14, comm.get_bytes_written())
        self.assertEquals(18, comm.get_bytes_read())

    def test_do_command_timeout_once(self):
        """ Test for timeout in PowerCommunicator.do_command. """
        action = power_api.get_voltage(power_api.POWER_MODULE)

        serial_mock = RS485(SerialMock([sin(action.create_input(1, 1)), sout(''),
                                        sin(action.create_input(1, 2)),
                                        sout(action.create_output(1, 2, 49.5))]))

        comm = PowerCommunicatorTest._get_communicator(serial_mock)
        comm.start()

        output = comm.do_command(1, action)
        self.assertEquals((49.5, ), output)

    def test_do_command_timeout_twice(self):
        """ Test for timeout in PowerCommunicator.do_command. """
        action = power_api.get_voltage(power_api.POWER_MODULE)

        serial_mock = RS485(SerialMock([sin(action.create_input(1, 1)), sout(''),
                                        sin(action.create_input(1, 2)),
                                        sout('')]))

        comm = PowerCommunicatorTest._get_communicator(serial_mock)
        comm.start()

        with self.assertRaises(CommunicationTimedOutException):
            comm.do_command(1, action)

    def test_do_command_split_data(self):
        """ Test PowerCommunicator.do_command when the data is split over multiple reads. """
        action = power_api.get_voltage(power_api.POWER_MODULE)
        out = action.create_output(1, 1, 49.5)

        serial_mock = RS485(SerialMock(
                        [sin(action.create_input(1, 1)),
                         sout(out[:5]), sout(out[5:])]))

        comm = PowerCommunicatorTest._get_communicator(serial_mock)
        comm.start()

        output = comm.do_command(1, action)

        self.assertEquals((49.5, ), output)

    def test_wrong_response(self):
        """ Test PowerCommunicator.do_command when the power module returns a wrong response. """
        action_1 = power_api.get_voltage(power_api.POWER_MODULE)
        action_2 = power_api.get_frequency(power_api.POWER_MODULE)

        serial_mock = RS485(SerialMock([sin(action_1.create_input(1, 1)),
                                        sout(action_2.create_output(3, 2, 49.5))]))

        comm = PowerCommunicatorTest._get_communicator(serial_mock)
        comm.start()

        with self.assertRaises(Exception):
            comm.do_command(1, action_1)

    def test_address_mode(self):
        """ Test the address mode. """
        sad = power_api.set_addressmode(power_api.POWER_MODULE)
        sad_p1c = power_api.set_addressmode(power_api.P1_CONCENTRATOR)

        serial_mock = RS485(SerialMock(
            [sin(sad.create_input(power_api.BROADCAST_ADDRESS, 1, power_api.ADDRESS_MODE)),
             sin(sad_p1c.create_input(power_api.BROADCAST_ADDRESS, 2, power_api.ADDRESS_MODE)),
             sout(power_api.want_an_address(power_api.POWER_MODULE).create_output(0, 0)),
             sin(power_api.set_address(power_api.POWER_MODULE).create_input(0, 0, 1)),
             sout(power_api.want_an_address(power_api.ENERGY_MODULE).create_output(0, 0)),
             sin(power_api.set_address(power_api.ENERGY_MODULE).create_input(0, 0, 2)),
             sout(power_api.want_an_address(power_api.P1_CONCENTRATOR).create_output(0, 0)),
             sin(power_api.set_address(power_api.P1_CONCENTRATOR).create_input(0, 0, 3)),
             sout(''),  # Timeout read after 1 second
             sin(sad.create_input(power_api.BROADCAST_ADDRESS, 3, power_api.NORMAL_MODE)),
             sin(sad_p1c.create_input(power_api.BROADCAST_ADDRESS, 4, power_api.NORMAL_MODE))],
            1
        ))
        SetUpTestInjections(power_db=PowerCommunicatorTest.FILE)

        controller = PowerController()
        comm = PowerCommunicatorTest._get_communicator(serial_mock, power_controller=controller)
        comm.start()

        self.assertEqual(controller.get_free_address(), 1)

        comm.start_address_mode()
        self.assertTrue(comm.in_address_mode())
        time.sleep(0.5)
        comm.stop_address_mode()

        self.assertEqual(controller.get_free_address(), 4)
        self.assertFalse(comm.in_address_mode())

    def test_do_command_in_address_mode(self):
        """ Test the behavior of do_command in address mode."""
        action = power_api.get_voltage(power_api.POWER_MODULE)
        sad = power_api.set_addressmode(power_api.POWER_MODULE)
        sad_p1c = power_api.set_addressmode(power_api.P1_CONCENTRATOR)

        serial_mock = RS485(SerialMock(
            [sin(sad.create_input(power_api.BROADCAST_ADDRESS, 1, power_api.ADDRESS_MODE)),
             sin(sad_p1c.create_input(power_api.BROADCAST_ADDRESS, 2, power_api.ADDRESS_MODE)),
             sout(''),  # Timeout read after 1 second
             sin(sad.create_input(power_api.BROADCAST_ADDRESS, 3, power_api.NORMAL_MODE)),
             sin(sad_p1c.create_input(power_api.BROADCAST_ADDRESS, 4, power_api.NORMAL_MODE)),
             sin(action.create_input(1, 5)),
             sout(action.create_output(1, 5, 49.5))],
            1
        ))

        comm = PowerCommunicatorTest._get_communicator(serial_mock)
        comm.start()

        comm.start_address_mode()

        with self.assertRaises(InAddressModeException):
            comm.do_command(1, action)

        comm.stop_address_mode()

        self.assertEquals((49.5, ), comm.do_command(1, action))

    def test_address_mode_timeout(self):
        """ Test address mode timeout. """
        action = power_api.get_voltage(power_api.POWER_MODULE)
        sad = power_api.set_addressmode(power_api.POWER_MODULE)
        sad_p1c = power_api.set_addressmode(power_api.P1_CONCENTRATOR)

        serial_mock = RS485(SerialMock(
            [sin(sad.create_input(power_api.BROADCAST_ADDRESS, 1, power_api.ADDRESS_MODE)),
             sin(sad_p1c.create_input(power_api.BROADCAST_ADDRESS, 2, power_api.ADDRESS_MODE)),
             sout(''),  # Timeout read after 1 second
             sin(sad.create_input(power_api.BROADCAST_ADDRESS, 3, power_api.NORMAL_MODE)),
             sin(sad_p1c.create_input(power_api.BROADCAST_ADDRESS, 4, power_api.NORMAL_MODE)),
             sin(action.create_input(1, 5)),
             sout(action.create_output(1, 5, 49.5))],
            1
        ))

        comm = PowerCommunicatorTest._get_communicator(serial_mock, address_mode_timeout=1)
        comm.start()

        comm.start_address_mode()
        time.sleep(1.1)

        self.assertEquals((49.5, ), comm.do_command(1, action))

    def test_timekeeper(self):
        """ Test the TimeKeeper. """
        SetUpTestInjections(power_db=PowerCommunicatorTest.FILE)
        power_controller = PowerController()
        power_controller.register_power_module(1, power_api.POWER_MODULE)

        time_action = power_api.set_day_night(power_api.POWER_MODULE)
        times = [power_api.NIGHT for _ in range(8)]
        action = power_api.get_voltage(power_api.POWER_MODULE)

        serial_mock = RS485(SerialMock(
            [sin(time_action.create_input(1, 1, *times)),
             sout(time_action.create_output(1, 1)),
             sin(action.create_input(1, 2)),
             sout(action.create_output(1, 2, 243))],
            1
        ))

        comm = PowerCommunicatorTest._get_communicator(serial_mock, 1, power_controller=power_controller)
        comm.start()

        time.sleep(1.5)

        self.assertEquals((243, ), comm.do_command(1, action))


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
