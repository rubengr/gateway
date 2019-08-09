import random
from multiprocessing.connection import Client
from threading import Thread
import logging
import time

from om_bus_events import Events

try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger('openmotics')


class MessageClient(object):

    def __init__(self, name, ip='localhost', port=10000, authkey='openmotics'):
        self.address = (ip, port)  # family is deduced to be 'AF_INET'
        self.authkey = authkey
        self.callbacks = []
        self.client = None
        self._get_state = None
        self.client_name = name
        self.latest_state_received = None

        self._start()

    def _send_state(self):
        if self._get_state is not None:
            msg = self._get_state()
            self._send(msg, msg_type='state')

    def _process_message(self, payload):
        msg = json.loads(payload)
        if msg['type'] == 'request_state':
            self._send_state()
        if msg['type'] == 'state':
            self.latest_state_received = msg
        if msg['type'] == 'event':
            self._process_event(msg)

    def _process_event(self, msg):
        try:
            event_type = msg['data']['event_type']
            payload = msg['data']['payload']
            for callback in self.callbacks:
                callback(event_type, payload)
        except KeyError as e:
            logger.exception('error processing event')

    def _message_receiver(self):
        self.client = Client(self.address, authkey=self.authkey)
        self.send_event(Events.CLIENT_DISCOVERY, None)
        while True:
            try:
                msg = self.client.recv_bytes()
                self._process_message(msg)
            except EOFError as eof_error:
                logger.exception('client connection closed unexpectedly')
                self.client.close()
                self.client = Client(self.address, authkey=self.authkey)
            except Exception as e:
                logger.exception('unexpected error occured in message receiver'.format(e))

    def _send(self, data, msg_type='event'):
        payload = {'type': msg_type, 'client': self.client_name, 'data': data}
        msg = json.dumps(payload)
        if self.client is not None and self.client.closed is False:
            self.client.send_bytes(msg)
        else:
            # TODO: raise error
            pass

    def _start(self):
        receiver = Thread(target=self._message_receiver)
        receiver.daemon = True
        receiver.start()

    def get_state(self, client_name, default=None, timeout=5):
        self.latest_state_received = None
        data = {'client': client_name}
        self._send(data, msg_type='request_state')
        t_end = time.time() + timeout
        while time.time() < t_end:
            if self.latest_state_received is not None and self.latest_state_received['client'] == client_name:
                response = self.latest_state_received
                self.latest_state_received = None
                return response
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
