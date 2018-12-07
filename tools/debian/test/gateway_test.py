# Copyright (C) 2016 OpenMotics BVBA
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
Test if the required gpios are correctly exposed to userspace
"""

import os
import logging
import subprocess


class GWTEST(object):
    def __init__(self):
        self.warnings = 0
        self.errors = 0

    def test_gpios(self):
        """
        The main function contains the code to test if the gpios are exposed to user space
        and if that happened in time by checking of the led_service was able to set the POWER LED(60) high
        :return: boolean
        """
        result = True
        LOGGER.info('-- TEST GPIOS: Start --')
        for gpio_nr in GPIOS:
            if not os.path.isdir('/sys/class/gpio/gpio{0}'.format(gpio_nr)):
                LOGGER.error('GPIO{0} - NOT READY: Directory /sys/class/gpio/gpio{0} is missing'.format(gpio_nr))
                result = False
            if os.path.isfile('/sys/class/gpio/gpio{0}/value'.format(gpio_nr)):
                with open('/sys/class/gpio/gpio{0}/value'.format(gpio_nr)) as gpiofd:
                    status = gpiofd.read()
                    LOGGER.info('GPIO{0} - VALUE: {1}'.format(gpio_nr, status.strip()))
                    if gpio_nr == 60 and status == 0:
                        LOGGER.error('GPIO{0} - TOO LITTLE TOO LATE'.format(gpio_nr))
                        result = False
                        self.errors += 1
            else:
                LOGGER.error('GPIO{0} - NOT READY: File /sys/class/gpio/gpio{0}/value is missing'.format(gpio_nr))
        LOGGER.info('-- TEST GPIOS: End --')
        return result

    def test_services(self):
        """
        Test the gateway service status as reported by supervisor
        :return: boolean
        """
        result = True
        LOGGER.info('-- TEST SERVICE: Start --')
        output = subprocess.check_output(["supervisorctl", "status"]).splitlines()
        for line in output:
            service, status = line.split()[0:2]
            if status == 'RUNNING':
                LOGGER.info('SERVICE {0} is {1}'.format(service, status))
            else:
                LOGGER.error('SERVICE {0} is {1}'.format(service, status))
                result = False
                self.errors += 1
        LOGGER.info('-- TEST SERVICE: End --')
        return result

    def test_gateway_api(self):
        """
        Test the gateway api and underneath master communication
        gateway.get_errors()
        ? gateway.create_virtual_output()
        ? gateway.set_output()
        ? gateway.delete_virtual_output()
        :return: boolean
        """
        result = True
        LOGGER.info('-- TEST GATEWAY API: Start --')
        os.chdir('/opt/openmotics/python')
        from vpn_service import Gateway
        gateway = Gateway()
        errors = gateway.get_errors()
        if errors == None:
            LOGGER.error('GATEWAY - MASTER communication might be broken')
            result = False
            self.errors += 1
        elif errors['master_errors'] != 0:
            LOGGER.warning('GATEWAY - MASTER communication shows errors')
            self.warnings += 1
        else:
            LOGGER.info('GATEWAY - MASTER communication has no errors and looks ok')
        LOGGER.info('-- TEST GATEWAY API: End --')
        return result


if __name__ == '__main__':

    LOGGER = logging.getLogger("gateway_tests")
    LOGGER.setLevel(logging.DEBUG)
    fh = logging.FileHandler('/opt/log/gateway_tests.log')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s")
    fh.setFormatter(formatter)
    LOGGER.addHandler(fh)

    GPIOS = [26, 44, 48, 49, 60, 117]

    if not os.path.exists('/opt/log'):
        os.makedirs('/opt/log')

    gwtest = GWTEST()
    gpios_result = gwtest.test_gpios()
    services_result = gwtest.test_services()
    gateway_result = gwtest.test_gateway_api()

    LOGGER.info(' !!! TESTS COMPLETED with {0} warnings and {1} errors !!!'.format(gwtest.warnings, gwtest.errors))
