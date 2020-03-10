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
import msgpack
from select import select
from collections import deque
from threading import Thread


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
    """
    This class handles IPC communications.

    It uses netstring: <data_length>:<data>,\n
    * data_length: The length of `data`
    * data: The actual payload, using the format <encoding_type>:<encoded_data>
      * encoding_type: A one-character reference to the used encoding protocol
        * 1 = msgpack
      * encoded_data: The encoded data
    """

    def __init__(self, stream, logger, command_receiver=None):
        self._buffer = ''
        self._command_queue = Queue()
        self._stream = stream
        self._read_thread = None
        self._logger = logger
        self._running = False
        self._command_receiver = command_receiver

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
        wait_for_length = None
        while self._running:
            try:
                if wait_for_length is None:
                    # Waiting for a new command to start. Let's do 1 second polls to make sure we're not blocking forever
                    # in case no new data will come
                    read_available, _, _ = select([self._stream], [], [], 1.0)
                    if not read_available:
                        continue
                # Minimum dataset: 0:x:,\n = 6 characters, so we always read at least 6 chars
                self._buffer += self._stream.read(6 if wait_for_length is None else wait_for_length)
                if wait_for_length is None:
                    if ':' not in self._buffer:
                        # This is unexpected, discard data
                        self._buffer = ''
                        continue
                    length, self._buffer = self._buffer.split(':', 1)
                    # The length defines the encoded data length. We to add 4 because of the `<encoding_protocol>:` and `,\n`
                    wait_for_length = int(length) - len(self._buffer) + 2
                    if wait_for_length > 0:
                        continue
                if self._buffer.endswith(',\n'):
                    protocol, self._buffer = self._buffer.split(':', 1)
                    command = PluginIPCStream._decode(protocol, self._buffer[:-2])
                    if command is None:
                        # Unexpected protocol
                        self._buffer = ''
                        wait_for_length = None
                        continue
                    if self._command_receiver is not None:
                        self._command_receiver(command)
                    else:
                        self._command_queue.put(command)
                self._buffer = ''
                wait_for_length = None
            except Exception as ex:
                self._logger('Unexpected read exception', ex)

    def get(self, block=True, timeout=None):
        return self._command_queue.get(block, timeout)

    @staticmethod
    def write(data):
        encode_type = '1'
        data = PluginIPCStream._encode(encode_type, data)
        return '{0}:{1}:{2},\n'.format(len(data) + 2, encode_type, data)

    @staticmethod
    def _encode(encode_type, data):
        if encode_type == '1':
            return msgpack.dumps(data)
        return ''

    @staticmethod
    def _decode(encode_type, data):
        if data == '':
            return None
        if encode_type == '1':
            return msgpack.loads(data)
        return None
