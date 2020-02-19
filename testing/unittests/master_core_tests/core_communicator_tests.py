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
import unittest

import mock
import xmlrunner

import master_core.core_communicator
from ioc import SetTestMode, SetUpTestInjections
from master_core.core_communicator import Consumer, CoreCommunicator


class CoreCommunicatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SetTestMode()

    def test_do_command_exception_discard_cid(self):
        communicator = CoreCommunicator(controller_serial=mock.Mock())
        with mock.patch.object(communicator, 'discard_cid') as discard:
            self.assertRaises(AttributeError, communicator.do_command, None, {})
            discard.assert_called_with(2)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
