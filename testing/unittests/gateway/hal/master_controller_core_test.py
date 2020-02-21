import time
import unittest
from Queue import Queue

import gateway.hal.master_controller_core
import mock
import xmlrunner
from gateway.hal.master_controller import MasterEvent
from ioc import Scope, SetTestMode, SetUpTestInjections
from master import eeprom_models
from master.eeprom_controller import EepromController
from master_core.core_api import CoreAPI
from master_core.core_communicator import BackgroundConsumer
from master_core.memory_models import InputConfiguration
from master_core.ucan_communicator import UCANCommunicator


class MasterCoreControllerTest(unittest.TestCase):
    """ Tests for MasterCoreController. """

    @classmethod
    def setUpClass(cls):
        SetTestMode()
        SetUpTestInjections(memory_files={})

    def test_input_module_type(self):
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1)):
            controller = get_core_controller_dummy()
            data = controller.get_input_module_type(1)
            self.assertEquals('I', data)

    def test_load_input(self):
        controller = get_core_controller_dummy()
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1)):
            data = controller.load_input(1)
            self.assertEquals(data['id'], 1)

    def test_load_input_with_fields(self):
        controller = get_core_controller_dummy()
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1)):
            data = controller.load_input(1, fields=['module_type'])
            self.assertEquals(data['id'], 1)
            self.assertIn('module_type', data)
            self.assertNotIn('name', data)

    def test_load_input_with_invalid_type(self):
        controller = get_core_controller_dummy()
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1, module_type='O')):
            self.assertRaises(TypeError, controller.load_input, 1)

    def test_load_inputs(self):
        input_modules = map(get_input_dummy, xrange(1, 17))
        controller = get_core_controller_dummy({'output': 0, 'input': 2})
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               side_effect=input_modules):
            inputs = controller.load_inputs()
            self.assertEqual([x['id'] for x in inputs], range(1, 17))

    def test_load_inputs_skips_invalid_type(self):
        input_modules = map(get_input_dummy, xrange(1, 9))
        input_modules += map(lambda i: get_input_dummy(i, module_type='O'), xrange(9, 17))
        controller = get_core_controller_dummy({'output': 0, 'input': 2})
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               side_effect=input_modules):
            inputs = controller.load_inputs()
            self.assertNotIn(10, [x['id'] for x in inputs])

    def test_save_inputs(self):
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

    def test_inputs_with_status(self):
        controller = get_core_controller_dummy()
        from gateway.hal.master_controller_core import MasterInputState
        with mock.patch.object(MasterInputState, 'get_inputs', return_value=[]) as get:
            controller.get_inputs_with_status()
            get.assert_called_with()

    def test_recent_inputs(self):
        controller = get_core_controller_dummy()
        from gateway.hal.master_controller_core import MasterInputState
        with mock.patch.object(MasterInputState, 'get_recent', return_value=[]) as get:
            controller.get_recent_inputs()
            get.assert_called_with()

    def test_event_consumer(self):
        with mock.patch.object(gateway.hal.master_controller_core, 'BackgroundConsumer',
                               return_value=None) as new_consumer:
            get_core_controller_dummy()
            expected_call = mock.call(CoreAPI.event_information(), 0, mock.ANY)
            self.assertIn(expected_call, new_consumer.call_args_list)

    def test_subscribe_input_events(self):
        consumer_list = []

        def new_consumer(*args):
            consumer = BackgroundConsumer(*args)
            consumer_list.append(consumer)
            return consumer

        subscriber = mock.Mock()
        with mock.patch.object(gateway.hal.master_controller_core, 'BackgroundConsumer',
                               side_effect=new_consumer) as new_consumer:
            controller = get_core_controller_dummy()
        controller.subscribe_event(subscriber.callback)
        new_consumer.assert_called()
        event_data = {'type': 1, 'action': 1, 'device_nr': 2,
                      'data': {}}
        with mock.patch.object(Queue, 'get', return_value=event_data):
            consumer_list[0].deliver()
        expected_event = MasterEvent.deserialize({'type': 'INPUT_CHANGE',
                                                  'data': {'id': 2,
                                                           'status': True,
                                                           'location': {'room_id': 255}}})
        subscriber.callback.assert_called_with(expected_event)


class MasterCoreControllerCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SetTestMode()

    def test_load_input(self):
        SetUpTestInjections(memory_files={})
        core = get_core_controller_dummy()
        with mock.patch.object(gateway.hal.master_controller_core, 'InputConfiguration',
                               return_value=get_input_dummy(1)):
            core_data = core.load_input(1)
        input_module = eeprom_models.InputConfiguration.deserialize(core_data)
        classic = get_classic_controller_dummy([input_module])
        classic_data = classic.load_input(1)
        self.assertEqual(classic_data, core_data)


