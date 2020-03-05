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
import logging
import socket
import ssl
import time

import psutil
import pytest

logger = logging.getLogger('openmotics')


def check_ip_range():
    # type: () -> bool
    addresses = ([x.address for x in xs if x.broadcast == '10.91.115.255'] for xs in psutil.net_if_addrs().values())
    return not sum(addresses, [])


@pytest.fixture
def power_on(request, toolbox):
    yield
    toolbox.ensure_power_on()


@pytest.fixture
def discover_mode(request, toolbox):
    yield
    toolbox.target.get('/module_discover_stop')


@pytest.mark.slow
@pytest.mark.skip(reason='makes other tests unreliable')
def test_power_cycle(toolbox, power_on):
    toolbox.power_cycle()


@pytest.mark.smoke
def test_module_discover(toolbox, discover_mode):
    logger.info('starting module discovery')
    toolbox.target.get('/module_discover_start')
    time.sleep(2)
    data = toolbox.target.get('/module_discover_status')
    assert data['running'] == True
    toolbox.target.get('/module_discover_stop')

    data = toolbox.target.get('/get_modules')
    assert 'inputs' in data
    assert 'I' in data['inputs']
    assert 'outputs' in data
    assert 'O' in data['outputs']


@pytest.mark.slow
@pytest.mark.skipif(check_ip_range(), reason='the maintenance ports are not accessible on jenkins')
def test_maintenance(toolbox):
    # TODO: ensure maintenance mode is disabled afterwards
    data = toolbox.target.get('/get_status')
    expected_version = 'F{} H{}'.format(data['version'], data['hw_version'])

    logger.info('starting maintenance')
    data = toolbox.target.get('/open_maintenance')
    assert 'port' in data

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)

    time.sleep(2)
    ssl_sock = ssl.wrap_socket(
        sock,
        ssl_version=ssl.PROTOCOL_SSLv23,
        do_handshake_on_connect=False,
        suppress_ragged_eofs=False
    )
    ssl_sock.connect((toolbox.target._host, data['port']))

    data = ''
    while data != 'OK':
        data = ssl_sock.recv(1024).strip()
        logger.debug('received data "{}"'.format(data))

    ssl_sock.send('firmware version\r\n')
    assert ssl_sock.recv(1024).strip() == 'firmware version'
    assert ssl_sock.recv(1024).strip() == expected_version
    ssl_sock.send('exit\r\n')
    ssl_sock.close()
