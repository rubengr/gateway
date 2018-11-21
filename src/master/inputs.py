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


class InputStatus(object):
    """ Contains the last Y inputs pressed the last Y seconds. """

    def __init__(self, num_inputs=5, seconds=10):
        """
        Create an InputStatus, specifying the number of inputs to track and
        the number of seconds to keep the data.
        """
        self._num_inputs = num_inputs
        self._seconds = seconds
        self._inputs = []

    def _clean(self):
        """ Remove the old input data. """
        threshold = time.time() - self._seconds
        self._inputs = [i for i in self._inputs if i[0] > threshold]

    def add_data(self, data):
        """ Add input data. """
        self._clean()
        while len(self._inputs) >= self._num_inputs:
            self._inputs.pop(0)
        self._inputs.append((time.time(), data))

    def get_status(self):
        """ Get the last inputs. """
        self._clean()
        return [i[1] for i in self._inputs]
