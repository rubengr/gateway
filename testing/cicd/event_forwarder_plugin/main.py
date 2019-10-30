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
Plugin to forward all master events to a socket.
"""

import simplejson as json
import time
from multiprocessing.connection import Listener

try:  # When running as plugin
    from plugins.base import (
        OMPluginBase, PluginConfigChecker,
        background_task, om_expose, receive_events)
except ImportError:  # When running in IDE
    from plugin_runtime.base import (
        OMPluginBase, PluginConfigChecker,
        background_task, om_expose, receive_events)


class EventForwarder(OMPluginBase):
    name = 'EventForwarder'
    version = '0.0.10'
    interfaces = [('config', '1.0')]

    config_description = [
        {
            'name': 'port',
            'type': 'int',
            'description': 'Internal port for this process to listen on',
        },
    ]

    default_config = {
        'port': 6666,
    }

    def __init__(self, webinterface, logger):
        super(EventForwarder, self).__init__(webinterface, logger)
        self.config = self.read_config(self.default_config)
        self.config_checker = PluginConfigChecker(self.config_description)
        self.connections = {}

    @background_task
    def listen(self):
        port = self.config['port']
        listener = Listener(('localhost', port))
        self.logger('Listening on port localhost:%s' % port)
        while True:
            if port != self.config['port']:
                listener.close()
                self.connections = {}
                port = self.config['port']
                listener = Listener('localhost', port)
            connection = listener.accept()
            # Hangs until a client connects
            client_address = listener.last_accepted
            self.connections[client_address] = connection
            self.logger('Connection accepted on port %s from %s:%s'
                        % (port, client_address[0], client_address[1]))

    @receive_events
    def forward_master_events(self, event):
        """
        Forward events of the master. You can set events e.g. as advanced
        action when configuring inputs.
        :param event: Event number sent by the master
        :type event: int
        """
        if not self.connections:
            self.logger('Received event: %s (silent)' % event)
            return
        self.logger('Received event: %s (forwarding)' % event)
        for address, connection in self.connections.items():  # Yes, a copy!
            try:
                connection.send(event)
            except IOError:
                self.logger(
                    'Failed to forward event, closing connection for %s:%s'
                    % (address[0], address[1]))
                connection.close()
                del self.connections[address]

    @om_expose
    def get_config_description(self):
        return json.dumps(EventForwarder.config_description)

    @om_expose
    def get_config(self):
        return json.dumps(self.config)

    @om_expose
    def set_config(self, config):
        config = json.loads(config)
        self.config_checker.check_config(config)
        self.config = config
        self.write_config(config)
        return json.dumps({'success': True})

