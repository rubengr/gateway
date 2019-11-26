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

""" Module contains all websocket related logic """

import msgpack
import cherrypy
import logging
from ws4py import WS_VERSION
from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket
from gateway.observer import Event

logger = logging.getLogger('openmotics')


class OMPlugin(WebSocketPlugin):
    def __init__(self, bus):
        WebSocketPlugin.__init__(self, bus)
        self.metrics_receivers = {}
        self.events_receivers = {}
        self.maintenance_receivers = {}

    def start(self):
        WebSocketPlugin.start(self)
        self.bus.subscribe('add-metrics-receiver', self.add_metrics_receiver)
        self.bus.subscribe('get-metrics-receivers', self.get_metrics_receivers)
        self.bus.subscribe('remove-metrics-receiver', self.remove_metrics_receiver)
        self.bus.subscribe('add-events-receiver', self.add_events_receiver)
        self.bus.subscribe('get-events-receivers', self.get_events_receivers)
        self.bus.subscribe('remove-events-receiver', self.remove_events_receiver)
        self.bus.subscribe('update-events-receiver', self.update_events_receiver)
        self.bus.subscribe('add-maintenance-receiver', self.add_maintenance_receiver)
        self.bus.subscribe('get-maintenance-receivers', self.get_maintenance_receivers)
        self.bus.subscribe('remove-maintenance-receiver', self.remove_maintenance_receiver)

    def stop(self):
        WebSocketPlugin.stop(self)
        self.bus.unsubscribe('add-metrics-receiver', self.add_metrics_receiver)
        self.bus.unsubscribe('get-metrics-receivers', self.get_metrics_receivers)
        self.bus.unsubscribe('remove-metrics-receiver', self.remove_metrics_receiver)
        self.bus.unsubscribe('add-events-receiver', self.add_events_receiver)
        self.bus.unsubscribe('get-events-receivers', self.get_events_receivers)
        self.bus.unsubscribe('remove-events-receiver', self.remove_events_receiver)
        self.bus.unsubscribe('update-events-receiver', self.update_events_receiver)
        self.bus.unsubscribe('add-maintenance-receiver', self.add_maintenance_receiver)
        self.bus.unsubscribe('get-maintenance-receivers', self.get_maintenance_receivers)
        self.bus.unsubscribe('remove-maintenance-receiver', self.remove_maintenance_receiver)

    def add_metrics_receiver(self, client_id, receiver_info):
        self.metrics_receivers[client_id] = receiver_info

    def get_metrics_receivers(self):
        return self.metrics_receivers

    def remove_metrics_receiver(self, client_id):
        self.metrics_receivers.pop(client_id, None)

    def add_events_receiver(self, client_id, receiver_info):
        self.events_receivers[client_id] = receiver_info

    def get_events_receivers(self):
        return self.events_receivers

    def remove_events_receiver(self, client_id):
        self.events_receivers.pop(client_id, None)

    def update_events_receiver(self, client_id, receiver_info):
        self.events_receivers[client_id].update(receiver_info)

    def add_maintenance_receiver(self, client_id, receiver_info):
        self.maintenance_receivers[client_id] = receiver_info

    def get_maintenance_receivers(self):
        return self.maintenance_receivers

    def remove_maintenance_receiver(self, client_id):
        self.maintenance_receivers.pop(client_id, None)


class OMSocketTool(WebSocketTool):
    def upgrade(self, protocols=None, extensions=None, version=WS_VERSION, handler_cls=WebSocket, heartbeat_freq=None):
        _ = protocols  # ws4py doesn't support protocols the way we like (using them for authentication)
        request = cherrypy.serving.request
        allowed_protocols = []
        requested_protocols = request.headers.get('Sec-WebSocket-Protocol')
        if requested_protocols:
            for protocol in requested_protocols.split(','):
                protocol = protocol.strip()
                if 'authorization.bearer.' in protocol:
                    allowed_protocols.append(protocol)
        return WebSocketTool.upgrade(self,
                                     protocols=allowed_protocols,
                                     extensions=extensions,
                                     version=version,
                                     handler_cls=handler_cls,
                                     heartbeat_freq=heartbeat_freq)


