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
import unittest

import ujson as json
from hypothesis import assume, example, given, reproduce_failure
from hypothesis.strategies import booleans, integers, just
from requests.packages import urllib3

logger = logging.getLogger('openmotics')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if False:  # MYPY
    from typing import Any, Dict, List, Optional


def example_io(**kwargs):
    return integers(min_value=0, max_value=7, **kwargs)


def test_module_discovery(toolbox):
    toolbox.target.get('/module_discover_start')
    time.sleep(0.2)
    data = toolbox.target.get('/module_discover_status')
    assert data['running'] == True
    toolbox.target.get('/module_discover_stop')

    data = toolbox.target.get('/get_modules')
    assert 'inputs' in data
    assert 'I' in data['inputs']
    assert 'outputs' in data
    assert 'O' in data['outputs']

@given(example_io(), booleans())
def test_output_events(toolbox, output_id, output_status):
    logger.info('output status o#{}, expect event {} -> {}'.format(output_id, not output_status, output_status))
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    toolbox.set_output(output_id, output_status)
    toolbox.assert_output_event(output_id, output_status)

@given(example_io(), booleans(), booleans())
def test_output_status(toolbox, output_id, previous_output_status, output_status):
    logger.info('output status o#{}, expect status {} -> {}'.format(output_id, previous_output_status, output_status))
    output_config = {'timer': 2**16 - 1}
    toolbox.configure_output(output_id, output_config)

    toolbox.set_output(output_id, previous_output_status)
    toolbox.set_output(output_id, output_status)
    toolbox.assert_output_status(output_id, output_status)

@given(example_io(), just(True))
def test_output_timer(toolbox, output_id, output_status):
    logger.info('output timer o#{}, expect event {} -> {}'.format(output_id, output_status, not output_status))
    output_config = {'timer': 2}  # FIXME: event reordering with timer of <2s
    toolbox.ensure_output(output_id, False, output_config)

    toolbox.set_output(output_id, output_status)
    toolbox.assert_output_event(output_id, output_status)
    toolbox.assert_output_event(output_id, not output_status, timeout=3)

@given(example_io(), example_io(), booleans())
def test_input_action(toolbox, input_id, output_id, output_status):
    logger.info('input action i#{} to o#{}, expect event {} -> {}'.format(input_id, output_id, not output_status, output_status))
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    input_config = json.dumps({'id': input_id, 'action': output_id, 'invert': 255})
    toolbox.target.get('/set_input_configuration', {'config': input_config})
    toolbox.toggle_input(input_id)
    toolbox.assert_output_event(output_id, output_status)
