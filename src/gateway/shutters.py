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
This module contains logic to handle shutters with their state/position
"""
import logging
import time
from threading import Lock
from master.master_api import BA_SHUTTER_DOWN, BA_SHUTTER_STOP, BA_SHUTTER_UP

LOGGER = logging.getLogger('openmotics')


class ShutterController(object):
    """
    Controls everything related to shutters.

    Important assumptions:
    * A shutter can go UP and go DOWN
    * A shutter that is UP is considered open and has a position of 0
    * A shutter that is DOWN is considered closed and has a position of `steps`

    # TODO: The states OPEN and CLOSED make more sense but is a reasonable heavy change at this moment. To be updated if/when a new Gateway API is introduced
    """

    class Direction(object):
        UP = 'UP'
        DOWN = 'DOWN'
        STOP = 'STOP'

    class State(object):
        GOING_UP = 'going_up'
        GOING_DOWN = 'going_down'
        STOPPED = 'stopped'
        UP = 'up'
        DOWN = 'down'

    DIRECTION_STATE_MAP = {Direction.UP: State.GOING_UP,
                           Direction.DOWN: State.GOING_DOWN,
                           Direction.STOP: State.STOPPED}
    DIRECTION_END_STATE_MAP = {Direction.UP: State.UP,
                               Direction.DOWN: State.DOWN,
                               Direction.STOP: State.STOPPED}
    STATE_DIRECTION_MAP = {State.GOING_UP: Direction.UP,
                           State.GOING_DOWN: Direction.DOWN,
                           State.STOPPED: Direction.STOP}

    def __init__(self, master_communicator, verbose=False):
        """
        Initializes a ShutterController
        :param master_communicator: Master communicator
        :type master_communicator: master.master_communicator.MasterCommunicator
        """
        self._master_communicator = master_communicator

        self._shutters = {}
        self._actual_positions = {}
        self._desired_positions = {}
        self._directions = {}
        self._states = {}

        self._verbose = verbose
        self._config_lock = Lock()
        self._on_shutter_changed = None

    def set_shutter_changed_callback(self, callback):
        self._on_shutter_changed = callback

    def _log(self, message):
        if self._verbose:
            LOGGER.info('ShutterController: {0}'.format(message))

    # Update internal shutter configuration cache

    def update_config(self, config):
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
                self._states[shutter_id] = [0, ShutterController.State.STOPPED]
                self._actual_positions[shutter_id] = None
                self._desired_positions[shutter_id] = None
                self._directions[shutter_id] = ShutterController.Direction.STOP

        for shutter_id in self._shutters.keys():
            if shutter_id not in shutter_ids:
                del self._shutters[shutter_id]
                del self._states[shutter_id]
                del self._actual_positions[shutter_id]
                del self._desired_positions[shutter_id]
                del self._directions[shutter_id]

    # Allow shutter positions to be reported

    def report_shutter_position(self, shutter_id, position, direction=None):
        self._log('Shutter {0} reports position {1}'.format(shutter_id, position))
        # Fetch and validate information
        shutter = self._get_shutter(shutter_id)
        steps = ShutterController._get_steps(shutter)
        ShutterController._validate_position(shutter_id, position, steps)

        # Store new position
        self._actual_positions[shutter_id] = position

        # Update the direction and report if changed
        expected_direction = self._directions[shutter_id]
        if direction is not None and expected_direction != direction:
            # We received a more accurate direction
            self._log('Shutter {0} report direction change to {1}'.format(shutter_id, direction))
            self._report_shutter_state(shutter_id, ShutterController.DIRECTION_STATE_MAP[direction])

        direction = self._directions[shutter_id]
        desired_position = self._desired_positions[shutter_id]
        if desired_position is None:
            return
        if ShutterController._is_position_reached(direction, desired_position, position, stopped=True):
            self._log('Shutter {0} reported position is desired position: Stopping'.format(shutter_id))
            self.shutter_stop(shutter_id)

    # Control shutters

    def shutter_up(self, shutter_id, desired_position=None):
        return self._shutter_goto_direction(shutter_id, ShutterController.Direction.UP, desired_position)

    def shutter_down(self, shutter_id, desired_position=None):
        return self._shutter_goto_direction(shutter_id, ShutterController.Direction.DOWN, desired_position)

    def shutter_goto(self, shutter_id, desired_position):
        # Fetch and validate data
        shutter = self._get_shutter(shutter_id)
        steps = ShutterController._get_steps(shutter)
        ShutterController._validate_position(shutter_id, desired_position, steps)

        actual_position = self._actual_positions[shutter_id]
        if actual_position is None:
            raise RuntimeError('Shutter {0} has unknown actual position'.format(shutter_id))

        direction = self._get_direction(actual_position, desired_position)
        if direction == ShutterController.Direction.STOP:
            return self.shutter_stop(shutter_id)

        self._log('Shutter {0} setting desired position to {1}'.format(shutter_id, desired_position))

        self._desired_positions[shutter_id] = desired_position
        self._directions[shutter_id] = direction
        self._execute_shutter(shutter_id, direction)

    def shutter_stop(self, shutter_id):
        # Validate data
        self._get_shutter(shutter_id)

        self._log('Shutter {0} stopped. Removing desired position'.format(shutter_id))

        self._desired_positions[shutter_id] = None
        self._directions[shutter_id] = ShutterController.Direction.STOP
        self._execute_shutter(shutter_id, ShutterController.Direction.STOP)

    def _shutter_goto_direction(self, shutter_id, direction, desired_position=None):
        # Fetch and validate data
        shutter = self._get_shutter(shutter_id)
        steps = ShutterController._get_steps(shutter)

        if desired_position is not None:
            ShutterController._validate_position(shutter_id, desired_position, steps)
        else:
            desired_position = ShutterController._get_limit(direction, steps)

        self._log('Shutter {0} setting desired position to {1}'.format(shutter_id, desired_position))

        self._desired_positions[shutter_id] = desired_position
        self._directions[shutter_id] = direction
        self._execute_shutter(shutter_id, direction)

    def _execute_shutter(self, shutter_id, direction):
        if direction == ShutterController.Direction.UP:
            self._master_communicator.do_basic_action(BA_SHUTTER_UP, shutter_id)
        elif direction == ShutterController.Direction.DOWN:
            self._master_communicator.do_basic_action(BA_SHUTTER_DOWN, shutter_id)
        elif direction == ShutterController.Direction.STOP:
            self._master_communicator.do_basic_action(BA_SHUTTER_STOP, shutter_id)

    # Internal checks and validators

    def _get_shutter(self, shutter_id):
        shutter = self._shutters.get(shutter_id)
        if shutter is None:
            raise RuntimeError('Shutter {0} is not available'.format(shutter_id))
        return shutter

    @staticmethod
    def _is_position_reached(direction, desired_position, actual_position, stopped=True):
        if desired_position == actual_position:
            return True  # Obviously reached
        if direction == ShutterController.Direction.STOP:
            return stopped  # Can't be decided, so return user value
        # An overshoot is considered as "position reached"
        if direction == ShutterController.Direction.UP:
            return actual_position < desired_position
        return actual_position > desired_position

    @staticmethod
    def _get_limit(direction, steps):
        if steps is None:
            return None
        if direction == ShutterController.Direction.UP:
            return 0
        return steps - 1

    @staticmethod
    def _get_direction(actual_position, desired_position):
        if actual_position == desired_position:
            return ShutterController.Direction.STOP
        if actual_position < desired_position:
            return ShutterController.Direction.UP
        return ShutterController.Direction.DOWN

    @staticmethod
    def _get_steps(shutter):
        steps = shutter['steps']
        if steps in [0, 1, 65535]:
            # These step values are considered "not configured" and thus "no position support"
            return None
        return steps

    @staticmethod
    def _validate_position(shutter_id, position, steps):
        if steps is None:
            raise RuntimeError('Shutter {0} does not support positioning'.format(shutter_id))
        if not (0 <= position < steps):
            raise RuntimeError('Shutter {0} has a position limit of 0 <= position <= {1}'.format(shutter_id, steps - 1))

    # Reporting

    def update_from_master_state(self, data):
        """
        Called with Master event information.
        """
        with self._config_lock:
            module_id = data['module_nr']
            new_state = self._interprete_output_states(module_id, data['status'])
            if new_state is None:
                return  # Failsafe for master event handler
            for i in xrange(4):
                shutter_id = module_id * 4 + i
                self._report_shutter_state(shutter_id, new_state[i])

    def _report_shutter_state(self, shutter_id, new_state):
        shutter = self._get_shutter(shutter_id)
        steps = ShutterController._get_steps(shutter)

        self._directions[shutter_id] = ShutterController.STATE_DIRECTION_MAP[new_state]
        self._log('Shutter {0} reports state {1}, which is direction {2}'.format(shutter_id, new_state, self._directions[shutter_id]))

        current_state_timestamp, current_state = self._states[shutter_id]
        if new_state == current_state or (new_state == ShutterController.State.STOPPED and current_state in [ShutterController.State.DOWN, ShutterController.State.UP]):
            self._log('Shutter {0} new state {1} ignored since it equals {2}'.format(shutter_id, new_state, current_state))
            return  # State didn't change, nothing to do

        if new_state != ShutterController.State.STOPPED:
            # Shutter started moving
            self._states[shutter_id] = [time.time(), new_state]
            self._log('Shutter {0} started moving'.format(shutter_id))
        else:
            direction = ShutterController.STATE_DIRECTION_MAP[current_state]
            if steps is None:
                # Time based state calculation
                threshold = 0.95 * shutter['timer_{0}'.format(direction.lower())]  # Allow 5% difference
                if time.time() >= current_state_timestamp + threshold:  # The shutter was going up/down for the whole `timer`. So it's now up/down
                    self._log('Shutter {0} going {1} passed time threshold. New state {2}'.format(shutter_id, direction, ShutterController.DIRECTION_END_STATE_MAP[direction]))
                    new_state = ShutterController.DIRECTION_END_STATE_MAP[direction]
                else:
                    self._log('Shutter {0} going {1} did not pass time threshold. New state {2}'.format(shutter_id, direction, ShutterController.State.STOPPED))
                    new_state = ShutterController.State.STOPPED
            else:
                # Supports position, so state will be calculated on position
                limit_position = ShutterController._get_limit(direction, steps)
                if ShutterController._is_position_reached(direction, limit_position, self._actual_positions[shutter_id]):
                    self._log('Shutter {0} going {1} reached limit. New state {2}'.format(shutter_id, direction, ShutterController.DIRECTION_END_STATE_MAP[direction]))
                    new_state = ShutterController.DIRECTION_END_STATE_MAP[direction]
                else:
                    self._log('Shutter {0} going {1} did not reach limit. New state {2}'.format(shutter_id, direction, ShutterController.State.STOPPED))
                    new_state = ShutterController.State.STOPPED

            self._states[shutter_id] = [time.time(), new_state]

        self._report_change(shutter_id, shutter, self._states[shutter_id])

    def _interprete_output_states(self, module_id, output_states):
        states = []
        for i in xrange(4):
            shutter_id = module_id * 4 + i
            if shutter_id not in self._shutters:
                return  # Failsafe for master event handler

            # first_up = 0 -> output 0 = up, output 1 = down
            # first_up = 1 -> output 0 = down, output 1 = up
            first_up = 0 if self._shutters[shutter_id]['up_down_config'] == 0 else 1

            up = (output_states >> (i * 2 + (1 - first_up))) & 0x1
            down = (output_states >> (i * 2 + first_up)) & 0x1

            if up == 1 and down == 0:
                states.append(ShutterController.State.GOING_UP)
            elif down == 1 and up == 0:
                states.append(ShutterController.State.GOING_DOWN)
            else:  # Both are off or - unlikely - both are on
                states.append(ShutterController.State.STOPPED)

        return states

    def get_states(self):
        all_states = []
        for i in sorted(self._states.keys()):
            all_states.append(self._states[i][1])
        return {'status': all_states,
                'detail': {shutter_id: {'state': self._states[shutter_id][1],
                                        'actual_position': self._actual_positions[shutter_id],
                                        'desired_position': self._desired_positions[shutter_id]}
                           for shutter_id in self._shutters}}

    def _report_change(self, shutter_id, shutter_data, shutter_state):
        if self._on_shutter_changed is not None:
            self._on_shutter_changed(shutter_id, shutter_data, shutter_state[1].upper())
