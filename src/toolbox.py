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
                time.sleep(0.025 if timeout < 1 else 0.1)
        raise Empty()

    def qsize(self):
        return len(self._queue)

    def clear(self):
        return self._queue.clear()


class PluginIPCStream(object):

    def __init__(self):
        self._buffer = ''

    def feed(self, stream):
        self._buffer += stream
        if '\n' in self._buffer:
            response, self._buffer = self._buffer.split('\n', 1)
            return json.loads(response)
        return

    @staticmethod
    def encode(data):
        return '{0}\n'.format(json.dumps(data))
