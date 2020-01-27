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
Tests for metrics.
"""
import os
import unittest
import requests
import copy
import ujson as json
import fakesleep
import xmlrunner
import time
from threading import Lock
from mock import Mock
from ioc import SetTestMode, SetUpTestInjections
from gateway.config import ConfigurationController
from gateway.metrics_controller import MetricsController
from gateway.metrics_caching import MetricsCacheController


class MetricsTest(unittest.TestCase):
    intervals = {}

    BUFFER_FILE = 'buffer_test.db'
    CONFIG_FILE = 'config_test.db'

    @classmethod
    def setUpClass(cls):
        SetTestMode()
        fakesleep.monkey_patch()
        fakesleep.reset(seconds=0)

    @classmethod
    def tearDownClass(cls):
        fakesleep.monkey_restore()

    def setUp(self):
        if os.path.exists(MetricsTest.CONFIG_FILE):
            os.remove(MetricsTest.CONFIG_FILE)
        if os.path.exists(MetricsTest.BUFFER_FILE):
            os.remove(MetricsTest.BUFFER_FILE)
        self.maxDiff = None

    def tearDown(self):
        if os.path.exists(MetricsTest.CONFIG_FILE):
            os.remove(MetricsTest.CONFIG_FILE)
        if os.path.exists(MetricsTest.BUFFER_FILE):
            os.remove(MetricsTest.BUFFER_FILE)

    @staticmethod
    def _set_cloud_interval(self, metric_type, interval):
        _ = self
        MetricsTest.intervals[metric_type] = interval

    @staticmethod
    def _get_controller(intervals):
        metrics_collector = type('MetricsCollector', (), {'intervals': intervals,
                                                          'get_metric_definitions': lambda: [],
                                                          'get_definitions': lambda *args, **kwargs: {},
                                                          'set_cloud_interval': MetricsTest._set_cloud_interval})()
        metrics_cache_controller = type('MetricsCacheController', (), {'load_buffer': lambda *args, **kwargs: []})()
        plugin_controller = type('PluginController', (), {'get_metric_definitions': lambda *args, **kwargs: {}})()
        SetUpTestInjections(config_db=MetricsTest.CONFIG_FILE,
                            config_db_lock=Lock())
        config_controller = ConfigurationController()
        SetUpTestInjections(plugin_controller=plugin_controller,
                            metrics_collector=metrics_collector,
                            metrics_cache_controller=metrics_cache_controller,
                            configuration_controller=config_controller,
                            gateway_uuid='none')
        metrics_controller = MetricsController()
        return config_controller, metrics_controller

    def test_base_validation(self):
        MetricsTest.intervals = {}
        _, _ = MetricsTest._get_controller(intervals=['energy'])
        self.assertEqual(MetricsTest.intervals.get('energy'), 300)

    def test_set_cloud_interval(self):
        MetricsTest.intervals = {}
        config_controller, metrics_controller = MetricsTest._get_controller(intervals=['energy'])
        self.assertEqual(MetricsTest.intervals.get('energy'), 300)
        metrics_controller.set_cloud_interval('energy', 900)
        self.assertEqual(MetricsTest.intervals.get('energy'), 900)
        self.assertEqual(config_controller.get_setting('cloud_metrics_interval|energy'), 900)

    def test_needs_upload(self):
        # 0. the boring stuff
        def get_setting(setting, fallback=None):
            return config.get(setting, fallback)

        def load_buffer(before=None):
            _ = before
            return []

        config_controller = Mock()
        config_controller.get_setting = get_setting
        metrics_cache_mock = Mock()
        metrics_cache_mock.load_buffer = load_buffer
        metrics_collector_mock = Mock()
        metrics_collector_mock.intervals = []
        metrics_collector_mock.get_definitions = lambda: []

        # 1. baseline config and definitions
        config = {'cloud_enabled': True,
                  'cloud_metrics_types': ['counter', 'energy'],
                  'cloud_metrics_sources': ['openmotics'],
                  'cloud_metrics_enabled|energy': True}

        definitions = {'OpenMotics': {'counter': Mock(), 'energy': Mock()}}

        SetUpTestInjections(plugin_controller=Mock(),
                            metrics_collector=metrics_collector_mock,
                            metrics_cache_controller=metrics_cache_mock,
                            configuration_controller=config_controller,
                            gateway_uuid=Mock())

        metrics_controller = MetricsController()
        metrics_controller.definitions = definitions

        # 2. test simple metric
        metric = {'source': 'OpenMotics',
                  'type': 'energy',
                  'timestamp': 1234,
                  'tags': {'device': 'OpenMotics energy ID1', 'id': 'E7.3'},
                  'values': {'counter': 5678, 'power': 9012}}

        needs_upload = metrics_controller._needs_upload_to_cloud(metric)
        self.assertTrue(needs_upload)

        # 3. disable energy metric type, now test again
        config['cloud_metrics_enabled|energy'] = False
        needs_upload = metrics_controller._needs_upload_to_cloud(metric)
        self.assertFalse(needs_upload)
        config['cloud_metrics_enabled|energy'] = True

        # 3. disable energy metric type, now test again
        config['cloud_metrics_types'] = ['counter']
        needs_upload = metrics_controller._needs_upload_to_cloud(metric)
        self.assertFalse(needs_upload)
        config['cloud_metrics_types'] = ['counter', 'energy']

        # 4. test metric with unconfigured definition
        metric = {'source': 'MBus',
                  'type': 'energy',
                  'timestamp': 1234,
                  'tags': {'device': 'OpenMotics energy ID1', 'id': 'E7.3'},
                  'values': {'counter': 5678, 'power': 9012}}

        needs_upload = metrics_controller._needs_upload_to_cloud(metric)
        self.assertFalse(needs_upload)

        # 5. configure definition, now test again
        definitions['MBus'] = {'counter': Mock(), 'energy': Mock()}
        needs_upload = metrics_controller._needs_upload_to_cloud(metric)
        self.assertFalse(needs_upload)

        # 5. configure source, now test again
        config['cloud_metrics_sources'].append('mbus')
        needs_upload = metrics_controller._needs_upload_to_cloud(metric)
        self.assertTrue(needs_upload)

        # 7. disable cloud, now test again
        config['cloud_enabled'] = False
        needs_upload = metrics_controller._needs_upload_to_cloud(metric)
        self.assertFalse(needs_upload)

    def test_metrics_receiver(self):

        config = {'cloud_endpoint': 'tests.openmotics.com',
                  'cloud_endpoint_metrics': 'metrics',
                  'cloud_metrics_interval|foobar': 5}

        # Add interceptors

        send_metrics = []
        response_data = {}

        def get_setting(setting, fallback=None):
            return config.get(setting, fallback)

        def post(url, data, timeout):
            _ = url, timeout
            # Extract metrics, parse assumed data format
            time.sleep(1)
            send_metrics.append([m[0] for m in json.loads(data['metrics'])])
            response = type('response', (), {})()
            response.text = json.dumps(copy.deepcopy(response_data))
            return response

        # Initialize (mocked) classes

        base_metric = {'source': 'OpenMotics',
                       'type': 'foobar',
                       'timestamp': 1,
                       'tags': {'name': 'name', 'id': 0},
                       'values': {'counter': 0}}

        requests.post = post

        SetUpTestInjections(metrics_db=MetricsTest.BUFFER_FILE, metrics_db_lock=Lock())

        metrics_cache = MetricsCacheController()
        config_controller = Mock()
        config_controller.get_setting = get_setting
        metrics_collector_mock = Mock()
        metrics_collector_mock.intervals = []

        definitions = [{'type': 'foobar',
                        'tags': ['id', 'name'],
                        'metrics': [{'name': 'counter',
                                     'description': 'Some field',
                                     'type': 'counter',
                                     'policies': ['buffer'],
                                     'unit': ''}]}]
        metrics_collector_mock.get_definitions = lambda: definitions

        SetUpTestInjections(plugin_controller=Mock(),
                            metrics_collector=metrics_collector_mock,
                            metrics_cache_controller=metrics_cache,
                            configuration_controller=config_controller,
                            gateway_uuid='uuid')

        metrics_controller = MetricsController()
        metrics_controller._needs_upload_to_cloud = lambda *args, **kwargs: True
        self.assertEqual(metrics_controller._buffer_counters, {'OpenMotics': {'foobar': {'counter': True}}})

        # Add some helper methods

        def send_metric(counter, error):
            response_data.update({'success': True})
            if error:
                response_data.update({'success': False, 'error': 'error'})
            metric = copy.deepcopy(base_metric)
            # noinspection PyTypeChecker
            metric['timestamp'] = time.time()
            metric['values']['counter'] = counter
            metrics_controller.receiver(metric)
            return metric

        def assert_fields(controller, cache, queue, stats, buffer, last_send, last_try, retry_interval):
            self.assertDictEqual(controller._cloud_cache, cache)
            self.assertListEqual(controller._cloud_queue, queue)
            self.assertDictEqual(controller.cloud_stats, stats)
            self.assertListEqual(controller._cloud_buffer, buffer)
            self.assertEquals(controller._cloud_last_send, last_send)
            self.assertEquals(controller._cloud_last_try, last_try)
            self.assertEquals(controller._cloud_retry_interval, retry_interval)

        # Validate initial state

        assert_fields(metrics_controller,
                      cache={},
                      queue=[],
                      stats={'queue': 0, 'buffer': 0, 'time_ago_send': 0, 'time_ago_try': 0},
                      buffer=[],
                      last_send=0,
                      last_try=0,
                      retry_interval=None)

        # Send first metrics, but raise exception on "cloud"

        send_metrics = []
        config['cloud_metrics_batch_size'] = 0

        time.sleep(10)  # Time moves on inside fakesleep
        metric_1 = send_metric(counter=0, error=True)
        buffer_metric_timestamp = metric_1['timestamp']

        self.assertEqual(len(send_metrics), 1)
        metrics = send_metrics.pop()
        self.assertEqual(len(metrics), 1)
        self.assertDictEqual(metrics.pop(), metric_1)

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 10}}}},
                      queue=[[metric_1]],
                      stats={'queue': 1, 'buffer': 0, 'time_ago_send': 10, 'time_ago_try': 10},  # Nothing buffered yet
                      buffer=[],
                      last_send=0,
                      last_try=10,
                      retry_interval=None)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [{'timestamp': buffer_metric_timestamp, 'counter': 0}])

        # Send another metric, still errors on "cloud"

        time.sleep(10)  # Time moves on inside fakesleep
        metric_2 = send_metric(counter=1, error=True)

        self.assertEqual(len(send_metrics), 1)
        metrics = send_metrics.pop()
        self.assertEqual(len(metrics), 2)
        self.assertDictEqual(metrics.pop(), metric_2)
        self.assertDictEqual(metrics.pop(), metric_1)

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 20}}}},
                      queue=[[metric_1], [metric_2]],
                      stats={'queue': 2, 'buffer': 1, 'time_ago_send': 21, 'time_ago_try': 11},
                      buffer=[],
                      last_send=0,
                      last_try=21,
                      retry_interval=None)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [{'timestamp': buffer_metric_timestamp, 'counter': 0}])

        # Send another metric, this time the call is accepted correctly

        time.sleep(10)  # Time moves on inside fakesleep
        metric_3 = send_metric(counter=2, error=False)

        self.assertEqual(len(send_metrics), 1)
        metrics = send_metrics.pop()
        self.assertEqual(len(metrics), 3)
        self.assertDictEqual(metrics.pop(), metric_3)
        self.assertDictEqual(metrics.pop(), metric_2)
        self.assertDictEqual(metrics.pop(), metric_1)

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 30}}}},
                      queue=[],
                      stats={'queue': 3, 'buffer': 1, 'time_ago_send': 32, 'time_ago_try': 11},  # Buffer stats not cleared yet
                      buffer=[],
                      last_send=32,
                      last_try=32,
                      retry_interval=None)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [])

        # Validate increased batch sizes

        send_metrics = []
        config['cloud_metrics_batch_size'] = 3
        config['cloud_metrics_min_interval'] = 300

        time.sleep(10)  # Time moves on inside fakesleep
        metric_1 = send_metric(counter=3, error=False)
        time.sleep(1)  # Time moves on inside fakesleep
        send_metric(counter=4, error=False)  # This metric has the same (rounded) timestamp, so should be discarded
        time.sleep(9)  # Time moves on inside fakesleep
        metric_2 = send_metric(counter=5, error=False)

        self.assertEqual(len(send_metrics), 0)  # No metric send, still < batch size

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 50}}}},
                      queue=[[metric_1], [metric_2]],
                      stats={'queue': 2, 'buffer': 0, 'time_ago_send': 21, 'time_ago_try': 21},
                      buffer=[],
                      last_send=32,
                      last_try=32,
                      retry_interval=300)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [])

        time.sleep(10)  # Time moves on inside fakesleep
        metric_3 = send_metric(counter=6, error=False)  # Add another metric, now reaching batch size

        self.assertEqual(len(send_metrics), 1)
        metrics = send_metrics.pop()
        self.assertEqual(len(metrics), 3)
        self.assertDictEqual(metrics.pop(), metric_3)
        self.assertDictEqual(metrics.pop(), metric_2)
        self.assertDictEqual(metrics.pop(), metric_1)
        self.assertEqual(len(metrics), 0)

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 60}}}},
                      queue=[],
                      stats={'queue': 3, 'buffer': 0, 'time_ago_send': 31, 'time_ago_try': 31},
                      buffer=[],
                      last_send=63,
                      last_try=63,
                      retry_interval=300)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [])

        # Send metric after minimum interval, even though batch size isn't reached

        time.sleep(300)  # Time moves on inside fakesleep
        metric_1 = send_metric(counter=6, error=False)  # Add another metric, now reaching batch size

        self.assertEqual(len(send_metrics), 1)
        metrics = send_metrics.pop()
        self.assertListEqual(metrics, [metric_1])

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 360}}}},
                      queue=[],
                      stats={'queue': 1, 'buffer': 0, 'time_ago_send': 301, 'time_ago_try': 301},
                      buffer=[],
                      last_send=364,
                      last_try=364,
                      retry_interval=300)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [])

        # Send metric, but raise exception on "cloud"

        send_metrics = []
        config['cloud_metrics_batch_size'] = 0

        time.sleep(10)  # Time moves on inside fakesleep
        metric_1 = send_metric(counter=7, error=True)
        buffer_metric_timestamp = metric_1['timestamp']

        self.assertEqual(len(send_metrics), 1)
        metrics = send_metrics.pop()
        self.assertEqual(len(metrics), 1)
        self.assertDictEqual(metrics.pop(), metric_1)

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 375}}}},
                      queue=[[metric_1]],
                      stats={'queue': 1, 'buffer': 0, 'time_ago_send': 11, 'time_ago_try': 11},  # Nothing buffered yet
                      buffer=[],
                      last_send=364,
                      last_try=375,
                      retry_interval=300)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [{'timestamp': buffer_metric_timestamp, 'counter': 7}])

        # Emulate service restart

        metrics_controller = MetricsController()
        metrics_controller._needs_upload_to_cloud = lambda *args, **kwargs: True

        # Validate startup state

        assert_fields(metrics_controller,
                      cache={},
                      queue=[],
                      stats={'queue': 0, 'buffer': 1, 'time_ago_send': 0, 'time_ago_try': 0},
                      buffer=[[metric_1]],
                      last_send=376,
                      last_try=376,
                      retry_interval=None)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [{'timestamp': buffer_metric_timestamp, 'counter': 7}])

        # Send another metric which should result in sending queue en buffer

        time.sleep(10)  # Time moves on inside fakesleep
        metric_2 = send_metric(counter=8, error=False)

        self.assertEqual(len(send_metrics), 1)
        metrics = send_metrics.pop()
        self.assertEqual(len(metrics), 2)
        self.assertDictEqual(metrics.pop(), metric_2)
        self.assertDictEqual(metrics.pop(), metric_1)

        assert_fields(metrics_controller,
                      cache={'OpenMotics': {'foobar': {'id=0|name=name': {'timestamp': 385}}}},
                      queue=[],
                      stats={'queue': 1, 'buffer': 1, 'time_ago_send': 10, 'time_ago_try': 10},
                      buffer=[],
                      last_send=386,
                      last_try=386,
                      retry_interval=300)
        buffered_metrics = MetricsTest._load_buffered_metrics(metrics_cache)
        self.assertEqual(buffered_metrics, [])

    def test_buffer(self):
        SetUpTestInjections(metrics_db=MetricsTest.BUFFER_FILE,
                            metrics_db_lock=Lock())
        controller = MetricsCacheController()
        tags = {'name': 'name', 'id': 0}

        expected_metrics = []
        for i in xrange(10):
            timestamp = 300 + 60 * 60 * 12 * i  # Metric every 12 hours
            controller.buffer_counter('OpenMotics', 'foobar', tags, {'counter': i}, timestamp)
            if not (i % 2):
                # Only one metric every day is expected to be buffered
                expected_metrics.append({'counter': i, 'timestamp': timestamp})

        buffered_metrics = MetricsTest._load_buffered_metrics(controller)
        self.assertEqual(5, len(buffered_metrics))
        self.assertEqual(expected_metrics, buffered_metrics)

        removed = controller.clear_buffer(60 * 60 * 24 * 2)
        self.assertEqual(2, removed)
        buffered_metrics = MetricsTest._load_buffered_metrics(controller)
        self.assertEqual(3, len(buffered_metrics))
        self.assertEqual(expected_metrics[2:], buffered_metrics)

    @staticmethod
    def _load_buffered_metrics(controller):
        buffered_metrics = []
        buffer_items = controller._execute_unlocked("SELECT counters, timestamp FROM counters_buffer INNER JOIN counter_sources ON counter_sources.id = counters_buffer.source_id;")
        for item in buffer_items:
            buffered_metrics.append({'counter': json.loads(item[0])['counter'], 'timestamp': item[1]})
        return buffered_metrics


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='../gw-unit-reports'))
