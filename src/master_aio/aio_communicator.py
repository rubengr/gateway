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
Module to communicate with the AIO.

"""

import logging
import time
from threading import Thread, Lock
from Queue import Queue, Empty
from master_aio.aio_api import AIOAPI
from master_aio.fields import WordField
from serial_utils import CommunicationTimedOutException, printable

LOGGER = logging.getLogger('openmotics')


class AIOCommunicator(object):
    """
    Uses a serial port to communicate with the AIO and updates the output state.
    Provides methods to send AIOCommands.
    """

    # TODO: Use the length of the below constants instead of hardcoding e.g. 3 or 8, ...

    # Message constants. There are here for better code readability, no not change them without checking the other code.
    START_OF_REQUEST = 'STR'
    END_OF_REQUEST = '\r\n\r\n'
    START_OF_REPLY = 'RTR'
    END_OF_REPLY = '\r\n'

    def __init__(self, serial, verbose=False):
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

        self._read_thread = Thread(target=self._read, name='AIOCommunicator read thread')
        self._read_thread.setDaemon(True)

        self._communication_stats = {'calls_succeeded': [],
                                     'calls_timedout': [],
                                     'bytes_written': 0,
                                     'bytes_read': 0}
        self._debug_buffer = {'read': {},
                              'write': {}}
        self._debug_buffer_duration = 300

    def start(self):
        """ Start the AIOComunicator, this starts the background read thread. """
        self._stop = False
        self._read_thread.start()

    def get_bytes_written(self):
        """ Get the number of bytes written to the AIO. """
        return self._serial_bytes_written

    def get_bytes_read(self):
        """ Get the number of bytes read from the AIO. """
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
        with self._cid_lock:
            if self._cid is None:
                cid = 2
            else:
                cid = self._cid + 1
            while cid != self._cid and cid in self._cids_in_use:
                cid += 1
                if cid == 256:
                    cid = 2
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
                LOGGER.info('Writing to AIO serial:   {0}'.format(printable(data)))

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
        Sends a basic action to the AIO with the given action type and action number
        :param action_type: The action type to execute
        :type action_type: int
        :param action: The action number to execute
        :type action: int
        :param device_nr: Device number
        :type device_nr: int
        :param extra_parameter: Optional extra argument
        :type extra_parameter: int
        :raises: :class`CommunicationTimedOutException` if AIO did not respond in time
        :returns: dict containing the output fields of the command
        """
        LOGGER.info('BA: Execute {0} {1} {2} {3}'.format(action_type, action, device_nr, extra_parameter))
        return self.do_command(
            AIOAPI.basic_action(),
            {'type': action_type,
             'action': action,
             'device_nr': device_nr,
             'extra_parameter': extra_parameter}
        )

    def do_command(self, command, fields, timeout=2):
        """
        Send a command over the serial port and block until an answer is received.
        If the AIO does not respond within the timeout period, a CommunicationTimedOutException is raised

        :param command: specification of the command to execute
        :type command: master_aio.aio_command.AIOCommandSpec
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
        self.send_command(cid, command, fields)

        try:
            result = None
            if isinstance(consumer, Consumer):
                result = consumer.get(timeout)
            self._last_success = time.time()
            self._communication_stats['calls_succeeded'].append(time.time())
            self._communication_stats['calls_succeeded'] = self._communication_stats['calls_succeeded'][-50:]
            return result
        except CommunicationTimedOutException:
            self._communication_stats['calls_timedout'].append(time.time())
            self._communication_stats['calls_timedout'] = self._communication_stats['calls_timedout'][-50:]
            raise

    def send_command(self, cid, command, fields):
        """
        Send a command over the serial port and block until an answer is received.
        If the AIO does not respond within the timeout period, a CommunicationTimedOutException is raised

        :param cid: The command ID
        :type cid: int
        :param command: The AIO CommandSpec
        :type command: master_aio.aio_command.AIOCommandSpec
        :param fields: A dictionary with the command input field values
        :type fields dict
        :raises: serial_utils.CommunicationTimedOutException
        """

        payload = command.create_request_payload(fields)

        checked_payload = (str(chr(cid)) +
                           command.instruction +
                           WordField.encode(len(payload)) +
                           payload)

        data = (AIOCommunicator.START_OF_REQUEST +
                str(chr(cid)) +
                command.instruction +
                WordField.encode(len(payload)) +
                payload +
                'C' +
                str(chr(AIOCommunicator._calculate_crc(checked_payload))) +
                AIOCommunicator.END_OF_REQUEST)

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

        while not self._stop:

            # Read what's now on the buffer
            num_bytes = self._serial.inWaiting()
            if num_bytes > 0:
                data += self._serial.read(num_bytes)

            # Update counters
            self._serial_bytes_read += num_bytes
            self._communication_stats['bytes_read'] += num_bytes

            # Wait for a speicific number of bytes, or the minimum of 8
            if (wait_for_length is None and len(data) < 8) or len(data) < wait_for_length:
                continue

            # Check if the data contains the START_OF_REPLY
            if AIOCommunicator.START_OF_REPLY not in data:
                continue

            if wait_for_length is None:
                # Flush everything before the START_OF_REPLY
                data = AIOCommunicator.START_OF_REPLY + data.split(AIOCommunicator.START_OF_REPLY, 1)[-1]
                if len(data) < 8:
                    continue  # Not enough data

            cid = ord(data[3])
            command = data[4:6]
            header = data[:6]
            length = ord(data[6]) * 256 + ord(data[7])
            message_length = length + 8 + 4  # `length` payload, 8 header, 4 footer

            # If not all data is present, wait for more data
            if len(data) < message_length:
                wait_for_length = message_length
                continue

            message = data[:message_length]
            data = data[message_length:]

            # A possible message is received, log where appropriate
            if self._verbose:
                LOGGER.info('Reading from AIO serial: {0}'.format(printable(message)))
            threshold = time.time() - self._debug_buffer_duration
            self._debug_buffer['read'][time.time()] = printable(message)
            for t in self._debug_buffer['read'].keys():
                if t < threshold:
                    del self._debug_buffer['read'][t]

            # Validate message boundaries
            correct_boundaries = message.startswith(AIOCommunicator.START_OF_REPLY) and message.endswith(AIOCommunicator.END_OF_REPLY)
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
            expected_crc = AIOCommunicator._calculate_crc(checked_payload)
            if crc != expected_crc:
                LOGGER.info('Unexpected CRC ({0} vs expected {1}): {2}'.format(crc, expected_crc, printable(checked_payload)))
                # Reset, so we'll wait for the next RTR
                wait_for_length = None
                data = message[3:] + data  # Strip the START_OF_REPLY, and restore full data
                continue

            # A valid message is received, reliver it to the correct consumer
            consumers = self._consumers.get(header, [])
            for consumer in consumers[:]:
                if self._verbose:
                    LOGGER.info('Delivering payload to consumer {0}.{1}: {2}'.format(command, cid, printable(payload)))
                consumer.consume(payload)
                if isinstance(consumer, Consumer):
                    self.unregister_consumer(consumer)

            # Message processed, cleaning up
            wait_for_length = None


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
        """ Get the prefix of the answer from the AIO. """
        return 'RTR' + str(chr(self.cid)) + self.command.response_instruction

    def consume(self, payload):
        """ Consume payload. """
        data = self.command.consume_response_payload(payload)
        self._queue.put(data)

    def get(self, timeout):
        """
        Wait until the AIO replies or the timeout expires.

        :param timeout: timeout in seconds
        :raises: :class`CommunicationTimedOutException` if AIO did not respond in time
        :returns: dict containing the output fields of the command
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            raise CommunicationTimedOutException()


class BackgroundConsumer(object):
    """
    A consumer that runs in the background. The BackgroundConsumer does not provide get()
    but does a callback to a function whenever a message was consumed.
    """

    def __init__(self, command, cid, callback):
        """
        Create a background consumer using a cmd, cid and callback.

        :param command: the AIOCommand to consume.
        :param cid: the communication id.
        :param callback: function to call when an instance was found.
        """
        self.cid = cid
        self.command = command
        self._callback = callback
        self._queue = Queue()

        self._callback_thread = Thread(target=self.deliver, name='AIOCommunicator BackgroundConsumer delivery thread')
        self._callback_thread.setDaemon(True)
        self._callback_thread.start()

    def get_header(self):
        """ Get the prefix of the answer from the AIO. """
        return 'RTR' + str(chr(self.cid)) + self.command.response_instruction

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
