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
The maintenance module contains the MaintenanceService class.
"""

import time
import logging
from threading import Thread, Lock
from wiring import provides, inject, SingletonScope, scope

logger = logging.getLogger('openmotics')


class MaintenanceService(object):

    @provides('maintenance_service')
    @scope(SingletonScope)
    @inject(serial='cli_serial')
    def __init__(self, serial):
        """
        :param serial: Serial port to communicate with
        :type serial: serial.Serial
        """
        self._serial = serial
        self._write_lock = Lock()

        self._receiver_callback = None
        self._maintenance_active = False
        self._stopped = True
        self._read_data_thread = None

    def start(self):
        self._stopped = False
        self._read_data_thread = Thread(target=self._read_data, name='Core maintenance read thread')
        self._read_data_thread.daamon = True
        self._read_data_thread.start()

    def stop(self):
        self._stopped = True

    def activate(self):
        pass  # Core has a separate serial port

    def deactivate(self):
        pass  # Core has a separate serial port

    def set_receiver(self, callback):
        self._receiver_callback = callback

    def _read_data(self):
        data = ''
        previous_length = 0
        while not self._stopped:
            # Read what's now on the buffer
            num_bytes = self._serial.inWaiting()
            if num_bytes > 0:
                data += self._serial.read(num_bytes)

            if len(data) == previous_length:
                time.sleep(0.1)
                continue
            previous_length = len(data)

            if '\n' not in data:
                continue

            message, data = data.split('\n', 1)

            if self._receiver_callback is not None:
                try:
                    self._receiver_callback(message.rstrip())
                except Exception:
                    logger.exception('Unexpected exception during maintenance callback')

    def write(self, message):
        if message is None:
            return
        with self._write_lock:
            self._serial.write('{0}\r\n'.format(message.strip()))
