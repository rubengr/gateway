# Copyright (C) 2019 OpenMotics BV
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
Sends events to the cloud
"""
import logging
import time
from collections import deque
from threading import Thread
from ioc import Injectable, Singleton, INJECTED, Inject
from cloud.cloud_api_client import APIException
from gateway.observer import Event

logger = logging.getLogger('openmotics')


@Injectable.named('event_sender')
@Singleton
class EventSender(object):

    @Inject
    def __init__(self, cloud_api_client=INJECTED, gateway_api=INJECTED):
        """
        :param cloud_api_client: The cloud API object
        :type cloud_api_client: cloud.cloud_api_client.CloudAPIClient
        """
        self._queue = deque()
        self._stopped = True
        self._cloud_client = cloud_api_client
        self._gateway_api = gateway_api

        self._events_queue = deque()
        self._events_thread = Thread(target=self._send_events_loop, name='Event Sender')
        self._events_thread.setDaemon(True)

    def start(self):
        self._stopped = False
        self._events_thread.start()

    def stop(self):
        self._stopped = True

    def enqueue_event(self, event):
        if self._is_enabled(event):
            event.data['timestamp'] = time.time()
            self._queue.appendleft(event)

    def _is_enabled(self, event):
        if event.type in [Event.Types.OUTPUT_CHANGE,
                          Event.Types.SHUTTER_CHANGE,
                          Event.Types.THERMOSTAT_CHANGE,
                          Event.Types.THERMOSTAT_GROUP_CHANGE]:
            return True
        elif event.type == Event.Types.INPUT_CHANGE:
            input_id = event.data['id']
            config = self._gateway_api.get_input_configuration(input_id)
            return config['event_enabled']
        else:
            return False

    def _send_events_loop(self):
        while not self._stopped:
            try:
                if not self._batch_send_events():
                    time.sleep(0.20)
                time.sleep(0.05)
            except APIException as ex:
                logger.error('Error sending events to the cloud: {}'.format(str(ex)))
                time.sleep(1)
            except Exception:
                logger.exception('Unexpected error when sending events')
                time.sleep(1)

    def _batch_send_events(self):
        events = []
        while len(events) < 25:
            try:
                events.append(self._queue.pop())
            except IndexError:
                break
        if len(events) > 0:
            self._cloud_client.send_events(events)
            return True
        return False
