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
Tests for events.
"""
import unittest
import xmlrunner
from mock import Mock
from cloud.client import Client
from cloud.event_sender import EventSender


class EventsTest(unittest.TestCase):

    def test_events_sent_to_cloud(self):
        cloud = Client('test.example.com')
        cloud.send_event = Mock()
        event_sender = EventSender(cloud)  # Don't start, trigger manually
        self.assertEqual(event_sender._queue, 0)
        self.assertFalse(event_sender._send_events())
        event_sender.enqueue_event(Mock())
        self.assertEqual(event_sender._queue, 1)
        self.assertTrue(event_sender._send_events())
        cloud.send_event.assert_called_once()


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
