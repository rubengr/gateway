# Copyright (C) 2016 OpenMotics BVBA
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
The maintenance module contains the MaintenanceService class.
"""

import time
import logging
import traceback
import socket
from threading import Timer, Thread
from wiring import provides, inject, SingletonScope, scope
from platform_utils import System
from master_communicator import InMaintenanceModeException

LOGGER = logging.getLogger('openmotics')


class MaintenanceService(object):
    """
    The maintenance service accepts tcp connections. If a connection is accepted it
    grabs the serial port, sets the gateway mode to CLI and forwards input and output
    over the tcp connection.
    """

    # TODO: Support maintenance websocket

    MAINTENANCE_TIMEOUT = 600

    @provides('maintenance_service')
    @scope(SingletonScope)
    @inject(master_communicator='master_classic_communicator', privatekey_filename='ssl_private_key', certificate_filename='ssl_certificate')
    def __init__(self, master_communicator, privatekey_filename, certificate_filename):
        """
        Construct a MaintenanceServer.

        :param master_communicator: the communication with the master.
        :type master_communicator: master.master_communicator.MasterCommunicator
        :param privatekey_filename: the filename of the private key for the SSL connection.
        :param certificate_filename: the filename of the certificate for the SSL connection.
        """
        self._master_communicator = master_communicator
        self._privatekey_filename = privatekey_filename
        self._certificate_filename = certificate_filename
        self._last_maintenance_send_time = 0
        self._maintenance_timeout_timer = None
        self._serial_redirector = None
        self._stopped_callback = None

    def start_maintenance(self, port, stopped_callback, connection_timeout=60, ):
        """
        Start the maintenance service in a new thread. The maintenance service only accepts
        one connection. If this connection is not established within the connection_timeout, the
        server socket is closed.

        :param port: the port for the SSL socket.
        :param stopped_callback: Called when maintenance mode is stopped
        :param connection_timeout: timeout for the server socket.
        """
        self._stopped_callback = stopped_callback
        thread = Thread(target=self._socket_server, args=(port, connection_timeout))
        thread.setName('Maintenance socket thread')
        thread.daemon = True
        thread.start()

    def _socket_server(self, port, connection_timeout):
        """
        Run the maintenance service, accepts a connection. Starts a serial
        redirector when a connection is accepted.
        """
        LOGGER.info('Starting maintenance socket on port %s', port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(connection_timeout)
        sock = System.get_ssl_socket(sock,
                                     private_key_filename=self._privatekey_filename,
                                     certificate_filename=self._certificate_filename)
        sock.bind(('', port))
        sock.listen(1)

        try:
            LOGGER.info('Waiting for maintenance connection.')
            self._handle_connection(*sock.accept())
            LOGGER.info('Maintenance session ended, closing maintenance socket')
            sock.close()
        except socket.timeout:
            LOGGER.info('Maintenance socket timed out, closing.')
            sock.close()
        except Exception:
            LOGGER.error('Error in maintenance service: %s', traceback.format_exc())
            sock.close()

    def _handle_connection(self, connection, addr):
        """
        Handles one incoming connection.
        """
        LOGGER.info('Maintenance connection from %s', str(addr))
        connection.settimeout(1)
        try:
            connection.sendall('Starting maintenance mode, waiting for other actions to complete ...\n')
            self._start_maintenance_mode()
            LOGGER.info('Maintenance connection got lock')

            self._serial_redirector = SerialRedirector(self._master_communicator, connection)
            self._serial_redirector.run()
        except InMaintenanceModeException:
            connection.sendall('Maintenance mode already started. Closing connection.')
        finally:
            LOGGER.info('Maintenance connection closed')
            self._stop_maintenance_mode()
            connection.close()

    def _start_maintenance_mode(self):
        """
        Start maintenance mode, if the time between send_maintenance_data calls exceeds the
        timeout, the maintenance mode will be closed automatically.
        """
        self._master_communicator.start_maintenance_mode()
        self._maintenance_timeout_timer = Timer(MaintenanceService.MAINTENANCE_TIMEOUT, self._check_maintenance_timeout)
        self._maintenance_timeout_timer.start()

    def _check_maintenance_timeout(self):
        """
        Checks if the maintenance if the timeout is exceeded, and closes maintenance mode
        if required.
        """
        timeout = MaintenanceService.MAINTENANCE_TIMEOUT
        if self._master_communicator.in_maintenance_mode():
            current_time = time.time()
            if self._last_maintenance_send_time + timeout < current_time:
                LOGGER.info('Stopping maintenance mode because of timeout.')
                self._stop_maintenance_mode()
                self._serial_redirector.stop()
            else:
                wait_time = self._last_maintenance_send_time + timeout - current_time
                self._maintenance_timeout_timer = Timer(wait_time, self._check_maintenance_timeout)
                self._maintenance_timeout_timer.start()
        else:
            self._stop_maintenance_mode()
            self._serial_redirector.stop()

    def _stop_maintenance_mode(self):
        """ Stop maintenance mode. """
        self._master_communicator.stop_maintenance_mode()

        if self._maintenance_timeout_timer is not None:
            self._maintenance_timeout_timer.cancel()
            self._maintenance_timeout_timer = None

        if self._stopped_callback is not None:
            self._stopped_callback()


class SerialRedirector(object):
    """
    Forwards data between the serial connection and the tcp socket
    """

    def __init__(self, master_communicator, connection):
        """
        :type master_communicator: master.master_communicator.MasterCommunicator
        """
        self.last_maintenance_send_time = 0
        self._master_communicator = master_communicator
        self._connection = connection
        self._reader_thread = None
        self._stopped = False

    def run(self):
        """
        Run the serial redirector, spins off a reader thread and uses
        the current thread for writing
        """
        self._reader_thread = Thread(target=self.reader)
        self._reader_thread.setName('Maintenance reader thread')
        self._reader_thread.start()
        self.writer()
        self._reader_thread.join()

    def stop(self):
        """ Stop the serial redirector. """
        self._stopped = True

    def writer(self):
        """ Reads from the socket and writes to the serial port. """
        while not self._stopped:
            try:
                try:
                    data = self._connection.recv(1024)
                    if not data:
                        LOGGER.info('Stopping maintenance mode due to no data.')
                        break
                    if data.startswith('exit'):
                        LOGGER.info('Stopping maintenance mode due to exit.')
                        break

                    self.last_maintenance_send_time = time.time()
                    self._master_communicator.send_maintenance_data(data)
                except Exception as exception:
                    if System.handle_socket_exception(self._connection, exception, LOGGER):
                        continue
                    else:
                        break
            except Exception:
                LOGGER.error('Exception in maintenance mode: %s\n', traceback.format_exc())
                break
        self._stopped = True

    def reader(self):
        """ Reads from the serial port and writes to the socket. """
        while not self._stopped:
            try:
                data = self._master_communicator.get_maintenance_data()
                if data:
                    self._connection.sendall(data)
            except Exception:
                LOGGER.error('Exception in maintenance mode: %s\n', traceback.format_exc())
                break
        self._stopped = True
