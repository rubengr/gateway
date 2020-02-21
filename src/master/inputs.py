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
Input status keeps track of the last X pressed inputs, pressed in the last X seconds.
"""

import time
import logging
from threading import Lock

if False:  # MYPY
    from typing import Any, Dict, List

logger = logging.getLogger("openmotics")


class InputStatus(object):
    """ Contains the last Y inputs pressed the last Y seconds. """

    def __init__(self, num_inputs=5, seconds=10, on_input_change=None):
        """
        Create an InputStatus, specifying the number of inputs to track and
        the number of seconds to keep the data.
        """
        self._num_inputs = num_inputs
        self._seconds = seconds
        self._inputs_status = {}
        self._state_change_lock = Lock()
        self._on_input_change = on_input_change

    def _sorted_inputs(self):
        return sorted(self._inputs_status.itervalues(),
                      key=lambda x: x.get('last_status_change'))

    def get_recent(self):
        # type: () -> List[int]
        """ Get the last n triggered inputs. """
        last_inputs = []
        threshold = time.time() - self._seconds
        for current_state in self._sorted_inputs():
            last_status_change = current_state.get('last_status_change')
            if last_status_change > threshold:
                last_inputs.append(current_state['id'])
        # limit result size
        return last_inputs[-self._num_inputs:]

    def set_input(self, data):
        """ Set the input status. """
        with self._state_change_lock:
            now = time.time()
            # parse data
            input_id = data['input']
            current_state = self._inputs_status.get(input_id, {})
            current_state['id'] = input_id
            current_state['last_updated'] = now
            # optional values (can be None)
            current_state['output'] = data.get('output')
            # status update
            if 'status' in data:
                new_status = bool(data['status'])
                state_changed = current_state.get('status') != new_status
                current_state['status'] = new_status
            #  previous versions of the master only sent rising edges
            else:
                new_status = True
                state_changed = True
                current_state['status'] = None
            if state_changed:
                current_state['last_status_change'] = now
                self._report_change(input_id, new_status)
            # store in memory
            self._inputs_status[input_id] = current_state

    def get_inputs(self):
        # type: () -> List[Dict[str,Any]]
        """ Get the inputs status. """
        inputs = []
        for input_nr, current_state in self._inputs_status.iteritems():
            inputs.append(current_state)
        return inputs

    def get_input(self, input_nr):
        """ Get a specific input status. """
        return self._inputs_status[input_nr]

    def full_update(self, inputs):
        """ Update the status of the inputs using a list of Inputs. """
        obsolete_ids = self._inputs_status.keys()
        for input in inputs:
            input_id = input['input']
            if input_id in obsolete_ids:
                obsolete_ids.remove(input_id)
            self.set_input(input)
        for input_id in obsolete_ids:
            del self._inputs_status[input_id]

    def _report_change(self, input_id, status):
        if self._on_input_change is not None:
            self._on_input_change(input_id, status)
