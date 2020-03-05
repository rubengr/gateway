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
import time

import pytest

logger = logging.getLogger('openmotics')


@pytest.fixture
def power_on(request, toolbox):
    yield
    toolbox.ensure_power_on()


@pytest.mark.slow
@pytest.mark.skip(reason='makes other tests unreliable')
def test_power_cycle(toolbox, power_on):
    toolbox.power_cycle()


@pytest.fixture
def discover_mode(request, toolbox):
    yield
    toolbox.target.get('/module_discover_stop')


@pytest.mark.slow
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
