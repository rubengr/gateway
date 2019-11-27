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
from threading import Timer, Thread
from wiring import provides, inject, SingletonScope, scope

logger = logging.getLogger('openmotics')


class MaintenanceService(object):
    """
    The maintenance service accepts tcp connections. If a connection is accepted it
    grabs the serial port, sets the gateway mode to CLI and forwards input and output
    over the tcp connection.
    """

    MAINTENANCE_TIMEOUT = 600

    @provides('maintenance_service')
    @scope(SingletonScope)
    @inject(master_communicator='master_classic_communicator')
    def __init__(self, master_communicator):
        """
        Construct a MaintenanceServer.

        :param master_communicator: the communication with the master.
        :type master_communicator: master.master_communicator.MasterCommunicator
        """
        self._master_communicator = master_communicator
        self._receiver_callback = None
        self._last_maintenance_send_time = 0
        self._maintenance_timeout_timer = None
        self._last_maintenance_send_time = 0
        self._read_data_thread = None
        self._stopped = False

    def start(self):
        pass  # Classis doesn't have a permanent running maintenance

    def stop(self):
        pass  # Classis doesn't have a permanent running maintenance

    def set_receiver(self, callback):
        self._receiver_callback = callback

    def is_active(self):
        return self._master_communicator.in_maintenance_mode()

    def activate(self):
        """
        Activates maintenance mode, If no data is send for too long, maintenance mode will be closed automatically.
        """
        self._master_communicator.start_maintenance_mode()
        self._maintenance_timeout_timer = Timer(MaintenanceService.MAINTENANCE_TIMEOUT, self._check_maintenance_timeout)
        self._maintenance_timeout_timer.start()
        self._stopped = False
        self._read_data_thread = Thread(target=self._read_data, name='Classic maintenance read thread')
        self._read_data_thread.daamon = True
        self._read_data_thread.start()

    def deactivate(self):
        self._stopped = True
        if self._read_data_thread is not None:
            self._read_data_thread.join()
            self._read_data_thread = None
        self._master_communicator.stop_maintenance_mode()

        if self._maintenance_timeout_timer is not None:
            self._maintenance_timeout_timer.cancel()
            self._maintenance_timeout_timer = None

    def _check_maintenance_timeout(self):
        """
        Checks if the maintenance if the timeout is exceeded, and closes maintenance mode
        if required.
        """
        timeout = MaintenanceService.MAINTENANCE_TIMEOUT
        if self._master_communicator.in_maintenance_mode():
            current_time = time.time()
            if self._last_maintenance_send_time + timeout < current_time:
                logger.info('Stopping maintenance mode because of timeout.')
                self.deactivate()
            else:
                wait_time = self._last_maintenance_send_time + timeout - current_time
                self._maintenance_timeout_timer = Timer(wait_time, self._check_maintenance_timeout)
                self._maintenance_timeout_timer.start()
        else:
            self.deactivate()

    def write(self, message):
        self._last_maintenance_send_time = time.time()
        self._master_communicator.send_maintenance_data(message)

    def _read_data(self):
        """ Reads from the serial port and writes to the socket. """
        data = ''
        while not self._stopped:
            try:
                data += self._master_communicator.get_maintenance_data()
                if '\n' in data:
                    message, data = data.split('\n', 1)
                    if self._receiver_callback is not None:
                        try:
                            self._receiver_callback(message.rstrip())
                        except Exception:
                            logger.exception('Unexpected exception during maintenance callback')
            except Exception:
                logger.exception('Exception in maintenance read thread')
                break
        self.deactivate()
