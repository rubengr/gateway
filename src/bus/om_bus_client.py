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
IPC Bus messaging client
"""

import logging
import time
import ujson as json
from multiprocessing.connection import Client
from threading import Thread, Lock
from signal import signal, SIGTERM
from bus.om_bus_events import OMBusEvents

logger = logging.getLogger('openmotics')


class MessageClient(object):

    def __init__(self, name, ip='localhost', port=10000, authkey='openmotics'):
        self.address = (ip, port)  # family is deduced to be 'AF_INET'
        self.authkey = authkey
        self.callbacks = []
        self.client = None
        self._get_state = None
        self.client_name = name
        self.latest_state_received = {}
        self._connected = False
        self._get_state_lock = Lock()
        self._stop = False
        self._start()

    def _send_state(self, source):
        if self._get_state is not None:
            msg = self._get_state()
            self._send(msg, msg_type='state', destination=source)

    def _process_message(self, payload):
        msg = json.loads(payload)
        data = msg['data']
        source = msg['source']
        if msg['type'] == 'request_state':
            self._send_state(source)
        if msg['type'] == 'state':
            self.latest_state_received[source] = data
        if msg['type'] == 'event':
            self._process_event(data)

    def _process_event(self, data):
        try:
            event_type = data['event_type']
            payload = data['payload']
            for callback in self.callbacks:
                try:
                    callback(event_type, payload)
                except Exception:
                    logger.exception('Error executing callback')
        except KeyError:
            logger.exception('error processing event')

    def _message_receiver(self):
        self._connect()
        self._stop = False
        while not self._stop:
            try:
                msg = self.client.recv_bytes()
                self._process_message(msg)
            except EOFError:
                logger.error('Client connection closed unexpectedly')
                self.client.close()
                self._connected = False
                self._connect()
            except Exception as e:
                logger.exception('Unexpected error occured in message receiver'.format(e))
                self.client.close()
                self._connected = False
                time.sleep(5)
                self._connect()

    def _send(self, data, msg_type='event', destination=None):
        payload = {'type': msg_type, 'source': self.client_name, 'destination': destination, 'data': data}
        msg = json.dumps(payload)
        if self.client is not None and self.client.closed is False and self._connected:
            self.client.send_bytes(msg)
        else:
            logger.error('Unable to send payload. Client still connected?')

    def _connect(self):
        while not self._connected:
            try:
                self.client = Client(self.address, authkey=self.authkey)
                self._connected = True
                self.send_event(OMBusEvents.CLIENT_DISCOVERY, None)
            except IOError as io_error:
                logger.error('Could not connect to message server: {}'.format(io_error))
                time.sleep(1)
            except Exception as e:
                logger.exception('Unknown error connecting to message server: {}'.format(e))
                time.sleep(1)

    def _start(self):
        def stop(signum, frame):
            """ This function is called on SIGTERM. """
            _ = signum, frame
            self._stop = True
        signal(SIGTERM, stop)

        receiver = Thread(target=self._message_receiver)
        receiver.daemon = True
        receiver.start()

    def get_state(self, destination, default=None, timeout=5):
        with self._get_state_lock:
            self._send(None, msg_type='request_state', destination=destination)
            t_end = time.time() + timeout
            while time.time() < t_end:
                latest_state = self.latest_state_received.pop(destination, None)
                if latest_state is not None:
                    return latest_state
                else:
                    time.sleep(0.2)
            return default

    def send_event(self, event_type, payload):
        data = {'event_type': event_type, 'payload': payload}
        self._send(data, msg_type='event')

    def set_state_handler(self, state_handler):
        self._get_state = state_handler

    def add_event_handler(self, callback):
        self.callbacks.append(callback)
