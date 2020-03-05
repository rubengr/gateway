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
from hypothesis.strategies import booleans, composite, integers, just, one_of

logger = logging.getLogger('openmotics')


@composite
def build_output(draw, min_modules=0):
    def f(toolbox):
        modules = toolbox.list_modules('O', min_modules=min_modules)
        return draw(integers(min_value=0, max_value=len(modules) * 8 - 1))
    return f


@pytest.mark.smoke
@hypothesis.given(build_output(), booleans())
def test_events(toolbox, build_output, output_status):
    output_id = build_output(toolbox)
    logger.info('output status o#{}, expect event {} -> {}'.format(output_id, not output_status, output_status))
    output_config = {'timer': 2**16 - 1}
    toolbox.ensure_output(output_id, not output_status, output_config)

    toolbox.set_output(output_id, output_status)
    toolbox.assert_output_event(output_id, output_status)


@pytest.mark.smoke
@hypothesis.given(build_output(), booleans(), booleans())
def test_status(toolbox, build_output, previous_output_status, output_status):
    output_id = build_output(toolbox)
    logger.info('output status o#{}, expect status {} -> {}'.format(output_id, previous_output_status, output_status))
    output_config = {'timer': 2**16 - 1}
    toolbox.configure_output(output_id, output_config)

    toolbox.set_output(output_id, previous_output_status)
    time.sleep(2)
    toolbox.set_output(output_id, output_status)
    toolbox.assert_output_status(output_id, output_status)


@pytest.mark.smoke
@hypothesis.given(build_output(), just(True))
def test_timers(toolbox, build_output, output_status):
    output_id = build_output(toolbox)
    logger.info('output timer o#{}, expect event {} -> {}'.format(output_id, output_status, not output_status))
    output_config = {'timer': 3}  # FIXME: event reordering with timer of <2s
    toolbox.ensure_output(output_id, False, output_config)

    toolbox.set_output(output_id, output_status)
    # toolbox.assert_output_event(output_id, output_status)
    toolbox.assert_output_event(output_id, not output_status)
