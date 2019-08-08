# Copyright (C) 2019 OpenMotics BVBA
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
Tests for the observers module.
"""
import unittest
import xmlrunner
from mock import Mock
from gateway.observer import Observer


class ObserverTest(unittest.TestCase):
    """ Tests for Observer. """

    def test_value_formatting_output(self):
        master_mock = Mock()
        message_client_mock = Mock()

        def callback_test_value_present(event):
            self.assertIn('value', event.data['status'])

        def callback_no_test_value_present(event):
            self.assertNotIn('value', event.data['status'])

        type_callback_mapping = {'d': callback_test_value_present,
                                 'o': callback_no_test_value_present,
                                 'D': callback_test_value_present}

        for module_type, callback in type_callback_mapping.iteritems():
            observer = Observer(master_mock, message_client_mock)
            observer._output_config = {5: {'module_type': module_type, 'room': 'test_room'}}
            observer.subscribe_events(callback)
            status = {'on': 1, 'value': 131}
            observer._output_changed(5, status)


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))

