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
""""
Tests for InputStatus.
"""

import time
import unittest

import mock
import xmlrunner
from master.inputs import InputStatus


class InputStatusTest(unittest.TestCase):
    """ Tests for InputStatus. """

    def test_add(self):
        """ Test adding data to the InputStatus. """
        inps = InputStatus()
        inps.set_input({'input': 1, 'status': 1})
        states = [{k: v for k, v in x.items() if k in ('id', 'status')}
                  for x in inps.get_inputs()]
        self.assertEqual(len(states), 1)
        self.assertIn({'id': 1, 'status': True}, states)

        inps.set_input({'input': 2, 'status': 1})
        states = [{k: v for k, v in x.items() if k in ('id', 'status')}
                  for x in inps.get_inputs()]
        self.assertEqual(len(states), 2)
        self.assertIn({'id': 2, 'status': True}, states)
        self.assertIn({'id': 1, 'status': True}, states)

        inps.set_input({'input': 3, 'status': 0})
        states = [{k: v for k, v in x.items() if k in ('id', 'status')}
                  for x in inps.get_inputs()]
        self.assertEqual(len(states), 3)
        self.assertIn({'id': 3, 'status': False}, states)
        self.assertIn({'id': 1, 'status': True}, states)

    def test_get_recent(self):
        """ Test adding data to the InputStatus. """
        inps = InputStatus()
        with mock.patch.object(time, 'time', return_value=10):
            inps.set_input({'input': 1, 'status': 1})
            self.assertEqual([1], inps.get_recent())

        with mock.patch.object(time, 'time', return_value=30):
            for i in xrange(2, 10):
                inps.set_input({'input': i, 'status': 1})
            self.assertEqual(5, len(inps.get_recent()))

        with mock.patch.object(time, 'time', return_value=60):
            self.assertEqual(0, len(inps.get_recent()))

        with mock.patch.object(time, 'time', return_value=35):
            inps.set_input({'input': 1, 'status': 0})
            inps.set_input({'input': 2, 'status': 1})
            self.assertIn(1, inps.get_recent())
            self.assertNotIn(2, inps.get_recent())

    def test_on_changed(self):
        changed = []

        def on_input_change(input_id, status):
            changed.append(input_id)

        inps = InputStatus(on_input_change=on_input_change)
        inps.set_input({'input': 6, 'status': 0})
        inps.set_input({'input': 6, 'status': 1})
        inps.set_input({'input': 6, 'status': 1})
        inps.set_input({'input': 6, 'status': 0})
        inps.set_input({'input': 6, 'status': 0})
        inps.set_input({'input': 6, 'status': 1})
        self.assertEquals(len(changed), 4)

    def test_set_input_without_status(self):
        changed = []

        def on_input_change(input_id, status):
            changed.append(input_id)

        inps = InputStatus(on_input_change=on_input_change)
        inps.set_input({'input': 6, 'status': 1})
        current_status = inps.get_input(6)
        self.assertEquals(current_status['status'], True)
        inps.set_input({'input': 6})
        current_status = inps.get_input(6)
        self.assertEquals(current_status['status'], None)
        self.assertEquals(len(changed), 2)

    def test_timeout(self):
        """ Test timeout of InputStatus data. """
        inps = InputStatus(5, 1)
        inps.set_input({'input': 1, 'status': 1})
        self.assertEquals([1], inps.get_recent())

        time.sleep(0.8)

        inps.set_input({'input': 2, 'status': 1})
        self.assertEquals([1, 2], inps.get_recent())

        time.sleep(0.3)

        self.assertEquals([2], inps.get_recent())


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
