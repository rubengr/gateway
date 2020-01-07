# Copyright (C) 2019 OpenMotics BV
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
Tests for plugin runner
"""

import os
import plugin_runtime
import shutil
import tempfile
import unittest
import xmlrunner
from plugins.runner import PluginRunner


class PluginRunnerTest(unittest.TestCase):
    """ Tests for the PluginRunner. """

    PLUGIN_PATH = None
    RUNTIME_PATH = os.path.dirname(plugin_runtime.__file__)

    @classmethod
    def setUpClass(cls):
        cls.RUNTIME_PATH = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.PLUGIN_PATH is not None:
                shutil.rmtree(cls.PLUGIN_PATH)
        except Exception:
            pass

    def _log(self, *args, **kwargs):
        _ = args, kwargs

    def test_queue_length(self):
        runner = PluginRunner('foo', self.RUNTIME_PATH, self.PLUGIN_PATH, self._log)
        self.assertEqual(runner.get_queue_length(), 0)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
