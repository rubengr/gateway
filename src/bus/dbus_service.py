# Copyright (C) 2018 OpenMotics BVBA
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
The DBus service provides all tooling to send/receive events and request/receive state reports
"""

import dbus
import dbus.service
import dbus.mainloop.glib
try:
    import json
except ImportError:
    import simplejson as json


class DBusService(dbus.service.Object):
    """ The DBus service provides all tooling to send/receive events and request/receive state reports """

    PATH = '/com/openmotics/{0}'
    BUS = 'com.openmotics.{0}'
    INTERFACE = 'com.openmotics.{0}'

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    class Events(object):
        CLOUD_REACHABLE = 'CLOUD_REACHABLE'
        VPN_OPEN = 'VPN_OPEN'
        SERIAL_ACTIVITY = 'SERIAL_ACTIVITY'

    def __init__(self, service, event_receiver=None, get_state=None):
        self._system_bus = dbus.SystemBus()
        dbus.service.Object.__init__(self, dbus.service.BusName(DBusService.BUS.format(service), self._system_bus), DBusService.PATH.format(service))

        self._get_state = get_state
        if event_receiver is not None:
            self._event_receiver = event_receiver
            self._system_bus.add_signal_receiver(self._process_event, dbus_interface=DBusService.INTERFACE.format('events'))

    @dbus.service.signal(INTERFACE.format('events'), signature='ss')
    def _send_event(self, event, json_payload):
        """ The signal is emitted when this method exists """
        pass

    def send_event(self, event, payload):
        return self._send_event(event, json.dumps(payload))

    def _process_event(self, event, json_payload):
        return self._event_receiver(event, json.loads(json_payload))

    @dbus.service.method(INTERFACE.format('state'), in_signature='', out_signature='s')
    def _request_state(self):
        """
        Gets the service's state
        """
        if self._get_state is not None:
            return json.dumps(self._get_state())

    def get_state(self, service, default=None):
        try:
            service_bus = self._system_bus.get_object(DBusService.BUS.format(service), DBusService.PATH.format(service))
        except Exception:
            return default
        data = service_bus._request_state(dbus_interface=DBusService.INTERFACE.format('state'))
        if data is None:
            return default
        return json.loads(data)
