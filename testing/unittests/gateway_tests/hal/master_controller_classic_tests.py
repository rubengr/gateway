import mock
import os
import unittest
import xmlrunner
from ioc import Scope, SetTestMode, SetUpTestInjections
from master.eeprom_controller import EepromController
from master.eeprom_models import InputConfiguration


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


@Scope
def get_classic_controller_dummy(inputs):
    from gateway.hal.master_controller_classic import MasterClassicController
    from master.master_communicator import MasterCommunicator
    master_mock = mock.Mock(MasterCommunicator)
    eeprom_mock = mock.Mock(EepromController)
    eeprom_mock.read.return_value = inputs[0]
    eeprom_mock.read_all.return_value = inputs
    SetUpTestInjections(master_communicator=master_mock, eeprom_controller=eeprom_mock)
    return MasterClassicController()


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
