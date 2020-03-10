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
import json
import os
import time

import pytest
from hypothesis import assume, given, reproduce_failure, settings
from hypothesis.stateful import Bundle, RuleBasedStateMachine, consumes, \
    initialize, invariant, precondition, rule
from hypothesis.strategies import booleans, integers, just, one_of

from .toolbox import Toolbox


class Output(object):
    def __init__(self, output_id, status=False):
        self.output_id = output_id
        self.status = status


class Input(object):
    def __init__(self, input_id, linked_output):
        self.input_id = input_id
        self.linked_output = linked_output


@pytest.mark.stateful
class IOComparison(RuleBasedStateMachine):
    def __init__(self):
        super(IOComparison, self).__init__()
        self.changed = False
        self.toolbox = Toolbox()

        self.inputs = self.toolbox.target_inputs
        self.outputs = self.toolbox.target_outputs

    inputs = Bundle('inputs')
    outputs = Bundle('outputs')

    def teardown(self):
        pass

    @precondition(lambda self: self.outputs)
    @rule(target=outputs, status=just(False))
    def add_output(self, status):
        self.changed = True
        output_id = self.outputs.pop()
        self.toolbox.ensure_output(output_id, status, {'timer': 2**16 - 1})
        o = Output(output_id, status)
        return o

    # TODO: use timestamps for timer state
    # @precondition(lambda self: self.outputs)
    # @rule(target=outputs, timer=just(2), status=just(False))
    # def add_output_timer(self, timer, status):
    #     output_id = self.outputs.pop()
    #     self.toolbox.ensure_output(output_id, status, {'timer': timer})
    #     o = Output(output_id, status)
    #     return o

    @precondition(lambda self: self.inputs)
    @rule(target=inputs, o=outputs)
    def add_input_action(self, o):
        self.changed = True
        input_id = self.inputs.pop()
        input_config = {'id': input_id, 'action': o.output_id}
        self.toolbox.target.get('/set_input_configuration', {'config': json.dumps(input_config)})

        # FIXME: workaround
        time.sleep(1)
        self.toolbox.ensure_output(o.output_id, o.status)

        i = Input(input_id, o)
        return i

    @rule(i=inputs)
    def press_input(self, i):
        self.changed = True
        o = i.linked_output
        o.status = not o.status
        self.toolbox.press_input(i.input_id)

    @rule(o=outputs)
    def swap_output(self, o):
        self.changed = True
        o.status = not o.status
        time.sleep(1)
        self.toolbox.observer.reset()
        self.toolbox.set_output(o.output_id, o.status)
        self.toolbox.assert_output_event(o.output_id, o.status)

    @rule(o=outputs)
    @precondition(lambda self: self.changed)
    def get_output_status(self, o):
        self.changed = False
        self.toolbox.assert_output_status(o.output_id, o.status)


class TestIOComparison(IOComparison.TestCase):  # type: ignore
    @pytest.mark.stateful
    def runTest(self):
        super(TestIOComparison, self).runTest()
