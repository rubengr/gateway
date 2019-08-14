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
from mock import Mock
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

    def test_needs_upload(self):
        def get_setting(setting, fallback=None):
            return config.get(setting, fallback)

        config_controller = Mock()
        config_controller.get_setting = get_setting

        # 1. baseline config and definitions
        config = {'cloud_enabled': True,
                  'cloud_metrics_types': ['counter', 'energy'],
                  'cloud_metrics_sources': ['openmotics'],
                  'cloud_metrics_enabled|energy': True}

        definitions = {'OpenMotics': {'counter': Mock(), 'energy': Mock()}}

        # 2. test simple metric
        metric = {'source': 'OpenMotics',
                  'type': 'energy',
                  'timestamp': 1234,
                  'tags': {'device': 'OpenMotics energy ID1', 'id': 'E7.3'},
                  'values': {'counter': 5678, 'power': 9012}}

        needs_upload = MetricsController._needs_upload_to_cloud(config_controller, definitions, metric)
        self.assertTrue(needs_upload)

        # 3. disable energy metric type, now test again
        config['cloud_metrics_enabled|energy'] = False
        needs_upload = MetricsController._needs_upload_to_cloud(config_controller, definitions, metric)
        self.assertFalse(needs_upload)
        config['cloud_metrics_enabled|energy'] = True

        # 3. disable energy metric type, now test again
        config['cloud_metrics_types'] = ['counter']
        needs_upload = MetricsController._needs_upload_to_cloud(config_controller, definitions, metric)
        self.assertFalse(needs_upload)
        config['cloud_metrics_types'] = ['counter', 'energy']

        # 4. test metric with unconfigured source
        metric = {'source': 'MBus',
                  'type': 'energy',
                  'timestamp': 1234,
                  'tags': {'device': 'OpenMotics energy ID1', 'id': 'E7.3'},
                  'values': {'counter': 5678, 'power': 9012}}

        needs_upload = MetricsController._needs_upload_to_cloud(config_controller, definitions, metric)
        self.assertFalse(needs_upload)

        # 5. configure source, now test again without definitions
        config['cloud_metrics_sources'].append('mbus')
        needs_upload = MetricsController._needs_upload_to_cloud(config_controller, definitions, metric)
        self.assertFalse(needs_upload)

        # 6. configure source and add definitiions, now test again
        definitions['MBus'] = {'counter': Mock(), 'energy': Mock()}
        needs_upload = MetricsController._needs_upload_to_cloud(config_controller, definitions, metric)
        self.assertTrue(needs_upload)

        # 7. disable cloud, now test again
        config['cloud_enabled'] = False
        needs_upload = MetricsController._needs_upload_to_cloud(config_controller, definitions, metric)
        self.assertFalse(needs_upload)

if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
