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
The outputs module contains classes to track the current state of the outputs on
the master.
"""

import time


class OutputStatus(object):
    """ Contains a cached version of the current output of the controller. """

    def __init__(self, refresh_period=600, on_output_change=None):
        """
        Create a status object using a list of outputs (can be None),
        and a refresh period: the refresh has to be invoked explicitly.
        """
        self._outputs = {}
        self._refresh_period = refresh_period
        self._last_refresh = 0
        self._on_output_change = on_output_change

    def should_refresh(self):
        """ Check whether the status should be refreshed. """
        return time.time() >= self._last_refresh + self._refresh_period

    def partial_update(self, on_outputs):
        """
        Update the status of the outputs using a list of tuples containing the
        light id an the dimmer value of the lights that are on.
        """
        on_dict = {}
        for on_output in on_outputs:
            on_dict[on_output[0]] = on_output[1]

        for output_id, output in self._outputs.iteritems():
            self._update_maybe_report_change(output, output_id in on_dict, on_dict.get(output_id))

    def full_update(self, outputs):
        """ Update the status of the outputs using a list of Outputs. """
        obsolete_ids = self._outputs.keys()
        for output in outputs:
            output_id = output['id']
            if output_id in obsolete_ids:
                obsolete_ids.remove(output_id)
            if output_id in self._outputs:
                self._update_maybe_report_change(self._outputs[output_id], output['status'], output['dimmer'])
            else:
                self._report_change(output_id)
            self._outputs[output_id] = output
        for output_id in obsolete_ids:
            del self._outputs[output_id]
        self._last_refresh = time.time()

    def get_outputs(self):
        """ Return the list of Outputs. """
        return self._outputs.values()

    def _update_maybe_report_change(self, output, status, dimmer):
        report = False
        if status:
            if output.get('status') != 1 or output.get('dimmer') != dimmer:
                output['status'] = 1
                output['dimmer'] = dimmer
                report = True
        else:
            if output.get('status') != 0:
                output['status'] = 0
                report = True
        if report and self._on_output_change is not None:
            self._report_change(output['id'])

    def _report_change(self, output_id):
        self._on_output_change(output_id)
