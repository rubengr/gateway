"""
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
import unittest

import gateway.hal.master_controller_classic
import master.master_api
import master.master_communicator
import mock
import xmlrunner
from ioc import Scope, SetTestMode, SetUpTestInjections
from master.eeprom_controller import EepromController
from master.eeprom_models import InputConfiguration
from master.inputs import InputStatus
from master.master_communicator import BackgroundConsumer


class MasterClassicControllerTest(unittest.TestCase):
    """ Tests for MasterClassicController. """

    @classmethod
    def setUpClass(cls):
        SetTestMode()

    def test_input_module_type(self):
        input_data = {'id': 1, 'module_type': 'I'}
        controller = get_classic_controller_dummy([
            InputConfiguration.deserialize(input_data)
        ])
        data = controller.get_input_module_type(1)
        self.assertEquals(data, 'I')

    def test_load_input(self):
        input_data = {'id': 1, 'module_type': 'I'}
        controller = get_classic_controller_dummy([
            InputConfiguration.deserialize(input_data)
        ])
        data = controller.load_input(1)
        self.assertEquals(data['id'], 1)

    def test_load_input_with_invalid_type(self):
        input_data = {'id': 1, 'module_type': 'O'}
        controller = get_classic_controller_dummy([
            InputConfiguration.deserialize(input_data)
        ])
        self.assertRaises(TypeError, controller.load_input, 1)

    def test_load_inputs(self):
        input_data1 = {'id': 1, 'module_type': 'I'}
        input_data2 = {'id': 2, 'module_type': 'I'}
        controller = get_classic_controller_dummy([
            InputConfiguration.deserialize(input_data1),
            InputConfiguration.deserialize(input_data2)
        ])
        inputs = controller.load_inputs()
        self.assertEquals([x['id'] for x in inputs], [1, 2])

    def test_load_inputs_skips_invalid_type(self):
        input_data1 = {'id': 1, 'module_type': 'I'}
        input_data2 = {'id': 2, 'module_type': 'O'}
        controller = get_classic_controller_dummy([
            InputConfiguration.deserialize(input_data1),
            InputConfiguration.deserialize(input_data2)
        ])
        inputs = controller.load_inputs()
        self.assertEquals([x['id'] for x in inputs], [1])

    def test_input_event_consumer(self):
        with mock.patch.object(gateway.hal.master_controller_classic, 'BackgroundConsumer',
                               return_value=None) as consumer:
            get_classic_controller_dummy()
            expected_call = mock.call(master.master_api.input_list(None), 0, mock.ANY)
            self.assertIn(expected_call, consumer.call_args_list)

    def test_subscribe_input_events(self):
        consumer_list = []

        def new_consumer(*args):
            consumer = BackgroundConsumer(*args)
            consumer_list.append(consumer)
            return consumer

        subscriber = mock.Mock()
        with mock.patch.object(gateway.hal.master_controller_classic, 'BackgroundConsumer',
                               side_effect=new_consumer) as new_consumer:
            controller = get_classic_controller_dummy()
            controller._input_config = {1: {}}  # TODO: cleanup
            controller.subscribe_event(subscriber.callback)
            new_consumer.assert_called()
            consumer_list[0].deliver({'input': 1})
            from gateway.hal.master_controller_classic import MasterEvent
            expected_event = MasterEvent.deserialize({'type': 'INPUT_CHANGE',
                                                      'data': {'id': 1,
                                                               'status': True,
                                                               'location': {'room_id': 255}}})
            subscriber.callback.assert_called_with(expected_event)

    def test_get_inputs_with_status(self):
        classic = get_classic_controller_dummy()
        with mock.patch.object(InputStatus, 'get_inputs', return_value=[]) as get:
            classic.get_inputs_with_status()
            self.assertIn(mock.call(), get.call_args_list)

    def test_get_recent_inputs(self):
        classic = get_classic_controller_dummy()
        with mock.patch.object(InputStatus, 'get_recent', return_value=[]) as get:
            classic.get_recent_inputs()
            self.assertIn(mock.call(), get.call_args_list)


@Scope
def get_classic_controller_dummy(inputs=None):
    from gateway.hal.master_controller_classic import MasterClassicController
    from master.master_communicator import MasterCommunicator
    master_mock = mock.Mock(MasterCommunicator)
    eeprom_mock = mock.Mock(EepromController)
    eeprom_mock.read.return_value = inputs[0] if inputs else []
    eeprom_mock.read_all.return_value = inputs
    SetUpTestInjections(master_communicator=master_mock, eeprom_controller=eeprom_mock)
    return MasterClassicController()


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
