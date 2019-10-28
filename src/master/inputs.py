# Copyright (C) 2016 OpenMotics BVBA
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
Input status keeps track of the last X pressed inputs, pressed in the last X seconds.
"""

import time
from threading import Lock


class InputStatus(object):
    """ Contains the last Y inputs pressed the last Y seconds. """

    def __init__(self, num_inputs=5, seconds=10):
        """
        Create an InputStatus, specifying the number of inputs to track and
        the number of seconds to keep the data.
        """
        self._num_inputs = num_inputs
        self._seconds = seconds
        self._inputs_status = {}
        self.__state_change_lock = Lock()

    def get_recent(self):
        """ Get the last n triggered inputs. """
        last_inputs = []
        threshold = time.time() - self._seconds
        for input_nr, current_state in self._inputs_status.iteritems():
            last_status_change = current_state.get('last_status_change')
            if last_status_change > threshold:
                last_inputs.append((current_state['id'], current_state['output']))
        # limit result size
        return last_inputs[:self._num_inputs]

    def set_input(self, data):
        """ Set the input status. """
        with self.__state_change_lock:
            now = time.time()
            # parse data
            input_nr = data['input']
            current_state = self._inputs_status.get(input_nr, {})
            current_state['id'] = input_nr
            current_state['last_updated'] = now
            if current_state.get('status') != data['status']:
                current_state['last_status_change'] = now
                current_state['status'] = data['status']
            # optional values (can be None)
            current_state['output'] = data.get('output')
            # store in memory
            self._inputs_status[input_nr] = current_state

    def get_inputs(self):
        """ Get the inputs status. """
        inputs = []
        for input_nr, current_state in self._inputs_status.iteritems():
            inputs.append(current_state)
        return inputs

