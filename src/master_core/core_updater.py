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
Module to work update a Core
"""

import logging
import os
import time
from intelhex import IntelHex
from ioc import Inject, INJECTED

logger = logging.getLogger('openmotics')


class CoreUpdater(object):
    """
    This is a class holding tools to execute Core updates
    """

    BOOTLOADER_SERIAL_READ_TIMEOUT = 3

    @staticmethod
    @Inject
    def update(hex_filename, core_communicator=INJECTED, maintenance_communicator=INJECTED, cli_serial=INJECTED):
        """
        Flashes the content from an Intel HEX file to the Core
        :param hex_filename: The filename of the hex file to flash
        :type core_communicator: master_core.core_communicator.CoreCommunicator
        :type maintenance_communicator: master_core.maintenance.MaintenanceCommunicator
        :type cli_serial: serial.Serial
        """
        try:
            # TODO: Check version and skip update if the version is already active

            logger.info('Updating Core')

            maintenance_communicator.stop()
            # core_communicator.stop()  # TODO: Hold the communicator

            if not os.path.exists(hex_filename):
                raise RuntimeError('The given path does not point to an existing file')
            _ = IntelHex(hex_filename)  # Using the IntelHex library to validate content validity
            with open(hex_filename, 'r') as hex_file:
                hex_lines = hex_file.readlines()

            in_bootloader = False  # TODO: Figure out whether the BL is active
            if in_bootloader:
                logger.info('Bootloader active')
            else:
                logger.info('Bootloader not active, switching to bootloader')
                # TODO: Switch to bootloader
                in_bootloader = True
                if not in_bootloader:
                    raise RuntimeError('Could not enter bootloader')
                logger.info('Bootloader active')

            logger.info('Verify bootloader communications')  # TODO: Probably will be replaced by the above "in bootloader" check
            cli_serial.write('hi\n')
            response = CoreUpdater.read_line(cli_serial)
            if not response.startswith('hi;version='):
                raise RuntimeError('Unexpected bootloader resposne: {0}'.format(response))
            logger.info('Bootloader version {0}'.format(response.split('=')[-1]))

            logger.info('Flashing contents of {0}'.format(os.path.basename(hex_filename)))
            logger.info('Flashing...')
            amount_lines = len(hex_lines)
            for index, line in enumerate(hex_lines):
                cli_serial.write(line)
                response = CoreUpdater.read_line(cli_serial)
                if response.startswith('nok'):
                    raise RuntimeError('Unexpected NOK while flashing: {0}'.format(response))
                if not response.startswith('ok'):
                    raise RuntimeError('Unexpected answer while flashing: {0}'.format(response))
                if index % int(amount_lines / 10) == 0:
                    logger.debug('* {0}%'.format(int(index * 100 / amount_lines) + 1))
            logger.info('Flashing... Done')

            # TODO: Figure out how to jump back to application

            maintenance_communicator.start()
            # core_communicator.start()  # TODO: Make sure it can start again

            logger.info('Verify Core communication')
            # TODO: Execute call to load firmware version

            logger.info('Update completed')
            return True
        except Exception as ex:
            logger.error('Error flashing: {0}'.format(ex))
            return False

    @staticmethod
    def read_line(serial, verbose=True):
        timeout = time.time() + CoreUpdater.BOOTLOADER_SERIAL_READ_TIMEOUT
        line = ''
        while time.time() < timeout:
            if serial.inWaiting():
                char = serial.read(1)
                line += char
                if char == '\n':
                    if line[0] == '#' and verbose:
                        logger.debug('* Debug: {0}'.format(line.strip()))
                        line = ''
                    else:
                        return line.strip()
        raise RuntimeError('Timeout while communicating with Core bootloader')
