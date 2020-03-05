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
def build_input(draw, min_modules=0):
    def f(toolbox):
        modules = toolbox.list_modules('I', min_modules=min_modules)
        return draw(integers(min_value=0, max_value=len(modules) * 8 - 1))
    return f


@composite
def build_output(draw, min_modules=0):
    def f(toolbox):
        modules = toolbox.list_modules('O', min_modules=min_modules)
        return draw(integers(min_value=0, max_value=len(modules) * 8 - 1))
    return f


@pytest.mark.smoke
@hypothesis.given(build_input(), build_output(), booleans())
def test_actions(toolbox, build_input, build_output, output_status):
    input_id, output_id = (build_input(toolbox), build_output(toolbox))
    logger.info('input action i#{} to o#{}, expect event {} -> {}'.format(input_id, output_id, not output_status, output_status))

    input_config = json.dumps({'id': input_id, 'action': output_id, 'invert': 255})
    toolbox.target.get('/set_input_configuration', {'config': input_config})

    # NOTE ensure output status _after_ input configuration, changing
    # inputs can impact the output status for some reason.
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    toolbox.toggle_input(input_id)
    toolbox.assert_output_event(output_id, output_status)
