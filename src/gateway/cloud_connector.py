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
Cloud connector
"""
import os
import time
try:
    import json
except ImportError:
    import simplejson as json
import logging
from threading import Thread
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from platform_utils import Hardware, System

LOGGER = logging.getLogger('openmotics')


class CloudConnector(object):
    def __init__(self, uuid):
        """
        :param uuid: This gateway's UUID
        :type uuid: str
        """
        self._uuid = uuid
        self._client = None
        self._connected = False
        self._connected_trigger = False
        self._online = False
        self._online_trigger = False
        self._main_thread = None

    def start(self):
        self._client = AWSIoTMQTTClient(self._uuid)
        self._client.configureEndpoint('alk1hy8fq9lzp-ats.iot.eu-west-1.amazonaws.com', 8883)
        self._client.configureCredentials(CAFilePath=os.environ.get('REQUESTS_CA_BUNDLE', '/opt/openmotics/etc/aws/CA.crt'),
                                          KeyPath='/opt/openmotics/etc/aws/private.key',
                                          CertificatePath='/opt/openmotics/etc/aws/cert.pem')
        self._client.onOffline = self._report_offline
        self._client.onOnline = self._report_online

        self._main_thread = Thread(target=self._main_thread_worker)
        self._main_thread.setDaemon(True)
        self._main_thread.start()

    def _main_thread_worker(self):
        while True:
            if not self._connected:
                try:
                    LOGGER.info('AWS IoT: Connecting...')
                    self._client.connect()
                    self._connected_trigger = True
                    self._connected = True
                    LOGGER.info('AWS IoT: Connected')
                except Exception:
                    LOGGER.exception('AWS IoT: Could not connect')

            if self._connected_trigger:
                self._connected_trigger = False
                try:
                    LOGGER.info('AWS IoT: Subscribing...')
                    if self._client.subscribe('{0}/#'.format(self._uuid), 1, lambda *args, **kwargs: CloudConnector._parse_payload(*args, **kwargs)):
                        LOGGER.info('AWS IoT: Subscribed')
                    else:
                        LOGGER.error('AWS IoT: Got `False` when subscribing')
                except Exception:
                    LOGGER.exception('AWS IoT: Could not subscribe')

            if self._online_trigger:
                self._online_trigger = False
                try:
                    self._report_information()
                except Exception:
                    LOGGER.exception('AWS IoT: Could not report information')

            time.sleep(5)

    def report_event(self, event):
        data = event.serialize()
        topic = '{0}/events/{1}/{2}'.format(self._uuid, event.type.lower(), event.data['id'])
        payload = json.dumps(data)
        if self._connected:
            LOGGER.info('AWS IoT: Publishing to {0}...'.format(topic))
            self._client.publish(topic, payload, 1)
            LOGGER.info('AWS IoT: Published')

    def _report_information(self):
        topic = '{0}/information'.format(self._uuid)
        payload = json.dumps({'hardware': Hardware.get_board_type(),
                              'operating_system': {'ip_address': System.get_ip_address(),
                                                   'family': System.get_operating_system()}})
        LOGGER.info('AWS IoT: Reporting information to {0}...'.format(topic))
        self._client.publish(topic, payload, 1)
        LOGGER.info('AWS IoT: Reported')

    def _report_offline(self):
        _ = self
        LOGGER.info('AWS IoT: Offline')
        self._online = False

    def _report_online(self):
        LOGGER.info('AWS IoT: Online')
        self._online = True
        self._online_trigger = True

    @staticmethod
    def _parse_payload(client, userdata, message):
        _ = client, userdata
        for ignored_topic in ['/events', '/information']:
            if ignored_topic in message.topic:
                return
        data = json.loads(message.payload)
        LOGGER.info('AWS IoT: Got message on {0}: {1}'.format(message.topic, json.dumps(data)))
        return data
