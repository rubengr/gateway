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

    def __init__(self, master_communicator):
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

        self._merge_lock = Lock()
        self._on_shutter_changed = None

    def set_shutter_changed_callback(self, callback):
        self._on_shutter_changed = callback

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
        # Fetch and validate information
        shutter = self._get_shutter(shutter_id)
        position_limits = ShutterController._get_position_limits(shutter)
        ShutterController._validate_position_limits(shutter_id, position, position_limits)

        # Store new position
        self._actual_positions[shutter_id] = position

        # Check for desired position to stop the shutter if appropriate
        expected_direction = self._directions[shutter_id]
        if direction is not None and expected_direction != direction:
            # We received a more accurate direction
            self._report_shutter_state(shutter_id, ShutterController.DIRECTION_STATE_MAP[direction])
        expected_direction = self._directions[shutter_id]
        desired_position = self._desired_positions[shutter_id]
        if desired_position is None:
            return
        if ShutterController._is_position_reached(shutter, expected_direction, desired_position, position, stopped=True):
            self.shutter_stop(shutter_id)

    # Control shutters

    def shutter_up(self, shutter_id, desired_position=None):
        return self._shutter_goto_direction(shutter_id, ShutterController.Direction.UP, desired_position)

    def shutter_down(self, shutter_id, desired_position=None):
        return self._shutter_goto_direction(shutter_id, ShutterController.Direction.DOWN, desired_position)

    def shutter_goto(self, shutter_id, desired_position):
        # Fetch and validate data
        shutter = self._get_shutter(shutter_id)
        position_limits = ShutterController._get_position_limits(shutter)
        ShutterController._validate_position_limits(shutter_id, desired_position, position_limits)

        actual_position = self._actual_positions[shutter_id]
        if actual_position is None:
            raise RuntimeError('Shutter {0} has unknown actual position'.format(shutter_id))

        direction = self._get_direction(actual_position, desired_position, position_limits)

        self._desired_positions[shutter_id] = desired_position
        self._directions[shutter_id] = direction
        self._execute_shutter(shutter_id, direction)

    def shutter_stop(self, shutter_id):
        # Validate data
        self._get_shutter(shutter_id)

        self._desired_positions[shutter_id] = None
        self._directions[shutter_id] = ShutterController.Direction.STOP
        self._execute_shutter(shutter_id, ShutterController.Direction.STOP)

    def _shutter_goto_direction(self, shutter_id, direction, desired_position=None):
        # Fetch and validate data
        shutter = self._get_shutter(shutter_id)
        position_limits = ShutterController._get_position_limits(shutter)

        if desired_position is not None:
            ShutterController._validate_position_limits(shutter_id, desired_position, position_limits)
        else:
            desired_position = ShutterController._get_limit(direction, position_limits)

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
    def _is_position_reached(shutter, direction, desired_position, actual_position, stopped=True):
        up = shutter['up_position']
        down = shutter['down_position']
        if desired_position == actual_position:
            return True  # Obviously reached
        if direction == ShutterController.Direction.STOP:
            return stopped  # Can't be decided, so return user value
        if direction == ShutterController.Direction.UP:
            if up > down:
                return actual_position >= desired_position
            return actual_position <= desired_position
        if up > down:
            return actual_position <= desired_position
        return actual_position >= desired_position

    @staticmethod
    def _get_limit(direction, position_limits):
        if position_limits is None:
            return None
        if direction == ShutterController.Direction.UP:
            return position_limits['up']
        return position_limits['down']

    @staticmethod
    def _get_direction(actual_position, desired_position, position_limits):
        up = position_limits['up']
        down = position_limits['down']
        if up > down:
            if desired_position > actual_position:
                return ShutterController.Direction.UP
            return ShutterController.Direction.DOWN
        if desired_position > actual_position:
            return ShutterController.Direction.DOWN
        return ShutterController.Direction.UP

    @staticmethod
    def _get_position_limits(shutter):
        limits = {'up': shutter['up_position'],
                  'down': shutter['down_position']}
        if limits['up'] == limits['down']:
            # If they are equal it means that they are both set to the standard value 65535, or they are incorrectly configured
            return None
        return limits

    @staticmethod
    def _validate_position_limits(shutter_id, position, position_limits):
        if position_limits is None:
            raise RuntimeError('Shutter {0} does not support positioning'.format(shutter_id))
        if not (min(position_limits['up'], position_limits['down']) <= position <= max(position_limits['up'], position_limits['down'])):
            raise RuntimeError('Shutter {0} has a position limit between {1} and {2}'.format(shutter_id, position_limits['up'], position_limits['down']))

    # Reporting

    def update_from_master_state(self, data):
        """
        Called with Master event information.
        """
        with self._merge_lock:
            module_id = data['module_nr']
            new_state = self._interprete_output_states(module_id, data['status'])
            if new_state is None:
                return  # Failsafe for master event handler
            for i in xrange(4):
                shutter_id = module_id * 4 + i
                self._report_shutter_state(shutter_id, new_state[i])

    def _report_shutter_state(self, shutter_id, state):
        shutter = self._get_shutter(shutter_id)
        position_limits = ShutterController._get_position_limits(shutter)

        expected_direction = ShutterController.STATE_DIRECTION_MAP.get(state)
        if expected_direction is not None:
            direction = self._directions[shutter_id]
            if direction != expected_direction:
                self._directions[shutter_id] = expected_direction

        current_state_timestamp, current_state = self._states[shutter_id]
        if state == current_state or (state == ShutterController.State.STOPPED and current_state in [ShutterController.State.DOWN, ShutterController.State.UP]):
            return  # State didn't change, nothing to do

        if state != ShutterController.State.STOPPED:
            # Shutter started moving
            self._states[shutter_id] = [time.time(), state]
        else:
            direction = ShutterController.STATE_DIRECTION_MAP[current_state]
            if position_limits is None:
                # Time based state calculation
                threshold = 0.95 * shutter['timer_{0}'.format(direction.lower())]  # Allow 5% difference
                if time.time() >= current_state_timestamp + threshold:  # The shutter was going up/down for the whole `timer`. So it's now up/down
                    new_state = ShutterController.DIRECTION_END_STATE_MAP[direction]
                else:
                    new_state = ShutterController.State.STOPPED
            else:
                # Supports position, so state will be calculated on position
                if ShutterController._is_position_reached(shutter, direction, self._desired_positions[shutter_id], self._actual_positions[shutter_id]):
                    new_state = ShutterController.DIRECTION_END_STATE_MAP[direction]
                else:
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

            if up == 1:
                states.append(ShutterController.State.GOING_UP)
            elif down == 1:
                states.append(ShutterController.State.GOING_DOWN)
            else:
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
