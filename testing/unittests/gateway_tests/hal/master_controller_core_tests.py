import mock
import unittest
import xmlrunner
from ioc import Scope, SetTestMode, SetUpTestInjections
import gateway.hal.master_controller_core
from gateway.hal.master_controller_core import MasterCoreController
from master_core.memory_models import InputConfiguration
from master_core.ucan_communicator import UCANCommunicator


class MasterCoreControllerTest(unittest.TestCase):
    """ Tests for MasterCoreController. """

    @classmethod
    def setUpClass(cls):
        SetTestMode()

    def test_input_module_type(self):
        SetUpTestInjections(memory_files={})
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1)):
            controller = get_core_controller_dummy()
            data = controller.get_input_module_type(1)
            self.assertEquals('I', data)

    def test_load_input(self):
        SetUpTestInjections(memory_files={})
        controller = get_core_controller_dummy()
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1)):
            data = controller.load_input(1)
            self.assertEquals(data['id'], 1)

    def test_load_input_with_fields(self):
        SetUpTestInjections(memory_files={})
        controller = get_core_controller_dummy()
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1)):
            data = controller.load_input(1, fields=['module_type'])
            self.assertEquals(data['id'], 1)
            self.assertIn('module_type', data)
            self.assertNotIn('name', data)

    def test_load_input_with_invalid_type(self):
        SetUpTestInjections(memory_files={})
        controller = get_core_controller_dummy()
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1, module_type='O')):
            self.assertRaises(TypeError, controller.load_input, 1)

    def test_load_inputs(self):
        SetUpTestInjections(memory_files={})
        input_modules = map(get_input_dummy, xrange(1, 17))
        controller = get_core_controller_dummy({'output': 0, 'input': 2})
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               side_effect=input_modules):
            inputs = controller.load_inputs()
            self.assertEqual([x['id'] for x in inputs], range(1, 17))

    def test_load_inputs_skips_invalid_type(self):
        SetUpTestInjections(memory_files={})
        input_modules = map(get_input_dummy, xrange(1, 9))
        input_modules += map(lambda i: get_input_dummy(i, module_type='O'), xrange(9, 17))
        controller = get_core_controller_dummy({'output': 0, 'input': 2})
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               side_effect=input_modules):
            inputs = controller.load_inputs()
            self.assertNotIn(10, [x['id'] for x in inputs])

    def test_save_inputs(self):
        SetUpTestInjections(memory_files={})
        controller = get_core_controller_dummy()
        data = [{'id': 1, 'name': 'foo', 'module_type': 'I'},
                {'id': 2, 'name': 'bar', 'module_type': 'I'}]
        input_mock = mock.Mock(InputConfiguration)
        with mock.patch.object(InputConfiguration, 'deserialize', return_value=input_mock) as deserialize, \
             mock.patch.object(input_mock, 'save', return_value=None) as save:
            controller.save_inputs(data)
            self.assertIn(mock.call({'id': 1, 'name': 'foo'}), deserialize.call_args_list)
            self.assertIn(mock.call({'id': 2, 'name': 'bar'}), deserialize.call_args_list)
            save.assert_called_with()


@Scope
def get_core_controller_dummy(command_data=None):
    from master.master_communicator import MasterCommunicator
    communicator_mock = mock.Mock(MasterCommunicator)
    communicator_mock.do_command.return_value = command_data or {}
    SetUpTestInjections(master_communicator=communicator_mock)
    ucan_mock = UCANCommunicator()
    SetUpTestInjections(ucan_communicator=ucan_mock)
    return MasterCoreController()


def get_input_dummy(i, module_type='I'):
    return InputConfiguration.deserialize({
        'id': i,
        'name': 'foo',
        'input_config': 3,
        'module': {'id': 20 + i,
                   'device_type': module_type,
                   'address': '0.0.0.0',
                   'firmware_version': '0.0.1'}
    })


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
