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
Module for communicating with the Master
"""
import logging
import time
from threading import Thread
from wiring import inject, provides, SingletonScope, scope
from gateway.hal.master_controller import MasterController, MasterEvent
from gateway.maintenance_service import InMaintenanceModeException
from master_core.core_api import CoreAPI
from master_core.core_communicator import BackgroundConsumer
from master_core.events import Event as MasterCoreEvent
from master_core.errors import Error
from master_core.memory_file import MemoryFile, MemoryTypes
from master_core.memory_models import OutputConfiguration
from serial_utils import CommunicationTimedOutException

logger = logging.getLogger("openmotics")


class MasterCoreController(MasterController):

    @provides('master_controller')
    @scope(SingletonScope)
    @inject(master_communicator='master_core_communicator', ucan_communicator='ucan_communicator')
    def __init__(self, master_communicator, ucan_communicator):
        """
        :type master_communicator: master_core.core_communicator.CoreCommunicator
        :type ucan_communicator: master_core.ucan_communicator.UCANCommunicator
        """
        super(MasterCoreController, self).__init__(master_communicator)
        self._ucan_communicator = ucan_communicator
        self._memory_files = {MemoryTypes.EEPROM: MemoryFile(MemoryTypes.EEPROM, self._master_communicator),
                              MemoryTypes.FRAM: MemoryFile(MemoryTypes.FRAM, self._master_communicator)}

        self._synchronization_thread = Thread(target=self._synchronize, name='CoreMasterSynchronization')
        self._master_online = False
        self._output_interval = 600
        self._output_last_updated = 0
        self._output_states = {}

        self._master_communicator.register_consumer(
            BackgroundConsumer(CoreAPI.event_information(), 0, self._handle_event)
        )
        self._master_communicator.register_consumer(
            BackgroundConsumer(CoreAPI.error_information(), 0, lambda e: logger.info('Got master error: {0}'.format(Error(e))))
        )
        self._master_communicator.register_consumer(
            BackgroundConsumer(CoreAPI.ucan_module_information(), 0, lambda i: logger.info('Got ucan module information: {0}'.format(i)))
        )

    #################
    # Private stuff #
    #################

    def _handle_event(self, data):
        core_event = MasterCoreEvent(data)
        logger.info('Got master event: {0}'.format(core_event))
        if core_event.type == MasterCoreEvent.Types.OUTPUT:
            # Update internal state cache
            self._output_states[core_event.data['output']] = {'id': core_event.data['output'],
                                                              'status': 1 if core_event.data['status'] else 0,
                                                              'ctimer': core_event.data['timer_value'],
                                                              'dimmer': core_event.data['dimmer_value']}
            # Generate generic event
            event = MasterEvent(event_type=MasterEvent.Types.OUTPUT_CHANGE,
                                data={'id': core_event.data['output'],
                                      'status': {'on': core_event.data['status'],
                                                 'value': core_event.data['dimmer_value']},
                                      'location': {'room_id': 255}})  # TODO: Missing room
            for callback in self._event_callbacks:
                callback(event)

    def _synchronize(self):
        while True:
            try:
                # Refresh if required
                if self._output_last_updated + self._output_interval < time.time():
                    self._refresh_output_states()
                    self._set_master_state(True)
                time.sleep(1)
            except CommunicationTimedOutException:
                logger.error('Got communication timeout during synchronization, waiting 10 seconds.')
                self._set_master_state(False)
                time.sleep(10)
            except InMaintenanceModeException:
                # This is an expected situation
                time.sleep(10)
            except Exception as ex:
                logger.exception('Unexpected error during synchronization: {0}'.format(ex))
                time.sleep(10)

    def _set_master_state(self, online):
        if online != self._master_online:
            self._master_online = online

    #######################
    # Internal management #
    #######################

    def start(self):
        super(MasterCoreController, self).start()
        self._synchronization_thread.start()

    ##############
    # Public API #
    ##############

    def get_firmware_version(self):
        return 0, 0, 0  # TODO

    # Memory (eeprom/fram)

    def eeprom_read_page(self, page):
        return self._memory_files[MemoryTypes.EEPROM].read_page(page)

    def fram_read_page(self, page):
        return self._memory_files[MemoryTypes.FRAM].read_page(page)

    # Input

    def get_input_module_type(self, input_module_id):
        return 'i'  # TODO

    def load_input(self, input_id, fields=None):
        return {}  # TODO

    def load_inputs(self, fields=None):
        return []  # TODO

    def save_inputs(self, inputs, fields=None):
        raise NotImplementedError()  # TODO

    # Outputs

    def set_output(self, output_id, state, dimmer=None, timer=None):
        # TODO: Use `dimmer` and `timer`
        _ = dimmer, timer
        action = 1 if state else 0
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 0, 'action': action,
                                                                      'device_nr': output_id,
                                                                      'extra_parameter': 0})

    def toggle_output(self, output_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 0, 'action': 16,
                                                                      'device_nr': output_id,
                                                                      'extra_parameter': 0})

    def load_output(self, output_id, fields=None):
        output = OutputConfiguration(output_id, self._memory_files)
        timer = 0
        if output.timer_type == 2:
            timer = output.timer_value
        elif output.timer_type == 1:
            timer = output.timer_value / 10
        data = {'id': output.id,
                'module_type': output.module.device_type,  # TODO: Proper translation
                'name': output.name,
                'timer': timer,  # TODO: Proper calculation
                'floor': 255,
                'type': output.output_type,  # TODO: Proper translation
                'can_led_1_id': 255,
                'can_led_1_function': 'UNKNOWN',
                'can_led_2_id': 255,
                'can_led_2_function': 'UNKNOWN',
                'can_led_3_id': 255,
                'can_led_3_function': 'UNKNOWN',
                'can_led_4_id': 255,
                'can_led_4_function': 'UNKNOWN',
                'room': 255}
        if fields is None:
            return data
        return {field: data[field] for field in fields}

    def load_outputs(self, fields=None):
        amount_output_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['output']
        outputs = []
        for i in xrange(amount_output_modules * 8):
            outputs.append(self.load_output(i, fields))
        return outputs

    def save_outputs(self, outputs, fields=None):
        for output_data in outputs:
            new_data = {'id': output_data['id'],
                        'name': output_data['name']}  # TODO: Rest of the mapping
            output = OutputConfiguration.deserialize(new_data, self._memory_files)
            output.save()

    def get_output_statuses(self):
        return self._output_states.values()

    def _refresh_output_states(self):
        amount_output_modules = self._master_communicator.do_command(CoreAPI.general_configuration_number_of_modules(), {})['output']
        for i in xrange(amount_output_modules * 8):
            state = self._master_communicator.do_command(CoreAPI.output_detail(), {'device_nr': i})
            self._output_states[i] = {'id': i,
                                      'status': state['status'],  # 1 or 0
                                      'ctimer': state['timer'],
                                      'dimmer': state['dimmer']}
        self._output_last_updated = time.time()

    # Shutters

    def shutter_up(self, shutter_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 10, 'action': 1,
                                                                      'device_nr': shutter_id,
                                                                      'extra_parameter': 0})

    def shutter_down(self, shutter_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 10, 'action': 2,
                                                                      'device_nr': shutter_id,
                                                                      'extra_parameter': 0})

    def shutter_stop(self, shutter_id):
        self._master_communicator.do_command(CoreAPI.basic_action(), {'type': 10, 'action': 0,
                                                                      'device_nr': shutter_id,
                                                                      'extra_parameter': 0})
