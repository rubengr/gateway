from multiprocessing.connection import Listener
import logging
from threading import Thread

try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger('openmotics')

class MessageService():

    def __init__(self, ip='localhost', port=6000, authkey='openmotics'):
        self.connections = {}
        address = (ip, port)  # family is deduced to be 'AF_INET'
        self.listener = Listener(address, authkey=authkey)

    def multicast(self, source_connection, msg):
        for connection, client_name in self.connections.iteritems():
            if connection != source_connection:
                self._send(connection, msg)

    def unicast(self, target_client_name, msg):
        for connection, client_name in self.connections.iteritems():
            if client_name == target_client_name and connection is not None:
                self._send(connection, msg)
                break

    def _send(self, conn, msg):
        payload = json.dumps(msg)
        conn.send_bytes(payload)

    def _verify_client(self, conn, msg):
        should_be = self.connections.get(conn, None)
        if should_be is None:
            self.connections[conn] = msg['client']
            should_be = msg['client']
            print('Detected new client name {0}'.format(msg['client']))
        pretends_to_be = msg['client']
        if pretends_to_be != should_be:
            raise EOFError('Client cannot use name {0} on connection for {1}'.format(pretends_to_be, should_be))

    def process_message(self, conn, msg):
        # 1. update client name for connection
        self._verify_client(conn, msg)

        # 2. route message based on type
        msg_type = msg.get('type', None)
        if msg_type is None:
            print('no message type defined')
        elif msg_type == 'event' or msg_type == 'state':
            self.multicast(conn, msg)
        elif msg['type'] == 'request_state':
            target_client_name = msg['data']['client']
            self.unicast(target_client_name, msg)
        else:
            print('unknown message type: {0}'.format(msg_type))

    def receiver(self, conn):
        try:
            while True:
                payload = conn.recv_bytes()
                msg = json.loads(payload)
                self.process_message(conn, msg)
        except EOFError as e:
            client_name = self.connections[conn]
            conn.close()
            print('Connection closed {0}'.format(client_name))
            del self.connections[conn]

    def start(self):
        while True:
            try:
                conn = self.listener.accept()
                print('connection accepted from {0}'.format(self.listener.last_accepted))
                receiver = Thread(target=self.receiver, args=(conn, ))
                receiver.daemon = True
                receiver.start()
            except Exception as e:
                logger.exception('Error in message service. Shutting down...')
                self.listener.close()