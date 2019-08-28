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
from collections import deque
from threading import Thread
from cloud.client import APIException
from gateway.observer import Event

logger = logging.getLogger('openmotics')


class EventSender(object):

    def __init__(self, cloud_client):
        """
        :param cloud_client: The cloud API object
        :type cloud_client: cloud.client.Client
        """
        self._queue = deque()
        self._stopped = True
        self._cloud_client = cloud_client

        self._thread = Thread(target=self._send_events, name='Event sender')
        self._thread.setDaemon(True)

    def start(self):
        self._stopped = False
        self._thread.start()

    def stop(self):
        self._stopped = True

    def enqueue_event(self, event):
        if event.type in [Event.Types.OUTPUT_CHANGE,
                          Event.Types.SHUTTER_CHANGE,
                          Event.Types.THERMOSTAT_CHANGE,
                          Event.Types.THERMOSTAT_GROUP_CHANGE]:
            self._queue.appendleft(event)

    def _send_events(self):
        while not self._stopped:
            try:
                events = []
                try:
                    events.append(self._queue.pop())
                except IndexError:
                    pass
                if len(events) > 0:
                    self._cloud_client.send_events(events)
                else:
                    time.sleep(0.25)
            except APIException as ex:
                logger.error(ex)
                time.sleep(1)
            except Exception:
                logger.exception('Unexpected error when sending events')
                time.sleep(1)
