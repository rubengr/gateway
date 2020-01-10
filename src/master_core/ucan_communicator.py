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
Module to communicate with the uCANs.
"""

import logging
import time
from Queue import Queue, Empty
from ioc import Injectable, Inject, INJECTED, Singleton
from master_core.core_api import CoreAPI
from master_core.core_communicator import BackgroundConsumer
from master_core.exceptions import BootloadingException
from master_core.ucan_command import SID
from master_core.ucan_api import UCANAPI
from serial_utils import CommunicationTimedOutException, printable

logger = logging.getLogger('openmotics')


@Injectable.named('ucan_communicator')
@Singleton
class UCANCommunicator(object):
    """
    Uses a CoreCommunicator to communicate with uCANs
    """

    @Inject
    def __init__(self, master_communicator=INJECTED, ucan_communicator_verbose=INJECTED):
        """
        :param master_communicator: CoreCommunicator
        :type master_communicator: master_core.core_communicator.CoreCommunicator
        :param ucan_communicator_verbose: Log all communication
        :type ucan_communicator_verbose: boolean.
        """
        self._verbose = ucan_communicator_verbose
        self._communicator = master_communicator
        self._read_buffer = []
        self._consumers = {}
        self._cc_pallet_mode = {}

        self._background_consumer = BackgroundConsumer(CoreAPI.ucan_rx_transport_message(), 1, self._process_transport_message)
        self._communicator.register_consumer(self._background_consumer)

    def is_ucan_in_bootloader(self, cc_address, ucan_address):
        """
        Figures out whether a uCAN is in bootloader or application mode. This can be a rather slow call since it might rely on a communication timeout
        :param cc_address: The address of the CAN Control
        :param ucan_address:  The address of the uCAN
        :return: Boolean, indicating whether the uCAN is in bootloader or not
        """
        try:
            self.do_command(cc_address, UCANAPI.ping(SID.NORMAL_COMMAND), ucan_address, {'data': 1})
            return False
        except CommunicationTimedOutException:
            self.do_command(cc_address, UCANAPI.ping(SID.BOOTLOADER_COMMAND), ucan_address, {'data': 1})
            return True

    def register_consumer(self, consumer):
        """
        Register a consumer
        :param consumer: The consumer to register.
        :type consumer: Consumer or PalletConsumer.
        """
        self._consumers.setdefault(consumer.cc_address, []).append(consumer)

    def unregister_consumer(self, consumer):
        """
        Unregister a consumer
        :param consumer: The consumer to register.
        :type consumer: Consumer or PalletConsumer.
        """
        consumers = self._consumers.get(consumer.cc_address, [])
        if consumer in consumers:
            consumers.remove(consumer)

    def do_command(self, cc_address, command, identity, fields, timeout=2):
        """
        Send a uCAN command over the Communicator and block until an answer is received.
        If the Core does not respond within the timeout period, a CommunicationTimedOutException is raised

        :param cc_address: An address of the CC connected to the uCAN
        :type cc_address: str
        :param command: specification of the command to execute
        :type command: master_core.ucan_command.UCANCommandSpec
        :param identity: The identity
        :type identity: str
        :param fields: A dictionary with the command input field values
        :type fields dict
        :param timeout: maximum allowed time before a CommunicationTimedOutException is raised
        :type timeout: int or None
        :raises: serial_utils.CommunicationTimedOutException
        :returns: dict containing the output fields of the command
        """
        if self._cc_pallet_mode.get(cc_address, False) is True:
            raise BootloadingException('CC {0} is currently bootloading'.format(cc_address))

        command.set_identity(identity)

        if command.sid == SID.BOOTLOADER_PALLET:
            consumer = PalletConsumer(cc_address, command, self._release_pallet_mode)
            self._cc_pallet_mode[cc_address] = True
        else:
            consumer = Consumer(cc_address, command)
        self.register_consumer(consumer)

        master_timeout = False
        for payload in command.create_request_payloads(identity, fields):
            if self._verbose:
                logger.info('Writing to uCAN transport:   CC {0} - SID {1} - Data: {2}'.format(cc_address, command.sid, printable(payload)))
            try:
                self._communicator.do_command(command=CoreAPI.ucan_tx_transport_message(),
                                              fields={'cc_address': cc_address,
                                                      'nr_can_bytes': len(payload),
                                                      'sid': command.sid,
                                                      'payload': payload + [0] * (8 - len(payload))},
                                              timeout=timeout)
            except CommunicationTimedOutException as ex:
                logger.error('Internal timeout during uCAN transport to CC {0}: {1}'.format(cc_address, ex))
                master_timeout = True
                break

        consumer.check_send_only()
        if master_timeout:
            # When there's a communication timeout with the master, catch this exception and timeout the consumer
            # so it uses a flow expected by the caller
            return consumer.get(0)
        if timeout is not None:
            return consumer.get(timeout)

    def _release_pallet_mode(self, cc_address):
        print('Releasing pallet mode for {0}'.format(cc_address))
        self._cc_pallet_mode[cc_address] = False

    def _process_transport_message(self, package):
        payload_length = package['nr_can_bytes']
        payload = package['payload'][:payload_length]
        sid = package['sid']
        cc_address = package['cc_address']
        if self._verbose:
            logger.info('Reading from uCAN transport: CC {0} - SID {1} - Data: {2}'.format(cc_address, sid, printable(payload)))

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
        :raises: :class`CommunicationTimedOutException` if Core did not respond in time
        :returns: dict containing the output fields of the command
        """
        try:
            value = self._queue.get(timeout=timeout)
            if value is None:
                # No valid data could be received
                raise CommunicationTimedOutException('Empty or invalid uCAN data received')
            return value
        except Empty:
            raise CommunicationTimedOutException('No uCAN data received in {0}s'.format(timeout))

    def __str__(self):
        return 'Communicator(\'{0}\', {1})'.format(self.cc_address, self.command.instruction.instruction)

    def __repr__(self):
        return str(self)


class PalletConsumer(Consumer):
    """
    A pallet consumer is registered to the read thread before a command is issued.  If an output
    matches the consumer, the output will unblock the get() caller.
    """

    def __init__(self, cc_address, command, finished_callback):
        super(PalletConsumer, self).__init__(cc_address=cc_address,
                                             command=command)
        self._amount_of_segments = None
        self._finished_callback = finished_callback

    def suggest_payload(self, payload):
        """ Consume payload if needed """
        header = payload[0]
        first_segment = bool(header >> 7 & 1)
        segments_remaining = header & 127
        if first_segment:
            self._amount_of_segments = segments_remaining + 1
        segment_data = payload[1:]
        self._payload_set[segments_remaining] = segment_data
        if self._amount_of_segments is not None and sorted(self._payload_set.keys()) == range(self._amount_of_segments):
            pallet = []
            for segment in sorted(self._payload_set.keys(), reverse=True):
                pallet += self._payload_set[segment]
            self._queue.put(self.command.consume_response_payload(pallet))
            return True
        return False

    def get(self, timeout):
        try:
            return super(PalletConsumer, self).get(timeout=timeout)
        finally:
            self._finished_callback(self.cc_address)

    def check_send_only(self):
        pass

    def __str__(self):
        return 'PalletsConsumer(\'{0}\')'.format(self.cc_address)
