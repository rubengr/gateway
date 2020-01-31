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

from platform_utils import System
System.import_libs()

import sys
import logging
import constants
from ConfigParser import ConfigParser
from serial import Serial
from ioc import Injectable
from master_core.core_updater import CoreUpdater

logger = logging.getLogger("openmotics")


def setup_logger():
    """ Setup the OpenMotics logger. """

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage:')
        print('{0} firmware_filename'.format(sys.argv[0]))
        sys.exit(1)
    firmware_filename = sys.argv[1]

    config = ConfigParser()
    config.read(constants.get_config_file())
    core_cli_serial_port = config.get('OpenMotics', 'cli_serial')
    Injectable.value(cli_serial=Serial(core_cli_serial_port, 115200))
    Injectable.value(core_communicator=None)
    Injectable.value(maintenance_communicator=None)

    setup_logger()
    CoreUpdater.update(hex_filename=firmware_filename)
