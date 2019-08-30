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
Module to communicate with the uCANs.
"""

import logging
from Queue import Queue, Empty
from wiring import provides, inject, SingletonScope, scope
from master_aio.aio_api import AIOAPI
from master_aio.ucan_command import UCANCommandSpec
from master_aio.aio_communicator import BackgroundConsumer
from serial_utils import CommunicationTimedOutException

LOGGER = logging.getLogger('openmotics')


class UCANCommunicator(object):
    """
    Uses a AIOCommunicator to communicate with uCANs
    """

    # TODO: Handle variable-length payloads for bootloading purposes

    @provides('ucan_communicator')
    @scope(SingletonScope)
    @inject(aio_communicator='master_communicator')
    def __init__(self, aio_communicator, verbose=True):
        """
        :param aio_communicator: AIOCommunicator
        :type aio_communicator: master_aio.aio_communicator.AIOCommunicator
        :param verbose: Log all communication
        :type verbose: boolean.
        """
        self._verbose = verbose
        self._communicator = aio_communicator
        self._read_buffer = []
        self._consumers = {}

        self._background_consumer = BackgroundConsumer(AIOAPI.ucan_transport_message(), 1, self._process_transport_message)
        self._communicator.register_consumer(self._background_consumer)

    def register_consumer(self, consumer):
        """
        Register a consumer
        :param consumer: The consumer to register.
        :type consumer: Consumer or BackgroundConsumer.
        """
        self._consumers.setdefault(consumer.cc_address, []).append(consumer)

    def unregister_consumer(self, consumer):
        """
        Unregister a consumer
        :param consumer: The consumer to register.
        :type consumer: Consumer or BackgroundConsumer.
        """
        consumers = self._consumers.get(consumer.cc_address, [])
        if consumer in consumers:
            consumers.remove(consumer)

    def do_command(self, cc_address, command, identifier, fields, timeout=2):
        """
        Send a uCAN command over the Communicator and block until an answer is received.
        If the AIO does not respond within the timeout period, a CommunicationTimedOutException is raised

        :param cc_address: An address of the CC connected to the uCAN
        :type cc_address: str
        :param command: specification of the command to execute
        :type command: master_aio.ucan_command.UCANCommandSpec
        :param identifier: The identifier
        :type identifier: str
        :param fields: A dictionary with the command input field values
        :type fields dict
        :param timeout: maximum allowed time before a CommunicationTimedOutException is raised
        :type timeout: int
        :raises: serial_utils.CommunicationTimedOutException
        :returns: dict containing the output fields of the command
        """
        command.fill_headers(identifier)

        payload = command.create_request_payload(identifier, fields)
        payload.append(UCANCommandSpec.calculate_crc(payload))
        payload_bytes = len(payload)
        payload += [0] * (8 - payload_bytes)

        consumer = Consumer(cc_address, command)

        if self._verbose:
            LOGGER.info('Writing to uCAN transport ({0}):   {1}'.format(cc_address, payload))

        self.register_consumer(consumer)
        self._communicator.send_command(1, AIOAPI.ucan_transport_message(), {'cc_address': cc_address,
                                                                             'nr_can_bytes': payload_bytes,
                                                                             'sid': 5,
                                                                             'payload': payload})

        consumer.check_send_only()
        return consumer.get(timeout)

    def _process_transport_message(self, package):
        payload = package['payload']
        cc_address = package['cc_address']
        if self._verbose:
            LOGGER.info('Reading from uCAN transport ({0}): {1}'.format(cc_address, payload))

        consumers = self._consumers.get(cc_address, [])
        for consumer in consumers[:]:
            if consumer.suggest_payload(payload):
                self.unregister_consumer(consumer)


class Consumer(object):
    """
    A consumer is registered to the read thread before a command is issued.  If an output
    matches the consumer, the output will unblock the get() caller.
    """

    def __init__(self, cc_address, command):
        self.cc_address = cc_address
        self.command = command
        self._queue = Queue()
        self._payload_set = {}

    def suggest_payload(self, payload):
        """ Consume payload if needed """
        payload_hash = self.command.extract_hash(payload)
        if payload_hash in self.command.headers:
            self._payload_set[payload_hash] = payload
        if len(self._payload_set) == len(self.command.headers):
            self._queue.put(self.command.consume_response_payload(self._payload_set))
            return True
        return False

    def check_send_only(self):
        if len(self.command.response_instructions) == 0:
            self._queue.put(None)

    def get(self, timeout):
        """
        Wait until the uCAN (or CC) replies or the timeout expires.

        :param timeout: timeout in seconds
        :raises: :class`CommunicationTimedOutException` if AIO did not respond in time
        :returns: dict containing the output fields of the command
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            raise CommunicationTimedOutException()

    def __str__(self):
        return 'Communicator(\'{0}\', {1})'.format(self.cc_address, self.command.instruction.instruction)

    def __repr__(self):
        return str(self)
