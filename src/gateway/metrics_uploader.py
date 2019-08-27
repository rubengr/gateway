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
The metrics uploader sends metric data to the cloud
"""

import time
import logging
from threading import Thread
from wiring import inject, provides, SingletonScope, scope
from cloud.cloud_api_client import APIException
from collections import deque

try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger("openmotics")


class MetricsUploader(object):


    """
    The Metrics Upload uploads metrics to the cloud
    """
    @provides('metrics_uploader')
    @scope(SingletonScope)
    @inject(config_controller='config_controller', metrics_cache_controller='metrics_cache_controller',
            metrics_collector='metrics_collector', cloud_api_client='cloud_api_client')
    def __init__(self, config_controller, metrics_cache_controller, metrics_collector, cloud_api_client):
        """
        :param config_controller: Configuration Controller
        :type config_controller: gateway.config.ConfigurationController
        :param cloud_api_client: The cloud API object
        :type cloud_api_client: cloud.cloud_api_client.CloudAPIClient
        """
        self._unbuffered_metrics_queue = deque()
        self._stopped = True
        self._unbuffered_upload_thread = None
        self._buffered_upload_thread = None

        self._config_controller = config_controller
        self._cloud_api_client = cloud_api_client
        self._metrics_cache_controller = metrics_cache_controller
        self._metrics_collector = metrics_collector

        self._cloud_last_send = time.time()
        self._cloud_last_try = time.time()
        self._cloud_retry_interval = None

        self.cloud_stats = {'queue': 0,
                            'buffer': 0,
                            'time_ago_send': 0,
                            'time_ago_try': 0}

    def push(self, metric):
        if self._needs_upload(metric):
            if self._needs_buffering(metric):
                self._add_to_buffered_queue(metric)
            else:
                self._add_to_unbuffered_queue(metric)

    def start(self):
        if self._stopped:
            self._stopped = False

            self._buffered_upload_thread = Thread(target=self._buffered_upload)
            self._buffered_upload_thread.setName('Metrics Buffered Uploader for OpenMotics')
            self._buffered_upload_thread.daemon = True
            self._buffered_upload_thread.start()

            self._unbuffered_upload_thread = Thread(target=self._unbuffered_upload)
            self._unbuffered_upload_thread.setName('Metrics Unbuffered Uploader for OpenMotics')
            self._unbuffered_upload_thread.daemon = True
            self._unbuffered_upload_thread.start()
        else:
            raise RuntimeError('Metrics uploader already started')

    def stop(self):
        self._stopped = True

    # drop unwanted metrics or all in case not configured to upload metric
    def _needs_upload(self, metric):
        metric_type = metric['type']
        metric_source = metric['source']

        if self._config_controller.get_setting('cloud_enabled', True) is False:
            return False

        if metric_source == 'OpenMotics':
            if self._config_controller.get_setting('cloud_metrics_enabled|{0}'.format(metric_type), True) is False:
                return False

            # filter openmotics metrics that are not listed in cloud_metrics_types
            metric_types = self._config_controller.get_setting('cloud_metrics_types')
            if metric_type not in metric_types:
                return False
        else:
            # filter 3rd party (plugin) metrics that are not listed in cloud_metrics_sources
            metric_sources = self._config_controller.get_setting('cloud_metrics_sources')
            # make sure to get the lowercase metric_source
            if metric_source.lower() not in metric_sources:
                return False
        return True

    def _get_metrics_from_queue(self, n):
        # Yield n metrics from the Queue
        num = 0
        try:
            while num < n:
                yield self._unbuffered_metrics_queue.pop()
                num += 1
        except IndexError:
            pass

    def _unbuffered_upload_needed(self):
        cloud_batch_size = self._config_controller.get_setting('cloud_metrics_batch_size')
        cloud_min_interval = self._config_controller.get_setting('cloud_metrics_min_interval')
        if self._cloud_retry_interval is None:
            self._cloud_retry_interval = cloud_min_interval

        # Check timings/rates
        now = time.time()
        time_ago_send = int(now - self._cloud_last_send)
        time_ago_try = int(now - self._cloud_last_try)
        outstanding_data_length = len(self._unbuffered_metrics_queue)

        upload_now = (outstanding_data_length > 0 and  # There must be outstanding data
                     ((outstanding_data_length > cloud_batch_size and time_ago_send == time_ago_try) or  # Last send was successful, but the buffer length > batch size
                     (time_ago_send > cloud_min_interval and time_ago_send == time_ago_try) or  # Last send was successful, but it has been too long ago
                     (time_ago_send > time_ago_try > self._cloud_retry_interval)))  # Last send was unsuccessful, and it has been a while

        self.cloud_stats['queue'] = len(self._unbuffered_metrics_queue)
        self.cloud_stats['buffer'] = self._cloud_buffer_length
        self.cloud_stats['time_ago_send'] = time_ago_send
        self.cloud_stats['time_ago_try'] = time_ago_try

        return upload_now

    def _unbuffered_upload(self):
        while not self._stopped and self._upload_now():
            try:
                now = time.time()
                self._cloud_last_try = now
                cloud_batch_size = self._config_controller.get_setting('cloud_metrics_batch_size')
                metrics = [m for m in self._get_metrics_from_queue(cloud_batch_size)]
                if len(metrics) > 0:
                    self._cloud_api_client.send_metrics(metrics)  # raises APIExceptions
            except APIException as ex:
                logger.error(ex)
                self._decrease_intervals(time_ago_send)
            except Exception as ex:
                logger.exception('Unkown error sending metrics to cloud: {0}'.format(ex))
                self._decrease_intervals(time_ago_send)
            time.sleep(0.1)

        try:
            # Try to send the metrics
            payload = self._cloud_buffer + self._cloud_queue

            # If successful; clear buffers
            if self._metrics_cache_controller.clear_buffer(metric['timestamp']) > 0:
                self._load_cloud_buffer()
            self._cloud_queue = []
            self._cloud_last_send = now
            self._cloud_retry_interval = cloud_min_interval
        except Exception as ex:
            logger.error('Error sending metrics to Cloud: {0}'.format(ex))
            self._decrease_intervals(time_ago_send)

    def _get_timestamp(self, metric):
        metric_type = metric['type']
        metric_source = metric['source']
        if metric_source == 'OpenMotics':
            # round off timestamps for openmotics metrics
            modulo_interval = self._config_controller.get_setting('cloud_metrics_interval|{0}'.format(metric_type), 900)
            timestamp = int(metric['timestamp'] - metric['timestamp'] % modulo_interval)
        else:
            timestamp = int(metric['timestamp'])
        return timestamp

    def set_cloud_interval(self, metric_type, interval):
        logger.info('setting cloud interval {0}_{1}'.format(metric_type, interval))
        self.cloud_intervals[metric_type] = interval
        self._metrics_collector.set_cloud_interval(metric_type, interval)
        self._config_controller.set_setting('cloud_metrics_interval|{0}'.format(metric_type), interval)

    def _decrease_intervals(self, time_ago_send):
        if time_ago_send > 60 * 60:
            # Decrease metrics rate, but at least every 2 hours
            # Decrease cloud try interval, but at least every hour
            if time_ago_send < 6 * 60 * 60:
                self._cloud_retry_interval = 15 * 60
                new_interval = 30 * 60
            elif time_ago_send < 24 * 60 * 60:
                self._cloud_retry_interval = 30 * 60
                new_interval = 60 * 60
            else:
                self._cloud_retry_interval = 60 * 60
                new_interval = 2 * 60 * 60
            metric_types = self._config_controller.get_setting('cloud_metrics_types')
            for mtype in metric_types:
                self.set_cloud_interval(mtype, new_interval)

    def _needs_buffering(self, metric):
        metric_type = metric['type']
        metric_source = metric['source']
        definition = self.definitions.get(metric_source, {}).get(metric_type)
        identifier = '|'.join(['{0}={1}'.format(tag, metric['tags'][tag]) for tag in sorted(definition['tags'])])
        entry = self._cloud_cache.setdefault(metric_source, {}).setdefault(metric_type, {}).setdefault(identifier, {})
        include_this_metric = False
        if 'timestamp' not in entry:
            include_this_metric = True
        else:
            old_timestamp = entry['timestamp']
            if old_timestamp < timestamp:
                include_this_metric = True

        # Add metrics to the send queue if they need to be send
        if include_this_metric is True:
            entry['timestamp'] = timestamp
            self._cloud_queue.append([metric])
            self._cloud_queue = self._cloud_queue[-5000:]  # 5k metrics buffer
        pass

    def _add_to_buffered_queue(self, metric):
        metric_type = metric['type']
        metric_source = metric['source']
        self._metrics_cache_controller.buffer_counter(metric_source, metric_type, metric['tags'], cache_data, metric['timestamp']):

        # Buffer metrics if appropriate
        now = time.time()
        time_ago_send = int(now - self._cloud_last_send)
        time_ago_try = int(now - self._cloud_last_try)
        if time_ago_send > time_ago_try and include_this_metric is True and len(counters_to_buffer) > 0:
            cache_data = {}
            for counter, match_setting in counters_to_buffer.iteritems():
                if match_setting is not True:
                    if metric['tags'][match_setting['key']] not in match_setting['matches']:
                        continue
                cache_data[counter] = metric['values'][counter]
            if self._metrics_cache_controller.buffer_counter(metric_source, metric_type, metric['tags'], cache_data, metric['timestamp']):
                self._cloud_buffer_length += 1
            # clear metrics older than 1 year in buffer, reload in case metrics were deleted from buffer
            if self._metrics_cache_controller.clear_buffer(time.time() - 365 * 24 * 60 * 60) > 0:
                self._load_cloud_buffer()

    def _add_to_unbuffered_queue(self, metric):
        self._unbuffered_metrics_queue.appendleft(metric)

    def _update_definitions(self):
        # Metrics generated by the Metrics_Controller_ are also defined in the collector. Trying to get them in one place.
        for definition in self._metrics_collector.get_definitions():
            settings = MetricsUploader._parse_definition(definition)
            self._persist_counters.setdefault('OpenMotics', {})[definition['type']] = settings['persist']
            self._buffer_counters.setdefault('OpenMotics', {})[definition['type']] = settings['buffer']

    @staticmethod
    def _parse_definition(definition):
        settings = {'persist': {},
                    'buffer': {}}
        for metric in definition['metrics']:
            if metric['type'] == 'counter':
                for policy in metric.get('policies', []):
                    setting = True
                    if isinstance(policy, dict):
                        setting = {'key': policy['key'],
                                   'matches': policy['matches']}
                        policy = policy['policy']

                    # Backwards compatibility
                    if policy == 'buffered':
                        policy = 'buffer'
                    if policy == 'persistent':
                        policy = 'persist'

                    settings[policy][metric['name']] = setting
        return settings
