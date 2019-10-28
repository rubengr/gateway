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
Sends events to the cloud
"""
import logging
import time
import persistqueue
from collections import deque
from threading import Thread

from persistqueue import Empty
from wiring import inject, provides, scope, SingletonScope

import constants
from cloud.cloud_api_client import APIException
from gateway.observer import Event

logger = logging.getLogger('openmotics')


class EventSender(object):

    EVENT_EXPIRY = 5 * 24 * 3600  # 5 days


    @provides('event_manager')
    @scope(SingletonScope)
    @inject(cloud_client='cloud_api_client', gateway_api='gateway_api')
    def __init__(self, cloud_client, gateway_api):
        """
        :param cloud_client: The cloud API object
        :type cloud_client: cloud.client.Client
        """
        self._queue = deque()
        self._alarm_queue = deque()
        self._retry_queue = deque()
        self._stopped = True
        self._cloud_client = cloud_client
        self._gateway_api = gateway_api

        self._events_queue = deque()
        self._events_thread = Thread(target=self._send_events_loop, name='In-memory Event Sender')
        self._events_thread.setDaemon(True)

        self._persistent_queue = persistqueue.SQLiteAckQueue(constants.get_events_database_file())
        self._retry_events_thread = Thread(target=self._retry_events_loop, name='Persistent Event Sender')
        self._retry_events_thread.setDaemon(True)

    def start(self):
        self._stopped = False
        self._events_thread.start()
        self._retry_events_thread.start()

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
        elif event.type == Event.Types.INPUT_TRIGGER:
            id = event.data['id']
            config = self._gateway_api.get_input_configuration(id)
            config_code = config.get('event_enabled')
            return not (config_code == 255 or config_code == 0)
        else:
            return False

    def _needs_redelivery(self, event):
        config_code = 0
        if event.type == Event.Types.INPUT_TRIGGER:
            id = event.data['id']
            config = self._gateway_api.get_input_configuration(id)
            config_code = config.get('event_redelivery')
        if event.type == Event.Types.OUTPUT_CHANGE:
            id = event.data['id']
            config = self._gateway_api.get_output_configuration(id)
            config_code = config.get('event_redelivery')
        return not (config_code == 0 or config_code == 255)

    def _send_events_loop(self):
        while not self._stopped:
            try:
                if not self._send_events():
                    time.sleep(0.25)
            except APIException as ex:
                logger.error('Error sending events to the cloud: {}'.format(str(ex)))
                time.sleep(1)
            except Exception:
                logger.exception('Unexpected error when sending events')
                time.sleep(1)

    def _send_events(self):
        events = []
        while len(events) < 25:
            try:
                events.append(self._queue.pop())
            except IndexError:
                break
        if len(events) > 0:
            try:
                self._cloud_client.send_events(events)
                return True
            except APIException as ex:
                logger.error('Error sending events to the cloud: {}'.format(str(ex)))
                self._put_on_persistent_queue(events)
        return False

    def _put_on_persistent_queue(self, events):
        for event in events:
            if self._needs_redelivery(event):
                self._persistent_queue.put(events)
        # discard events from queue if too large
        if self._persistent_queue.size > 100:
            n = self._persistent_queue.size - 100
            for i in xrange(n):
                item = self._persistent_queue.get(block=False)
                self._persistent_queue.ack_failed(item)

    def _retry_events_loop(self):
        while not self._stopped:
            now = time.time()
            while True:
                try:
                    event = self._persistent_queue.get(block=False)
                except Empty:
                    break
                try:
                    if event.data.get('timestamp', 0) < now - self.EVENT_EXPIRY:
                        # discard alerts older than event expiry time delta
                        self._persistent_queue.ack_failed(event)
                    else:
                        # retry sending events
                        self._cloud_client.send_event(event)
                        self._persistent_queue.ack(event)
                        time.sleep(1)  # avoid API throttling by server
                except APIException as ex:
                    self._persistent_queue.nack(event)
                except Exception:
                    logger.exception('Unexpected error in retry sending persisted events')
                    self._persistent_queue.ack_failed(event)
            time.sleep(30)
