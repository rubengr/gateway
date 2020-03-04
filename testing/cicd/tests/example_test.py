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
from datetime import datetime

import hypothesis
import pytest
import ujson as json
from hypothesis.strategies import booleans, integers, just, one_of
from pytz import timezone
from requests.packages import urllib3

logger = logging.getLogger('openmotics')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def test_health_check(toolbox):
    data = toolbox.target.get('/health_check')
    assert 'health' in data
    assert data['health']['led_service']['state']
    assert data['health']['vpn_service']['state']
    assert data['health']['openmotics']['state']


def test_features(toolbox):
    data = toolbox.target.get('/get_features')
    assert 'features' in data
    assert 'input_states' in data['features']


def test_version(toolbox):
    data = toolbox.target.get('/get_version')
    assert 'version' in data
    assert 'gateway' in data


@pytest.fixture
def set_timezone(request, toolbox):
    yield
    toolbox.target.get('/set_timezone', params={'timezone': 'UTC'})


@pytest.mark.time
def test_status_timezone(toolbox, set_timezone):
    data = toolbox.target.get('/get_timezone')
    assert 'timezone' in data
    assert data['timezone'] == 'UTC'

    now = datetime.utcnow()
    data = toolbox.target.get('/get_status')
    assert 'time' in data
    assert data['time'] == now.strftime('%H:%M')


@pytest.mark.time
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


@pytest.fixture
def discover_mode(request, toolbox):
    yield
    toolbox.target.get('/module_discover_stop')


@pytest.mark.module
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


def example_io(**kwargs):
    return integers(min_value=0, max_value=5, **kwargs)


@pytest.mark.output
@hypothesis.given(example_io(), booleans())
def test_output_events(toolbox, output_id, output_status):
    logger.info('output status o#{}, expect event {} -> {}'.format(output_id, not output_status, output_status))
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    toolbox.set_output(output_id, output_status)
    toolbox.assert_output_event(output_id, output_status)


@pytest.mark.output
@hypothesis.given(example_io(), booleans(), booleans())
def test_output_status(toolbox, output_id, previous_output_status, output_status):
    logger.info('output status o#{}, expect status {} -> {}'.format(output_id, previous_output_status, output_status))
    output_config = {'timer': 2**16 - 1}
    toolbox.configure_output(output_id, output_config)

    toolbox.set_output(output_id, previous_output_status)
    time.sleep(2)
    toolbox.set_output(output_id, output_status)
    toolbox.assert_output_status(output_id, output_status)


@pytest.mark.output
@hypothesis.given(example_io(), just(True))
def test_output_timer(toolbox, output_id, output_status):
    logger.info('output timer o#{}, expect event {} -> {}'.format(output_id, output_status, not output_status))
    output_config = {'timer': 3}  # FIXME: event reordering with timer of <2s
    toolbox.ensure_output(output_id, False, output_config)

    toolbox.set_output(output_id, output_status)
    # toolbox.assert_output_event(output_id, output_status)
    toolbox.assert_output_event(output_id, not output_status)


@pytest.mark.input
@pytest.mark.output
@hypothesis.given(example_io(), example_io(), booleans())
def test_input_action(toolbox, input_id, output_id, output_status):
    logger.info('input action i#{} to o#{}, expect event {} -> {}'.format(input_id, output_id, not output_status, output_status))

    input_config = json.dumps({'id': input_id, 'action': output_id, 'invert': 255})
    toolbox.target.get('/set_input_configuration', {'config': input_config})

    # NOTE ensure output status _after_ input configuration, changing
    # inputs can impact the output status for some reason.
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    toolbox.toggle_input(input_id)
    toolbox.assert_output_event(output_id, output_status)
