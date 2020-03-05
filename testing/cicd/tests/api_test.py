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
from datetime import datetime

import pytest
from pytz import timezone

logger = logging.getLogger('openmotics')


@pytest.mark.smoke
def test_health_check(toolbox):
    data = toolbox.target.get('/health_check')
    assert 'health' in data
    assert data['health']['led_service']['state']
    assert data['health']['vpn_service']['state']
    assert data['health']['openmotics']['state']


@pytest.mark.smoke
def test_features(toolbox):
    data = toolbox.target.get('/get_features')
    assert 'features' in data
    assert 'input_states' in data['features']


@pytest.mark.smoke
def test_version(toolbox):
    data = toolbox.target.get('/get_version')
    assert 'version' in data
    assert 'gateway' in data


@pytest.fixture
def set_timezone(request, toolbox):
    yield
    toolbox.target.get('/set_timezone', params={'timezone': 'UTC'})


@pytest.mark.smoke
def test_status_timezone(toolbox, set_timezone):
    data = toolbox.target.get('/get_timezone')
    assert 'timezone' in data
    assert data['timezone'] == 'UTC'

    now = datetime.utcnow()
    data = toolbox.target.get('/get_status')
    assert 'time' in data
    assert data['time'] == now.strftime('%H:%M')


@pytest.mark.smoke
def test_timezone_change(toolbox, set_timezone):
    toolbox.target.get('/set_timezone', params={'timezone': 'America/Bahia'})

    data = toolbox.target.get('/get_timezone')
    assert 'timezone' in data
    assert data['timezone'] == 'America/Bahia'

    bahia_timezone = timezone('America/Bahia')
    now = datetime.now(bahia_timezone)
    data = toolbox.target.get('/get_status')
    assert 'time' in data
    assert data['time'] == now.strftime('%H:%M')
