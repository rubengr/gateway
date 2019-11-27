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
Module to communicate with the Core.

"""

import logging
import time
from threading import Thread, Lock
from Queue import Queue, Empty
from wiring import provides, inject, SingletonScope, scope
from master_core.core_api import CoreAPI
from master_core.fields import WordField
from serial_utils import CommunicationTimedOutException, printable

LOGGER = logging.getLogger('openmotics')


class CoreCommunicator(object):
    """
    Uses a serial port to communicate with the Core and updates the output state.
    Provides methods to send CoreCommands.
    """

    # Message constants. There are here for better code readability, you can't just simply change them
    START_OF_REQUEST = 'STR'
    END_OF_REQUEST = '\r\n\r\n'
    START_OF_REPLY = 'RTR'
    END_OF_REPLY = '\r\n'

    @provides('master_core_communicator')
    @scope(SingletonScope)
    @inject(serial='controller_serial', verbose='core_communicator_verbose')
    def __init__(self, serial, verbose):
        """
        :param serial: Serial port to communicate with
        :type serial: serial.Serial
        :param verbose: Log all serial communication
        :type verbose: boolean.
        """
        self._verbose = verbose

        self._serial = serial
        self._serial_write_lock = Lock()
        self._cid_lock = Lock()
        self._serial_bytes_written = 0
        self._serial_bytes_read = 0

        self._cid = None  # Reserved CIDs: 0, 1
        self._cids_in_use = set()
        self._consumers = {}
        self._last_success = 0
        self._stop = False

        self._read_thread = Thread(target=self._read, name='CoreCommunicator read thread')
        self._read_thread.setDaemon(True)

        self._communication_stats = {'calls_succeeded': [],
                                     'calls_timedout': [],
                                     'bytes_written': 0,
                                     'bytes_read': 0}
        self._debug_buffer = {'read': {},
                              'write': {}}
        self._debug_buffer_duration = 300

    def start(self):
        """ Start the CoreComunicator, this starts the background read thread. """
        self._stop = False
        self._read_thread.start()

    def get_bytes_written(self):
        """ Get the number of bytes written to the Core. """
        return self._serial_bytes_written

    def get_bytes_read(self):
        """ Get the number of bytes read from the Core. """
        return self._serial_bytes_read

    def get_communication_statistics(self):
        return self._communication_stats

    def get_debug_buffer(self):
        return self._debug_buffer

    def get_seconds_since_last_success(self):
        """ Get the number of seconds since the last successful communication. """
        if self._last_success == 0:
            return 0  # No communication - return 0 sec since last success
        else:
            return time.time() - self._last_success

    def _get_cid(self):
        """ Get a communication id. 0 and 1 are reserved. """
        def _increment_cid(current_cid):
            if current_cid is None:
                new_cid = 2
            else:
                new_cid = current_cid + 1
            if new_cid == 256:
                new_cid = 2
            return new_cid

        def _available(candidate_cid):
            if candidate_cid is None:
                return False
            if candidate_cid == self._cid:
                return False
            if candidate_cid in self._cids_in_use:
                return False
            return True

        with self._cid_lock:
            cid = self._cid  # Initial value
            while not _available(cid):
                cid = _increment_cid(cid)
                if cid == self._cid:
                    # Seems there is no CID available at this moment
                    raise RuntimeError('No available CID')
            self._cid = cid
            self._cids_in_use.add(cid)
            return cid

    def _write_to_serial(self, data):
        """
        Write data to the serial port.

        :param data: the data to write
        :type data: string
        """
        with self._serial_write_lock:
            if self._verbose:
                LOGGER.info('Writing to Core serial:   {0}'.format(printable(data)))

            threshold = time.time() - self._debug_buffer_duration
            self._debug_buffer['write'][time.time()] = printable(data)
            for t in self._debug_buffer['write'].keys():
                if t < threshold:
                    del self._debug_buffer['write'][t]

            self._serial.write(data)
            self._serial_bytes_written += len(data)
            self._communication_stats['bytes_written'] += len(data)

    def register_consumer(self, consumer):
        """
        Register a consumer
        :param consumer: The consumer to register.
        :type consumer: Consumer or BackgroundConsumer.
        """
        self._consumers.setdefault(consumer.get_header(), []).append(consumer)

    def unregister_consumer(self, consumer):
        """
        Unregister a consumer
        :param consumer: The consumer to register.
        :type consumer: Consumer or BackgroundConsumer.
        """
        consumers = self._consumers.get(consumer.get_header(), [])
        if consumer in consumers:
            consumers.remove(consumer)
        with self._cid_lock:
            self._cids_in_use.discard(consumer.cid)

    def do_basic_action(self, action_type, action, device_nr, extra_parameter=0):
        """
        Sends a basic action to the Core with the given action type and action number
        :param action_type: The action type to execute
        :type action_type: int
        :param action: The action number to execute
        :type action: int
        :param device_nr: Device number
        :type device_nr: int
        :param extra_parameter: Optional extra argument
        :type extra_parameter: int
        :raises: :class`CommunicationTimedOutException` if Core did not respond in time
        :returns: dict containing the output fields of the command
        """
        LOGGER.info('BA: Execute {0} {1} {2} {3}'.format(action_type, action, device_nr, extra_parameter))
        return self.do_command(
            CoreAPI.basic_action(),
            {'type': action_type,
             'action': action,
             'device_nr': device_nr,
             'extra_parameter': extra_parameter}
        )

    def do_command(self, command, fields, timeout=2):
        """
        Send a command over the serial port and block until an answer is received.
        If the Core does not respond within the timeout period, a CommunicationTimedOutException is raised

        :param command: specification of the command to execute
        :type command: master_core.core_command.CoreCommandSpec
        :param fields: A dictionary with the command input field values
        :type fields dict
        :param timeout: maximum allowed time before a CommunicationTimedOutException is raised
        :type timeout: int
        :raises: serial_utils.CommunicationTimedOutException
        :returns: dict containing the output fields of the command
        """
        cid = self._get_cid()
        consumer = Consumer(command, cid)
        command = consumer.command

        self._consumers.setdefault(consumer.get_header(), []).append(consumer)
        self._send_command(cid, command, fields)

        try:
            result = None
            if isinstance(consumer, Consumer) and timeout is not None:
                result = consumer.get(timeout)
            self._last_success = time.time()
            self._communication_stats['calls_succeeded'].append(time.time())
            self._communication_stats['calls_succeeded'] = self._communication_stats['calls_succeeded'][-50:]
            return result
        except CommunicationTimedOutException:
            self._communication_stats['calls_timedout'].append(time.time())
            self._communication_stats['calls_timedout'] = self._communication_stats['calls_timedout'][-50:]
            raise

    def _send_command(self, cid, command, fields):
        """
        Send a command over the serial port

        :param cid: The command ID
        :type cid: int
        :param command: The Core CommandSpec
        :type command: master_core.core_command.CoreCommandSpec
        :param fields: A dictionary with the command input field values
        :type fields dict
        :raises: serial_utils.CommunicationTimedOutException
        """

        payload = command.create_request_payload(fields)

        checked_payload = (str(chr(cid)) +
                           command.instruction +
                           WordField.encode(len(payload)) +
                           payload)

        data = (CoreCommunicator.START_OF_REQUEST +
                str(chr(cid)) +
                command.instruction +
                WordField.encode(len(payload)) +
                payload +
                'C' +
                str(chr(CoreCommunicator._calculate_crc(checked_payload))) +
                CoreCommunicator.END_OF_REQUEST)

        self._write_to_serial(data)

    @staticmethod
    def _calculate_crc(data):
        """
        Calculate the CRC of the data.

        :param data: Data for which to calculate the CRC
        :returns: CRC
        """
        crc = 0
        for byte in data:
            crc += ord(byte)
        return crc % 256

    def _read(self):
        """
        Code for the background read thread: reads from the serial port and forward certain messages to waiting
        consumers

        Request format: 'STR' + {CID, 1 byte} + {command, 2 bytes} + {length, 2 bytes} + {payload, `length` bytes} + 'C' + {checksum, 1 byte} + '\r\n\r\n'
        Response format: 'RTR' + {CID, 1 byte} + {command, 2 bytes} + {length, 2 bytes} + {payload, `length` bytes} + 'C' + {checksum, 1 byte} + '\r\n'

        """
        data = ''
        wait_for_length = None
        header_length = len(CoreCommunicator.START_OF_REPLY) + 1 + 2 + 2  # RTR + CID (1 byte) + command (2 bytes) + length (2 bytes)
        footer_length = 1 + 1 + len(CoreCommunicator.END_OF_REPLY)  # 'C' + checksum (1 byte) + \r\n

        while not self._stop:

            # Read what's now on the buffer
            num_bytes = self._serial.inWaiting()
            if num_bytes > 0:
                data += self._serial.read(num_bytes)

            # Update counters
            self._serial_bytes_read += num_bytes
            self._communication_stats['bytes_read'] += num_bytes

            # Wait for a speicific number of bytes, or the header length
            if (wait_for_length is None and len(data) < header_length) or len(data) < wait_for_length:
                continue

            # Check if the data contains the START_OF_REPLY
            if CoreCommunicator.START_OF_REPLY not in data:
                continue

            if wait_for_length is None:
                # Flush everything before the START_OF_REPLY
                data = CoreCommunicator.START_OF_REPLY + data.split(CoreCommunicator.START_OF_REPLY, 1)[-1]
                if len(data) < header_length:
                    continue  # Not enough data

            header_fields = CoreCommunicator._parse_header(data)
            message_length = header_fields['length'] + header_length + footer_length

            # If not all data is present, wait for more data
            if len(data) < message_length:
                wait_for_length = message_length
                continue

            message = data[:message_length]
            data = data[message_length:]

            # A possible message is received, log where appropriate
            if self._verbose:
                LOGGER.info('Reading from Core serial: {0}'.format(printable(message)))
            threshold = time.time() - self._debug_buffer_duration
            self._debug_buffer['read'][time.time()] = printable(message)
            for t in self._debug_buffer['read'].keys():
                if t < threshold:
                    del self._debug_buffer['read'][t]

            # Validate message boundaries
            correct_boundaries = message.startswith(CoreCommunicator.START_OF_REPLY) and message.endswith(CoreCommunicator.END_OF_REPLY)
            if not correct_boundaries:
                LOGGER.info('Unexpected boundaries: {0}'.format(printable(message)))
                # Reset, so we'll wait for the next RTR
                wait_for_length = None
                data = message[3:] + data  # Strip the START_OF_REPLY, and restore full data
                continue

            # Validate message CRC
            crc = ord(message[-3])
            payload = message[8:-4]
            checked_payload = message[3:-4]
            expected_crc = CoreCommunicator._calculate_crc(checked_payload)
            if crc != expected_crc:
                LOGGER.info('Unexpected CRC ({0} vs expected {1}): {2}'.format(crc, expected_crc, printable(checked_payload)))
                # Reset, so we'll wait for the next RTR
                wait_for_length = None
                data = message[3:] + data  # Strip the START_OF_REPLY, and restore full data
                continue

            # A valid message is received, reliver it to the correct consumer
            consumers = self._consumers.get(header_fields['header'], [])
            for consumer in consumers[:]:
                if self._verbose:
                    LOGGER.info('Delivering payload to consumer {0}.{1}: {2}'.format(header_fields['command'], header_fields['cid'], printable(payload)))
                consumer.consume(payload)
                if isinstance(consumer, Consumer):
                    self.unregister_consumer(consumer)

            # Message processed, cleaning up
            wait_for_length = None

    @staticmethod
    def _parse_header(data):
        base = len(CoreCommunicator.START_OF_REPLY)
        return {'cid': ord(data[base]),
                'command': data[base + 1:base + 3],
                'header': data[:base + 3],
                'length': ord(data[base + 3]) * 256 + ord(data[base + 4])}


class Consumer(object):
    """
    A consumer is registered to the read thread before a command is issued.  If an output
    matches the consumer, the output will unblock the get() caller.
    """

    def __init__(self, command, cid):
        self.cid = cid
        self.command = command
        self._queue = Queue()

    def get_header(self):
        """ Get the prefix of the answer from the Core. """
        return CoreCommunicator.START_OF_REPLY + str(chr(self.cid)) + self.command.response_instruction

    def consume(self, payload):
        """ Consume payload. """
        data = self.command.consume_response_payload(payload)
        self._queue.put(data)

    def get(self, timeout):
        """
        Wait until the Core replies or the timeout expires.

        :param timeout: timeout in seconds
        :raises: :class`CommunicationTimedOutException` if Core did not respond in time
        :returns: dict containing the output fields of the command
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            raise CommunicationTimedOutException('No Core data received in {0}s'.format(timeout))


class BackgroundConsumer(object):
    """
    A consumer that runs in the background. The BackgroundConsumer does not provide get()
    but does a callback to a function whenever a message was consumed.
    """

    def __init__(self, command, cid, callback):
        """
        Create a background consumer using a cmd, cid and callback.

        :param command: the CoreCommand to consume.
        :param cid: the communication id.
        :param callback: function to call when an instance was found.
        """
        self.cid = cid
        self.command = command
        self._callback = callback
        self._queue = Queue()

        self._callback_thread = Thread(target=self.deliver, name='CoreCommunicator BackgroundConsumer delivery thread')
        self._callback_thread.setDaemon(True)
        self._callback_thread.start()

    def get_header(self):
        """ Get the prefix of the answer from the Core. """
        return CoreCommunicator.START_OF_REPLY + str(chr(self.cid)) + self.command.response_instruction

    def consume(self, payload):
        """ Consume payload. """
        data = self.command.consume_response_payload(payload)
        self._queue.put(data)

    def deliver(self):
        """ Deliver data to the callback functions. """
        while True:
            try:
                self._callback(self._queue.get())
            except Exception:
                LOGGER.exception('Unexpected exception delivering background consumer data')
                time.sleep(1)
