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
        :type serial: Instance of :class`serial.Serial`
        """
        self._serial = serial
        self._write_lock = Lock()

        self._subscribers = {}
        self._maintenance_active = False
        self._stopped = True

        self._read_data_thread = Thread(target=self._read_data, name='AIO maintenance read thread')
        self._read_data_thread.setDaemon(True)

    def start(self):
        self._stopped = False
        self._read_data_thread.start()

    def stop(self):
        self._stopped = True

    def add_subscriber(self, subscriber_id, data_received):
        self._subscribers[subscriber_id] = data_received

    def remove_subscriber(self, subscriber_id):
        self._subscribers.pop(subscriber_id, None)

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

            for callback in self._subscribers.values():
                try:
                    callback(message.rstrip())
                except Exception:
                    logger.exception('Unexpected exception during maintenance callback')

    def write(self, message):
        if message is None:
            return
        with self._write_lock:
            self._serial.write('{0}\r\n'.format(message.strip()))
