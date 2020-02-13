# Copyright (C) 2019 OpenMotics BV
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
A few helper classes
"""

import time
from collections import deque
from threading import Thread


try:
    import ujson as json
except ImportError:
    # This is the case when the plugin runtime is unittested
    import json


class Full(Exception):
    pass


class Empty(Exception):
    pass


class Queue(object):
    def __init__(self, size=None):
        self._queue = deque()
        self._size = size  # Not used

    def put(self, value, block=False):
        _ = block
        self._queue.appendleft(value)

    def get(self, block=True, timeout=None):
        if not block:
            try:
                return self._queue.pop()
            except IndexError:
                raise Empty()
        start = time.time()
        while timeout is None or time.time() - start < timeout:
            try:
                return self._queue.pop()
            except IndexError:
                sleep = 0.025
                if timeout is None or timeout > 1:
                    sleep = 0.1
                time.sleep(sleep)
        raise Empty()

    def qsize(self):
        return len(self._queue)

    def clear(self):
        return self._queue.clear()


class PluginIPCStream(object):

    def __init__(self, stream, logger):
        self._buffer = ''
        self._command_queue = Queue()
        self._stream = stream
        self._read_thread = None
        self._logger = logger
        self._running = False

    def start(self):
        self._running = True
        self._read_thread = Thread(target=self._read)
        self._read_thread.daemon = True
        self._read_thread.start()

    def stop(self):
        self._running = False
        if self._read_thread is not None:
            self._read_thread.join()

    def _read(self):
        """ Uses Netstring encoding """
        wait_for_length = None
        while self._running:
            try:
                self._buffer += self._stream.read(1 if wait_for_length is None else wait_for_length)
                if wait_for_length is None:
                    if ':' not in self._buffer:
                        continue
                    length, self._buffer = self._buffer.split(':')
                    wait_for_length = int(length) - len(self._buffer) + 2
                    continue
                if self._buffer.endswith(',\n'):
                    self._command_queue.put(json.loads(self._buffer[:-2]))
                self._buffer = ''
                wait_for_length = None
            except Exception as ex:
                self._logger('Unexpected read exception', ex)

    def get(self, block=True, timeout=None):
        return self._command_queue.get(block, timeout)

    @staticmethod
    def encode(data):
        """ Uses Netstring encoding """
        data = json.dumps(data)
        return '{0}:{1},\n'.format(len(data), data)
