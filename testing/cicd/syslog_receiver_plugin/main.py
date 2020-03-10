# Copyright (C) 2020 OpenMotics BV
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
Plugin to queue and expose all master events on the api.
"""

from collections import deque
import json
import socket
from threading import Lock

from plugins.base import OMPluginBase, background_task, om_expose

if False:  # MYPY
    from typing import Any, List


class SyslogReceiver(OMPluginBase):
    name = 'syslog_receiver'
    version = '0.0.1'
    interfaces = []  # type: List[Any]

    def __init__(self, webinterface, logger):
        # type: (Any, Any) -> None
        super(SyslogReceiver, self).__init__(webinterface, logger)
        self._lock = Lock()
        self._logs = deque([], 128)  # type: deque

    @background_task
    def listen(self):
        # type: () -> None
        while True:
            try:
                sock = socket.socket(type=socket.SOCK_DGRAM)
                sock.bind(('0.0.0.0', 514))
                self.logger('receiving logs on udp:514')
                while True:
                    log = sock.recv(1024)
                    with self._lock:
                        self._logs.append(log)
            except Exception as e:
                self.logger('error: {}'.format(e))

    @om_expose
    def reset(self):
        # type: () -> str
        with self._lock:
            self._logs.clear()
            return json.dumps({'logs': list(self._logs)})

    @om_expose
    def logs(self):
        # type: () -> str
        with self._lock:
            return json.dumps({'logs': list(self._logs)})
