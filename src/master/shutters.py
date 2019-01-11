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
The shutters module contains classes to track the current state of the shutters on
the master.
"""

import time
from threading import Lock

import logging
LOGGER = logging.getLogger('openmotics')


class ShutterStatus(object):
    """ Tracks the current state of the shutters. """

    class State(object):
        GOING_UP = 'going_up'
        GOING_DOWN = 'going_down'
        STOPPED = 'stopped'
        UP = 'up'
        DOWN = 'down'

    def __init__(self):
        """ Default constructor. Call init to initialize the states. """
        self._shutters = {}
        self._merge_lock = Lock()
        self._states = {}

    def update_config(self, config):
        with self._merge_lock:
            shutter_ids = []
            for shutter_config in config:
                shutter_id = shutter_config['id']
                shutter_ids.append(shutter_id)
                difference = shutter_id not in self._shutters
                if difference is False:
                    for key in shutter_config:
                        if shutter_config[key] != self._shutters[shutter_id][key]:
                            difference = True
                            break
                if difference:
                    self._shutters[shutter_id] = shutter_config
                    self._states[shutter_id] = [0, ShutterStatus.State.STOPPED]
            for shutter_id in self._shutters:
                if shutter_id not in shutter_ids:
                    del self._shutters[shutter_id]
                    del self._states[shutter_id]

    def update_states(self, data):
        with self._merge_lock:
            now = time.time()
            module_id = data['module_nr']
            state = data['status']
            new_state = self._interprete_states(module_id, state)
            if new_state is None:
                return
            for i in xrange(4):
                shutter_id = module_id * 4 + i
                previous_state = self._states[shutter_id]
                if previous_state[1] == new_state[i]:
                    continue
                if new_state[i] == ShutterStatus.State.STOPPED:
                    if previous_state[1] == ShutterStatus.State.GOING_UP:
                        threshold = 0.95 * self._shutters[shutter_id]['timer_up']  # Allow 5% difference
                        if previous_state[0] + threshold <= now:
                            previous_state = [now, ShutterStatus.State.UP]
                        else:
                            previous_state = [now, ShutterStatus.State.STOPPED]
                    elif previous_state[1] == ShutterStatus.State.GOING_DOWN:
                        threshold = 0.95 * self._shutters[shutter_id]['timer_down']  # Allow 5% difference
                        if previous_state[0] + threshold <= now:
                            previous_state = [now, ShutterStatus.State.DOWN]
                        else:
                            previous_state = [now, ShutterStatus.State.STOPPED]
                    # Was already stopped, nothing to change
                else:
                    # The state changed, but it is not stopped. This means the shutter just started moving
                    previous_state = [now, new_state[i]]
                self._states[shutter_id] = previous_state

    def _interprete_states(self, module_id, state):
        states = []
        for i in xrange(4):
            shutter_id = module_id * 4 + i
            if shutter_id not in self._shutters:
                return

            # first_up = 0 -> output 0 = up, output 1 = down
            # first_up = 1 -> output 0 = down, output 1 = up
            first_up = 0 if self._shutters[shutter_id]['up_down_config'] == 0 else 1

            up = (state >> (i * 2 + (1 - first_up))) & 0x1
            down = (state >> (i * 2 + first_up)) & 0x1

            if up == 1:
                states.append(ShutterStatus.State.GOING_UP)
            elif down == 1:
                states.append(ShutterStatus.State.GOING_DOWN)
            else:
                states.append(ShutterStatus.State.STOPPED)

        return states

    def get_states(self):
        """ Return the list of shutters states. """
        all_states = []
        for i in sorted(self._states.keys()):
            all_states.append(self._states[i][1])
        return all_states