class OMSocket(WebSocket):
    def once(self):
        """
        Almost exact the same code as in `WebSocket`, but somehow resolves an issue where not all
        data was read from the (secure) socket.
        """
        if self.terminated:
            return False

        try:
            b = self.sock.recv(self.reading_buffer_size)
            if self._is_secure:
                extra_b = self._get_from_pending()
                while len(extra_b) > 0:
                    b += extra_b
                    extra_b = self._get_from_pending()
        except Exception as e:
            self.unhandled_error(e)
            return False
        else:
            if not self.process(b):
                return False

        return True


# noinspection PyUnresolvedReferences
class MetricsSocket(OMSocket):
    """
    Handles web socket communications for metrics
    """
    def opened(self):
        if not hasattr(self, 'metadata'):
            return
        cherrypy.engine.publish('add-metrics-receiver',
                                self.metadata['client_id'],
                                {'source': self.metadata['source'],
                                 'metric_type': self.metadata['metric_type'],
                                 'token': self.metadata['token'],
                                 'socket': self})
        self.metadata['interface']._metrics_collector.set_websocket_interval(self.metadata['client_id'],
                                                                             self.metadata['metric_type'],
                                                                             self.metadata['interval'])

    def closed(self, *args, **kwargs):
        _ = args, kwargs
        if not hasattr(self, 'metadata'):
            return
        client_id = self.metadata['client_id']
        cherrypy.engine.publish('remove-metrics-receiver', client_id)
        self.metadata['interface']._metrics_collector.set_websocket_interval(client_id, self.metadata['metric_type'], None)


# noinspection PyUnresolvedReferences
class EventsSocket(OMSocket):
    """
    Handles web socket communications for events
    """
    def opened(self):
        if not hasattr(self, 'metadata'):
            return
        cherrypy.engine.publish('add-events-receiver',
                                self.metadata['client_id'],
                                {'token': self.metadata['token'],
                                 'subscribed_types': [],
                                 'socket': self})

    def closed(self, *args, **kwargs):
        _ = args, kwargs
        if not hasattr(self, 'metadata'):
            return
        client_id = self.metadata['client_id']
        cherrypy.engine.publish('remove-events-receiver', client_id)

    def received_message(self, message):
        if not hasattr(self, 'metadata'):
            return
        allowed_types = [Event.Types.OUTPUT_CHANGE,
                         Event.Types.THERMOSTAT_CHANGE,
                         Event.Types.THERMOSTAT_GROUP_CHANGE,
                         Event.Types.SHUTTER_CHANGE,
                         Event.Types.INPUT_TRIGGER]
        try:
            data = msgpack.loads(message.data)
            event = Event.deserialize(data)
            if event.type == Event.Types.ACTION:
                if event.data['action'] == 'set_subscription':
                    subscribed_types = [stype for stype in event.data['types'] if stype in allowed_types]
                    cherrypy.engine.publish('update-events-receiver',
                                            self.metadata['client_id'],
                                            {'subscribed_types': subscribed_types})
            elif event.type == Event.Types.PING:
                self.send(msgpack.dumps(Event(event_type=Event.Types.PONG,
                                              data=None).serialize()), binary=True)
        except Exception as ex:
            logger.exception('Error receiving message: %s', ex)
            # Ignore malformed data processing; in that case there's nothing that will happen


# noinspection PyUnresolvedReferences
class MaintenanceSocket(OMSocket):
    """
    Handles web socket communications for maintenance mode
    """
    def opened(self):
        if not hasattr(self, 'metadata'):
            return
        client_id = self.metadata['client_id']
        cherrypy.engine.publish('add-maintenance-receiver',
                                client_id,
                                {'token': self.metadata['token'],
                                 'socket': self})
        self.metadata['interface']._maintenance_service.add_subscriber(client_id, self._send_maintenance_data)

    def closed(self, *args, **kwargs):
        _ = args, kwargs
        if not hasattr(self, 'metadata'):
            return
        client_id = self.metadata['client_id']
        cherrypy.engine.publish('remove-maintenance-receiver', client_id)
        self.metadata['interface']._maintenance_service.remove_subscriber(client_id)

    def received_message(self, message):
        if not hasattr(self, 'metadata'):
            return
        try:
            self.metadata['interface']._maintenance_service.write(message.data)
        except Exception as ex:
            logger.exception('Error receiving data: %s', ex)

    def _send_maintenance_data(self, data):
        try:
            self.send(data, binary=False)
        except Exception as ex:
            logger.exception('Error sending data: %s', ex)
