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

import collections
import copy
import json
import time
from threading import Lock

from plugins.base import OMPluginBase, om_expose, receive_events

if False:  # MYPY
    from typing import Any, Dict, List


class EventObserver(OMPluginBase):
    name = 'event_observer'
    version = '0.0.1'
    interfaces = []  # type: List[Any]

    def __init__(self, webinterface, logger):
        # type: (Any, Any) -> None
        super(EventObserver, self).__init__(webinterface, logger)
        self._lock = Lock()
        unknown_event = {'received_at': 0.0, 'outputs': [None,None,None,None,None,None,None,None]}
        self._events = [unknown_event]  # type: List[Dict[str,Any]]

    @receive_events
    def handle_master_events(self, event):
        # type: (int) -> None
        received_at = time.time()
        output_id, output_status = (event / 2, event % 2)
        self.logger('Received event: %s for output=%s -> status=%s' % (event, output_id, output_status))
        with self._lock:
            outputs = copy.copy(self._events[-1]['outputs'])
            outputs[output_id] = output_status
            output_event = {'received_at': received_at, 'outputs': outputs,
                            'output_id': output_id, 'output_status': output_status}
            self._events.append(output_event)
            self._events = self._events[-8:]

    @om_expose
    def events(self):
        # type: () -> str
        return json.dumps({'events': self._events})
