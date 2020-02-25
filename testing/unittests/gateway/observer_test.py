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
""""
Tests for InputStatus.
"""

import unittest

import mock
import xmlrunner
from gateway.observer import Observer
from ioc import Scope, SetTestMode, SetUpTestInjections
from master.inputs import InputStatus


class ObserverTest(unittest.TestCase):
    """ Tests for Observer. """

    @classmethod
    def setUpClass(cls):
        SetTestMode()

    def test_get_inputs(self):
        observer = get_observer()
        observer.set_gateway_api(mock.Mock())
        input_status = {'id': 1, 'output': 2, 'status': True}
        with mock.patch.object(InputStatus, 'get_inputs',
                               return_value=[input_status]):
            inputs = observer.get_inputs()
            self.assertEqual([1], [x['id'] for x in inputs])

    def test_get_recent_inputs(self):
        observer = get_observer()
        observer.set_gateway_api(mock.Mock())
        input_status = {'id': 1, 'output': 2, 'status': True}
        with mock.patch.object(InputStatus, 'get_recent',
                               return_value=[input_status]):
            inputs = observer.get_recent()
            self.assertEqual([1], [x['id'] for x in inputs])


@Scope
def get_observer():
    SetUpTestInjections(configuration_controller=mock.Mock(),
                        eeprom_controller=mock.Mock(),
                        master_communicator=mock.Mock())
    from gateway.hal.master_controller_classic import MasterClassicController
    master = MasterClassicController()
    return Observer(master_controller=master,
                    message_client=mock.Mock(),
                    shutter_controller=mock.Mock())


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
