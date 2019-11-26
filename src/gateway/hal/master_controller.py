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
import ujson as json
from exceptions import NotImplementedError


class MasterEvent(object):
    """
    MasterEvent object
    """

    class Types(object):
        OUTPUT_CHANGE = 'OUTPUT_CHANGE'

    def __init__(self, event_type, data):
        self.type = event_type
        self.data = data

    def serialize(self):
        return {'type': self.type,
                'data': self.data}

    def __str__(self):
        return json.dumps(self.serialize())

    @staticmethod
    def deserialize(data):
        return MasterEvent(event_type=data['type'],
                           data=data['data'])


class MasterController(object):

    def __init__(self, master_communicator):
        self._master_communicator = master_communicator
        self._event_callbacks = []

    #######################
    # Internal management #
    #######################

    def start(self):
        self._master_communicator.start()

    def stop(self):
        self._master_communicator.stop()

    #################
    # Subscriptions #
    #################

    def subscribe_event(self, callback):
        self._event_callbacks.append(callback)

    ##############
    # Public API #
    ##############

    # TODO: Currently the objects returned here are classic-format dicts. This needs to be changed to intermediate transport objects

    # Memory (eeprom/fram)

    def eeprom_read_page(self, page):
        raise NotImplementedError()

    def fram_read_page(self, page):
        raise NotImplementedError()

    # Input

    def load_input(self, input_id, fields=None):
        raise NotImplementedError()

    def load_inputs(self, fields=None):
        raise NotImplementedError()

    def save_inputs(self, inputs, fields=None):
        raise NotImplementedError()

    # Outputs

    def set_output(self, output_id, state):
        raise NotImplementedError()

    def toggle_output(self, output_id):
        raise NotImplementedError()

    def load_output(self, output_id, fields=None):
        raise NotImplementedError()

    def load_outputs(self, fields=None):
        raise NotImplementedError()

    def save_outputs(self, outputs, fields=None):
        raise NotImplementedError()

    def get_output_statuses(self):
        raise NotImplementedError()

    # Shutters

    def shutter_up(self, shutter_id):
        raise NotImplementedError()

    def shutter_down(self, shutter_id):
        raise NotImplementedError()

    def shutter_stop(self, shutter_id):
        raise NotImplementedError()
