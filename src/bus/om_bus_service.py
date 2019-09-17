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
IPC Bus messaging service
"""

import logging
import time
try:
    import json
except ImportError:
    import simplejson as json
from multiprocessing.connection import Listener
from threading import Thread
from signal import signal, SIGTERM

logger = logging.getLogger('openmotics')


class MessageService(object):

    def __init__(self, ip='localhost', port=10000, authkey='openmotics'):
        self.connections = {}
        self.address = (ip, port)  # family is deduced to be 'AF_INET'
        self.authkey = authkey
        self.listener = Listener(self.address, authkey=self.authkey)
        self._stop = False

    def _multicast(self, source, msg):
        for connection, client_name in self.connections.iteritems():
            if client_name != source and connection is not None:
                self._send(connection, msg)

    def _unicast(self, destination, msg):
        for connection, client_name in self.connections.iteritems():
            if client_name == destination and connection is not None:
                self._send(connection, msg)
                break

    def _send(self, conn, msg):
        payload = json.dumps(msg)
        conn.send_bytes(payload)

    def _verify_client(self, conn, msg):
        should_be = self.connections.get(conn, None)
        if should_be is None:
            self.connections[conn] = msg['source']
            should_be = msg['source']
            logger.info('Detected new client name {0}'.format(msg['source']))
        pretends_to_be = msg['source']
        if pretends_to_be != should_be:
            raise EOFError('Client cannot use name {0} on connection for {1}'.format(pretends_to_be, should_be))

    def _process_message(self, conn, msg):
        # 1. update client name for connection
        self._verify_client(conn, msg)

        # 2. route message based on destination
        destination = msg.get('destination', None)
        if destination is None:
            source = msg.get('source', None)
            self._multicast(source, msg)
        else:
            self._unicast(destination, msg)

    def _receiver(self, conn):
        while not conn.closed:
            try:
                payload = conn.recv_bytes()
                msg = json.loads(payload)
                self._process_message(conn, msg)
            except IOError as io_error:
                logger.exception('Error receiving message from client {0}: {1}'.format(self.connections.get(conn, None), io_error))
                self._close(conn)
            except ValueError:
                logger.exception('Error decoding payload from client {0}'.format(self.connections.get(conn, None)))
            except EOFError as e:
                self._close(conn)
            except Exception:
                logger.exception('Unknown error in receiver')
                self._close(conn)

    def _close(self, conn):
        client_name = self.connections.get(conn, 'unknown')
        conn.close()
        if conn in self.connections:
            del self.connections[conn]
        logger.info('Connection closed from {0}'.format(client_name))

    def _server(self):
        logger.info('Starting OM messaging service...')
        self._stop = False
        while not self._stop:
            try:
                conn = self.listener.accept()
                logger.info('connection accepted from {0}'.format(self.listener.last_accepted))
                receiver = Thread(target=self._receiver, args=(conn,))
                receiver.daemon = True
                receiver.start()
            except IOError as io_error:
                logger.error('IOError in accepting connection: {0}'.format(io_error))
            except Exception as e:
                logger.exception('Error in message service. Restarting...')
                self.listener.close()
                time.sleep(1)
                self.listener = Listener(self.address, authkey=self.authkey)

    def start(self):
        def stop(signum, frame):
            """ This function is called on SIGTERM. """
            _ = signum, frame
            logger.info('Stopping OM messaging service...')
            self._stop = True
            logger.info('Stopping OM messaging service... Done')
        signal(SIGTERM, stop)

        server = Thread(target=self._server)
        server.daemon = True
        server.start()
