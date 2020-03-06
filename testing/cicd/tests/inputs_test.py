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

import hypothesis
import pytest
import ujson as json
from hypothesis.strategies import booleans, composite, integers, just, one_of

logger = logging.getLogger('openmotics')


@composite
def next_input(draw):
    used_values = []
    def f(toolbox):
        value = draw(one_of(map(just, toolbox.target_inputs)).filter(lambda x: x not in used_values))
        used_values.append(value)
        hypothesis.note('module i#{}'.format(value))
        return value
    return f


@composite
def next_output(draw):
    used_values = []
    def f(toolbox):
        value = draw(one_of(map(just, toolbox.target_outputs)).filter(lambda x: x not in used_values))
        used_values.append(value)
        hypothesis.note('module o#{}'.format(value))
        return value
    return f


@pytest.mark.smoke
@hypothesis.given(next_input(), next_output(), booleans())
def test_actions(toolbox, next_input, next_output, output_status):
    input_id, output_id = (next_input(toolbox), next_output(toolbox))
    logger.info('input action i#{} to o#{}, expect event {} -> {}'.format(input_id, output_id, not output_status, output_status))

    input_config = json.dumps({'id': input_id, 'action': output_id, 'invert': 255})
    toolbox.target.get('/set_input_configuration', {'config': input_config})

    # NOTE ensure output status _after_ input configuration, changing
    # inputs can impact the output status for some reason.
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    toolbox.toggle_input(input_id)
    toolbox.assert_output_event(output_id, output_status)


@pytest.mark.slow
@hypothesis.settings(max_examples=2)
@hypothesis.given(next_input(), next_output(), just(True))
def test_motion_sensor(toolbox, next_input, next_output, output_status):
    input_id, output_id = (next_input(toolbox), next_output(toolbox))

    logger.info('motion sensor i#{} to o#{}, expect event {} -> {} after 2m30s'.format(input_id, output_id, output_status, not output_status))
    actions = ['195', str(output_id)]  # output timeout of 2m30s
    input_config = json.dumps({'id': input_id, 'basic_actions': ','.join(actions), 'action': 240, 'invert': 255})
    toolbox.target.get('/set_input_configuration', {'config': input_config})

    # NOTE ensure output status _after_ input configuration, changing
    # inputs can impact the output status for some reason.
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    toolbox.toggle_input(input_id)
    toolbox.assert_output_event(output_id, output_status)
    logger.warning('should use a shorter timeout, waiting for 2m30s')
    time.sleep(180)
    toolbox.assert_output_event(output_id, not output_status)


@pytest.mark.smoke
@hypothesis.given(next_input(), next_output(), integers(min_value=0, max_value=159), booleans())
def test_group_action_toggle(toolbox, next_input, next_output, group_action_id, output_status):
    (input_id, output_id, other_output_id) = (next_input(toolbox), next_output(toolbox), next_output(toolbox))
    logger.info('group action a#{} for i#{} to o#{} o#{}, expect event {} -> {}'.format(group_action_id, input_id, output_id, other_output_id, not output_status, output_status))

    actions = ['2', str(group_action_id)]
    input_config = json.dumps({'id': input_id, 'basic_actions': ','.join(actions), 'action': 240, 'invert': 255})
    toolbox.target.get('/set_input_configuration', {'config': input_config})

    actions = ['162', str(output_id), '162', str(other_output_id)]  # toggle both outputs
    config = {'id': group_action_id, 'actions': ','.join(actions)}
    toolbox.target.get('/set_group_action_configuration', params={'config': json.dumps(config)})

    time.sleep(2)

    output_config = {'type': 0, 'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)
    toolbox.ensure_output(other_output_id, not output_status, output_config)

    toolbox.toggle_input(input_id)
    toolbox.assert_output_event(output_id, output_status)
    toolbox.assert_output_event(other_output_id, output_status)