class MasterInputState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SetTestMode()

    def test_handle_event(self):
        from gateway.hal.master_controller_core import MasterCoreEvent, MasterInputState
        state = MasterInputState()
        core_event = MasterCoreEvent({'type': 1, 'action': 1, 'device_nr': 2, 'data': {}})
        with mock.patch.object(time, 'time', return_value=30):
            event = state.handle_event(core_event)
            expected_data = {'type': 'INPUT_CHANGE',
                             'data': {'id': 2,
                                      'status': True,
                                      'location': {'room_id': 255}}}
            self.assertEqual(expected_data, event.serialize())
            self.assertIn({'id': 2, 'status': 1}, state.get_inputs())

    def test_refresh(self):
        from gateway.hal.master_controller_core import MasterCoreEvent, MasterInputState
        state = MasterInputState(interval=10)
        core_events = [
            MasterCoreEvent({'type': 1, 'action': 1, 'device_nr': 1, 'data': {}}),
            MasterCoreEvent({'type': 1, 'action': 0, 'device_nr': 2, 'data': {}}),
        ]
        with mock.patch.object(time, 'time', return_value=30):
            for core_event in core_events:
                state.handle_event(core_event)
            self.assertTrue(state.should_refresh())
            events = state.refresh([0b00000110])
            self.assertEqual(1, len(events))
            expected_event = MasterEvent(event_type=MasterEvent.Types.INPUT_CHANGE,
                                         data={'id': 2,
                                               'status': True,
                                               'location': {'room_id': 255}})
            self.assertIn(expected_event, events)
            self.assertFalse(state.should_refresh())

            events = state.refresh([0b00000110])
            self.assertEqual([], events)

        with mock.patch.object(time, 'time', return_value=60):
            self.assertTrue(state.should_refresh())

    def test_recent(self):
        from gateway.hal.master_controller_core import MasterCoreEvent, MasterInputState, MasterInputValue
        state = MasterInputState()
        with mock.patch.object(time, 'time', return_value=0):
            core_event = MasterCoreEvent({'type': 1, 'action': 1, 'device_nr': 1, 'data': {}})
            state.handle_event(core_event)
            self.assertEqual([1], state.get_recent())

        with mock.patch.object(time, 'time', return_value=30):
            for i in xrange(2, 10):
                core_event = MasterCoreEvent({'type': 1, 'action': 1, 'device_nr': i, 'data': {}})
                state.handle_event(core_event)
            devices = state.get_recent()
            self.assertEqual(5, len(devices))
            self.assertNotIn(1, devices)

        with mock.patch.object(time, 'time', return_value=60):
            self.assertEqual(0, len(state.get_recent()))

        with mock.patch.object(time, 'time', return_value=60):
            state.handle_event(MasterCoreEvent({'type': 1, 'action': 0, 'device_nr': 1, 'data': {}}))
            state.handle_event(MasterCoreEvent({'type': 1, 'action': 1, 'device_nr': 2, 'data': {}}))
            devices = state.get_recent()
            self.assertIn(1, devices)
            self.assertNotIn(2, devices)


@Scope
def get_core_controller_dummy(command_data=None):
    from gateway.hal.master_controller_core import MasterCoreController
    from master.master_communicator import MasterCommunicator
    communicator_mock = mock.Mock(MasterCommunicator)
    communicator_mock.do_command.return_value = command_data or {}
    SetUpTestInjections(master_communicator=communicator_mock)
    ucan_mock = UCANCommunicator()
    SetUpTestInjections(ucan_communicator=ucan_mock)
    return MasterCoreController()


@Scope
def get_classic_controller_dummy(inputs):
    from master.master_communicator import MasterCommunicator
    from gateway.hal.master_controller_classic import MasterClassicController
    master_mock = mock.Mock(MasterCommunicator)
    eeprom_mock = mock.Mock(EepromController)
    eeprom_mock.read.return_value = inputs[0]
    eeprom_mock.read_all.return_value = inputs
    SetUpTestInjections(master_communicator=master_mock, eeprom_controller=eeprom_mock)
    return MasterClassicController()


def get_input_dummy(i, module_type='I'):
    return InputConfiguration.deserialize({
        'id': i,
        'name': 'foo',
        'module': {'id': 20 + i,
                   'device_type': module_type,
                   'address': '0.0.0.0',
                   'firmware_version': '0.0.1'}
    })


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
