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
Tests for metrics.
"""
import os
import unittest
import xmlrunner
import time
from threading import Lock

from gateway.config import ConfigurationController
from gateway.metrics import MetricsController


class MetricsTest(unittest.TestCase):
    intervals = {}

    def setUp(self):
        self._config_db = "test.metrics.config.{0}.db".format(time.time())
        if os.path.exists(self._config_db):
            os.remove(self._config_db)

    def tearDown(self):
        if os.path.exists(self._config_db):
            os.remove(self._config_db)

    @staticmethod
    def _set_cloud_interval(self, metric_type, interval):
        _ = self
        MetricsTest.intervals[metric_type] = interval

    def _get_controller(self, intervals):
        metrics_collector = type('MetricsCollector', (), {'intervals': intervals,
                                                          'get_metric_definitions': lambda: [],
                                                          'get_definitions': lambda *args, **kwargs: {},
                                                          'set_cloud_interval': MetricsTest._set_cloud_interval})()
        metrics_cache_controller = type('MetricsCacheController', (), {'load_buffer': lambda *args, **kwargs: []})()
        plugin_controller = type('PluginController', (), {'get_metric_definitions': lambda *args, **kwargs: {}})()

        config_controller = ConfigurationController(self._config_db, Lock())
        metrics_controller = MetricsController(plugin_controller=plugin_controller,
                                               metrics_collector=metrics_collector,
                                               metrics_cache_controller=metrics_cache_controller,
                                               config_controller=config_controller,
                                               gateway_uuid='none')
        return config_controller, metrics_controller

    def test_base_validation(self):
        MetricsTest.intervals = {}
        _, _ = self._get_controller(intervals=['energy'])
        self.assertEqual(MetricsTest.intervals.get('energy'), 300)

    def test_set_cloud_interval(self):
        MetricsTest.intervals = {}
        config_controller, metrics_controller = self._get_controller(intervals=['energy'])
        self.assertEqual(MetricsTest.intervals.get('energy'), 300)
        metrics_controller.set_cloud_interval('energy', 900)
        self.assertEqual(MetricsTest.intervals.get('energy'), 900)
        self.assertEqual(config_controller.get_setting('cloud_metrics_interval|energy'), 900)


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
