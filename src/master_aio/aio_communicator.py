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

import aio_api
from aio_command import Field, printable
from serial_utils import CommunicationTimedOutException

LOGGER = logging.getLogger('openmotics')


class AIOCommunicator(object):
    """
    Uses a serial port to communicate with the AIO and updates the output state.
    Provides methods to send AIOCommands.
    """

    # Message constants. There are here for better code readability, no not change them without checking the other code.
    START_OF_REPLY = 'RTR'
    END_OF_REPLY = '\r\n'

    def __init__(self, serial, verbose=False):
        """
        :param serial: Serial port to communicate with
        :type serial: Instance of :class`serial.Serial`
        :param verbose: Print all serial communication to stdout.
        :type verbose: boolean.
        """
        self.__verbose = verbose

        self.__serial = serial
        self.__serial_write_lock = Lock()
        self.__command_lock = Lock()
        self.__serial_bytes_written = 0
        self.__serial_bytes_read = 0

        self.__cid = 1
        self.__consumers = {}
        self.__last_success = 0
        self.__stop = False

        self.__read_thread = Thread(target=self.__read, name='AIOCommunicator read thread')
        self.__read_thread.daemon = True

        self.__communication_stats = {'calls_succeeded': [],
                                      'calls_timedout': [],
                                      'bytes_written': 0,
                                      'bytes_read': 0}
        self.__debug_buffer = {'read': {},
                               'write': {}}
        self.__debug_buffer_duration = 300

    def start(self):
        """ Start the AIOComunicator, this starts the background read thread. """
        self.__stop = False
        self.__read_thread.start()

    def get_bytes_written(self):
        """ Get the number of bytes written to the Master. """
        return self.__serial_bytes_written

    def get_bytes_read(self):
        """ Get the number of bytes read from the Master. """
        return self.__serial_bytes_read

    def get_communication_statistics(self):
        return self.__communication_stats

    def get_debug_buffer(self):
        return self.__debug_buffer

    def get_seconds_since_last_success(self):
        """ Get the number of seconds since the last successful communication. """
        if self.__last_success == 0:
            return 0  # No communication - return 0 sec since last success
        else:
            return time.time() - self.__last_success

    def __get_cid(self):
        """ Get a communication id """
        (ret, self.__cid) = (self.__cid, (self.__cid % 255) + 1)
        return ret

    def __write_to_serial(self, data):
        """
        Write data to the serial port.

        :param data: the data to write
        :type data: string
        """
        with self.__serial_write_lock:
            if self.__verbose:
                LOGGER.info('Writing to AIO serial:   {0}'.format(printable(data)))

            threshold = time.time() - self.__debug_buffer_duration
            self.__debug_buffer['write'][time.time()] = printable(data)
            for t in self.__debug_buffer['write'].keys():
                if t < threshold:
                    del self.__debug_buffer['write'][t]

            self.__serial.write(data)
            self.__serial_bytes_written += len(data)
            self.__communication_stats['bytes_written'] += len(data)

    def register_consumer(self, consumer):
        """
        Register a customer consumer with the communicator. An instance of :class`Consumer`
        will be removed when consumption is done. An instance of :class`BackgroundConsumer` stays
        active and is thus able to consume multiple messages.

        :param consumer: The consumer to register.
        :type consumer: Consumer or BackgroundConsumer.
        """
        self.__consumers.setdefault(consumer.get_header(), []).append(consumer)

    def do_basic_action(self, action_type, action, device_nr, extra_parameter=0):
        """
        Sends a basic action to the master with the given action type and action number
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
            aio_api.basic_action(),
            {'type': action_type,
             'action': action,
             'device_nr': device_nr,
             'extra_parameter': extra_parameter}
        )

    def do_command(self, cmd, fields=None, timeout=2, extended_crc=False):
        """
        Send a command over the serial port and block until an answer is received.
        If the AIO does not respond within the timeout period, a CommunicationTimedOutException is raised

        :param cmd: specification of the command to execute
        :type cmd: :class`AIOCommand.AIOCommandSpec`
        :param fields: A dictionary with the command input field values
        :type fields dict
        :param timeout: maximum allowed time before a CommunicationTimedOutException is raised
        :type timeout: int
        :raises: :class`CommunicationTimedOutException` if master did not respond in time
        :returns: dict containing the output fields of the command
        """
        if fields is None:
            fields = dict()

        with self.__command_lock:
            cid = self.__get_cid()
            consumer = Consumer(cmd, cid)
            request = cmd.create_input(cid, fields, extended_crc)

            self.__consumers.setdefault(consumer.get_header(), []).append(consumer)
            self.__write_to_serial(request)
            try:
                result = consumer.get(timeout).fields
                self.__last_success = time.time()
                self.__communication_stats['calls_succeeded'].append(time.time())
                self.__communication_stats['calls_succeeded'] = self.__communication_stats['calls_succeeded'][-50:]
                return result
            except CommunicationTimedOutException:
                self.__communication_stats['calls_timedout'].append(time.time())
                self.__communication_stats['calls_timedout'] = self.__communication_stats['calls_timedout'][-50:]
                raise

    @staticmethod
    def __calculate_crc(data):
        """
        Calculate the CRC of the data.

        :param data: Data for which to calculate the CRC
        :returns: CRC
        """
        crc = 0
        for byte in data:
            crc += ord(byte)
        return crc

    def __read(self):
        """
        Code for the background read thread: reads from the serial port and forward certain messages to waiting
        consumers
        """
        data = ''
        wait_for_length = None

        while not self.__stop:
            # Read what's now on the buffer
            data += self.__serial.read(1)
            num_bytes = self.__serial.inWaiting()
            if num_bytes > 0:
                data += self.__serial.read(num_bytes)

            # Update counters
            self.__serial_bytes_read += (1 + num_bytes)
            self.__communication_stats['bytes_read'] += (1 + num_bytes)

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
            length = ord(data[6]) * 255 + ord(data[7])
            message_length = length + 8 + 6  # `length` payload, 8 header, 6 footer

            # If not all data is present, wait for more data
            if len(data) < message_length:
                wait_for_length = message_length
                continue

            # A possible message is received, log where appropriate
            if self.__verbose:
                LOGGER.info('Reading from AIO serial: {0}'.format(printable(data)))
            threshold = time.time() - self.__debug_buffer_duration
            self.__debug_buffer['read'][time.time()] = printable(data)
            for t in self.__debug_buffer['read'].keys():
                if t < threshold:
                    del self.__debug_buffer['read'][t]

            # Validate message boundaries
            correct_boundaries = not data.startswith(AIOCommunicator.START_OF_REPLY) or not data.endswith(AIOCommunicator.END_OF_REPLY)
            if not correct_boundaries:
                # Reset, so we'll wait for the next RTR
                wait_for_length = None
                data = data[3:]  # Strip the START_OF_REPLY
                LOGGER.info('Unexpected boundaries: {0}'.format(printable(data)))
                continue

            # Validate message CRC
            payload = data[8:-6]
            crc = ord(data[-5])
            expected_crc = AIOCommunicator.__calculate_crc(payload)
            if crc != expected_crc:
                # Reset, so we'll wait for the next RTR
                wait_for_length = None
                data = data[3:]  # Strip the START_OF_REPLY
                LOGGER.info('Unexpected CRC ({0} vs expected {1}): {2}'.format(crc, expected_crc, printable(data)))
                continue

            # A valid message is received, reliver it to the correct consumer
            consumers = self.__consumers.get(header, [])
            for consumer in consumers:
                if self.__verbose:
                    LOGGER.info('Delivering payload to consumer {0}.{1}: {2}'.format(command, cid, printable(payload)))
                consumer.consume(payload)

            # Message processed, cleaning up
            data = ''
            wait_for_length = None


class Consumer(object):
    """
    A consumer is registered to the read thread before a command is issued.  If an output
    matches the consumer, the output will unblock the get() caller.
    """

    def __init__(self, cmd, cid):
        self.cmd = cmd
        self.cid = cid
        self.__queue = Queue()

    def get_header(self):
        """ Get the prefix of the answer from the AIO. """
        return 'RTR' + str(chr(self.cid)) + self.cmd.output_action

    def consume(self, data):
        """ Consume data. """
        return self.cmd.consume_output(data)

    def deliver(self, data):
        """ Deliver data to the thread waiting on get(). """
        self.__queue.put(data)

    def get(self, timeout):
        """
        Wait until the AIO replies or the timeout expires.

        :param timeout: timeout in seconds
        :raises: :class`CommunicationTimedOutException` if master did not respond in time
        :returns: dict containing the output fields of the command
        """
        try:
            return self.__queue.get(timeout=timeout)
        except Empty:
            raise CommunicationTimedOutException()


class BackgroundConsumer(object):
    """
    A consumer that runs in the background. The BackgroundConsumer does not provide get()
    but does a callback to a function whenever a message was consumed.
    """

    def __init__(self, cmd, cid, callback):
        """
        Create a background consumer using a cmd, cid and callback.

        :param cmd: the AIOCommand to consume.
        :param cid: the communication id.
        :param callback: function to call when an instance was found.
        """
        self.__cmd = cmd
        self.__cid = cid
        self.__callback = callback

    def get_header(self):
        """ Get the prefix of the answer from the AIO. """
        return 'RTR' + str(chr(self.__cid)) + self.__cmd.output_action

    def consume(self, data):
        """ Consume data. """
        return self.__cmd.consume_output(data)

    def deliver(self, data):
        """ Deliver data to the thread waiting on get(). """
        self.__callback(data)
