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
from master import master_api, eeprom_models
from master.outputs import OutputStatus
from master.master_communicator import BackgroundConsumer
from serial_utils import CommunicationTimedOutException

logger = logging.getLogger("openmotics")


class MasterClassicController(MasterController):

    @provides('master_controller')
    @scope(SingletonScope)
    @inject(master_communicator='master_classic_communicator', eeprom_controller='eeprom_controller')
    def __init__(self, master_communicator, eeprom_controller):
        """
        :type master_communicator: master.master_communicator.MasterCommunicator
        :type eeprom_controller: master.eeprom_controller.EepromController
        """
        super(MasterClassicController, self).__init__(master_communicator)
        self._eeprom_controller = eeprom_controller

        self._output_status = OutputStatus(on_output_change=self._output_changed)
        self._synchronization_thread = Thread(target=self._synchronize, name='ClassicMasterSynchronization')
        self._master_version = None
        self._master_online = False
        self._output_interval = 600
        self._output_last_updated = 0
        self._output_config = {}

        self._master_communicator.register_consumer(
            BackgroundConsumer(master_api.output_list(), 0, self._on_master_output_change, True)
        )

    #################
    # Private stuff #
    #################

    def _synchronize(self):
        while True:
            try:
                self._get_master_version()
                # Refresh if required
                if self._output_last_updated + self._output_interval < time.time():
                    self._refresh_outputs()
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

    def _get_master_version(self):
        if self._master_version is None:
            status_info = self._master_communicator.do_command(master_api.status())
            self._master_version = int(status_info['f1']), int(status_info['f2']), int(status_info['f3'])
            self._set_master_state(True)

    def _set_master_state(self, online):
        if online != self._master_online:
            self._master_online = online

    #######################
    # Internal management #
    #######################

    def start(self):
        super(MasterClassicController, self).start()
        self._synchronization_thread.start()

    ##############
    # Public API #
    ##############

    # Memory (eeprom/fram)

    def eeprom_read_page(self, page):
        # TODO: Use eeprom controller
        return self._master_communicator.do_command(master_api.eeprom_list(), {'bank': page})['data']

    def fram_read_page(self, page):
        raise NotImplementedError('A classic master does not support FRAM')

    # Input

    def load_input(self, input_id, fields=None):
        o = self._eeprom_controller.read(eeprom_models.InputConfiguration, input_id, fields)
        if o.module_type not in ['i', 'I']:  # Only return 'real' inputs
            raise TypeError('The given id is not an input')
        return o.serialize()

    def load_inputs(self, fields=None):
        return [o.serialize() for o in self._eeprom_controller.read_all(eeprom_models.InputConfiguration, fields)
                if o.module_type in ['i', 'I']]  # Only return 'real' inputs

    def save_inputs(self, inputs, fields=None):
        for _input in inputs:
            self._eeprom_controller.write(eeprom_models.InputConfiguration.deserialize(_input))

    # Outputs

    def set_output(self, output_id, state):
        if output_id < 0 or output_id > 240:
            raise ValueError('Output ID not in range 0 <= id <= 240: %d' % output_id)

        if state:
            self._master_communicator.do_command(
                master_api.basic_action(),
                {'action_type': master_api.BA_LIGHT_ON, 'action_number': output_id}
            )
        else:
            self._master_communicator.do_command(
                master_api.basic_action(),
                {'action_type': master_api.BA_LIGHT_OFF, 'action_number': output_id}
            )

    def toggle_output(self, output_id):
        if output_id < 0 or output_id > 240:
            raise ValueError('Output ID not in range 0 <= id <= 240: %d' % output_id)

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_LIGHT_TOGGLE, 'action_number': output_id}
        )

    def load_output(self, output_id, fields=None):
        return self._eeprom_controller.read(eeprom_models.OutputConfiguration, output_id, fields).serialize()

    def load_outputs(self, fields=None):
        return [o.serialize() for o in self._eeprom_controller.read_all(eeprom_models.OutputConfiguration, fields)]

    def save_outputs(self, outputs, fields=None):
        for output in outputs:
            output_nr, timer = output['id'], output.get('timer')
            self._eeprom_controller.write(eeprom_models.OutputConfiguration.deserialize(output))
            if timer is not None:
                self._master_communicator.do_command(
                    master_api.write_timer(),
                    {'id': output_nr, 'timer': timer}
                )
        self._output_last_updated = 0

    def get_output_statuses(self):
        return self._output_status.get_outputs()

    def _refresh_outputs(self):
        self._output_config = self.load_outputs()
        number_of_outputs = self._master_communicator.do_command(master_api.number_of_io_modules())['out'] * 8
        outputs = []
        for i in xrange(number_of_outputs):
            outputs.append(self._master_communicator.do_command(master_api.read_output(), {'id': i}))
        self._output_status.full_update(outputs)
        self._output_last_updated = time.time()

    def _output_changed(self, output_id, status):
        """ Executed by the Output Status tracker when an output changed state """
        event_status = {'on': status['on']}
        # 1. only add value to status when handling dimmers
        if self._output_config[output_id]['module_type'] in ['d', 'D']:
            event_status['value'] = status['value']
        # 2. format response data
        event_data = {'id': output_id,
                      'status': event_status,
                      'location': {'room_id': self._output_config[output_id]['room']}}
        for callback in self._event_callbacks:
            callback(MasterEvent(event_type=MasterEvent.Types.OUTPUT_CHANGE, data=event_data))

    def _on_master_output_change(self, data):
        """ Triggers when the master informs us of an Output state change """
        self._output_status.partial_update(data['outputs'])

    # Shutters

    def shutter_up(self, shutter_id):
        self._master_communicator.do_basic_action(master_api.BA_SHUTTER_UP, shutter_id)

    def shutter_down(self, shutter_id):
        self._master_communicator.do_basic_action(master_api.BA_SHUTTER_DOWN, shutter_id)

    def shutter_stop(self, shutter_id):
        self._master_communicator.do_basic_action(master_api.BA_SHUTTER_STOP, shutter_id)
