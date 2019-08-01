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

from master.master_api import BA_SHUTTER_DOWN, BA_SHUTTER_STOP, BA_SHUTTER_UP


class ShutterController(object):
    class Direction(object):
        UP = 'UP'
        DOWN = 'DOWN'
        STOP = 'STOP'  # Not a real direction

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

    def reload_config(self, shutter_configs):
        current_ids = self._shutters.keys()
        for config in shutter_configs:
            shutter_id = config['id']
            self._shutters[shutter_id] = config
            if shutter_id in current_ids:
                current_ids.remove(shutter_id)
        for shutter_id in current_ids:
            self._shutters.pop(shutter_id, None)

    def report_shutter_position(self, shutter_id, position):
        # Fetch and validate information
        shutter = self._get_shutter(shutter_id)
        position_limits = ShutterController._get_position_limits(shutter)
        ShutterController._validate_position_limits(shutter_id, position, position_limits)

        # Store new position
        self._actual_positions[shutter_id] = position

        # Check for desired position to stop the shutter if appropriate
        desired_position = self._desired_positions.get(shutter_id)
        if desired_position is not None:
            direction = self._directions[shutter_id]
            if ShutterController._is_position_reached(shutter, direction, desired_position, position, stopped=True):
                self._execute_shutter(shutter_id, ShutterController.Direction.STOP)
                self._desired_positions[shutter_id] = None  # Remove desired position

    def shutter_up(self, shutter_id, position=None):
        # Fetch and validate data
        shutter = self._get_shutter(shutter_id)
        position_limits = self._get_position_limits(shutter)
        direction = ShutterController.Direction.UP

        if position is not None:
            ShutterController._validate_position_limits(shutter_id, position, position_limits)
        else:
            position = ShutterController._get_limit(direction, position_limits)

        self._desired_positions[shutter_id] = position
        self._directions[shutter_id] = direction
        self._execute_shutter(shutter_id, direction)

    def shutter_down(self, shutter_id, position=None):
        # Fetch and validate data
        shutter = self._get_shutter(shutter_id)
        position_limits = self._get_position_limits(shutter)
        direction = ShutterController.Direction.DOWN

        if position is not None:
            ShutterController._validate_position_limits(shutter_id, position, position_limits)
        else:
            position = ShutterController._get_limit(direction, position_limits)

        self._desired_positions[shutter_id] = position
        self._directions[shutter_id] = direction
        self._execute_shutter(shutter_id, direction)

    def shutter_goto(self, shutter_id, position):
        # Fetch and validate data
        shutter = self._get_shutter(shutter_id)
        position_limits = self._get_position_limits(shutter)
        ShutterController._validate_position_limits(shutter_id, position, position_limits)

        actual_position = self._actual_positions.get(shutter_id)
        if actual_position is None:
            raise RuntimeError('Shutter {0} has unknown actual position'.format(shutter_id))

        direction = self._get_direction(actual_position, position, position_limits)

        self._desired_positions[shutter_id] = position
        self._directions[shutter_id] = direction
        self._execute_shutter(shutter_id, direction)

    def shutter_stop(self, shutter_id):
        # Validate data
        self._get_shutter(shutter_id)

        self._desired_positions[shutter_id] = None
        self._directions[shutter_id] = ShutterController.Direction.STOP
        self._execute_shutter(shutter_id, ShutterController.Direction.STOP)

    def _execute_shutter(self, shutter_id, direction):
        if direction == ShutterController.Direction.UP:
            self._master_communicator.do_basic_action(BA_SHUTTER_UP, shutter_id)
        elif direction == ShutterController.Direction.DOWN:
            self._master_communicator.do_basic_action(BA_SHUTTER_DOWN, shutter_id)
        elif direction == ShutterController.Direction.STOP:
            self._master_communicator.do_basic_action(BA_SHUTTER_STOP, shutter_id)

    def _get_shutter(self, shutter_id):
        shutter = self._shutters.get(shutter_id)
        if shutter is None:
            raise RuntimeError('Shutter {0} is not available'.format(shutter_id))
        return shutter

    @staticmethod
    def _is_position_reached(shutter, direction, desired_position, actual_position, stopped=True):
        up = shutter['up_position']
        down = shutter['down_position']
        if direction == ShutterController.Direction.STOP:
            return stopped
        if direction == ShutterController.Direction.UP:
            if up > down:
                return actual_position >= desired_position
            return actual_position <= desired_position
        if up > down:
            return actual_position <= desired_position
        return actual_position >= desired_position

    @staticmethod
    def _get_limit(direction, position_limits):
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
