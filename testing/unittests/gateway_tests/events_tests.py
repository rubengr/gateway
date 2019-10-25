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
from cloud.cloud_api_client import CloudAPIClient
from gateway.observer import Event
from cloud.events import EventSender


class EventsTest(unittest.TestCase):

    def test_events_sent_to_cloud(self):
        container = {}

        def _send_events(events):
            container['events'] = events

        cloud = CloudAPIClient('test.example.com')
        cloud.send_events = _send_events
        event_sender = EventSender(cloud)  # Don't start, trigger manually
        self.assertEqual(len(event_sender._queue), 0)
        self.assertFalse(event_sender._send_events())
        event_sender.enqueue_event(Event(Event.Types.OUTPUT_CHANGE, None))
        event_sender.enqueue_event(Event(Event.Types.THERMOSTAT_CHANGE, None))
        event_sender.enqueue_event(Event(Event.Types.INPUT_TRIGGER, None))
        self.assertEqual(len(event_sender._queue), 2)
        self.assertTrue(event_sender._send_events())
        self.assertEqual(len(event_sender._queue), 0)
        self.assertEqual(len(container.get('events', [])), 2)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
