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
import os
import time
from datetime import datetime

import requests
import ujson as json

logger = logging.getLogger('openmotics')

if False:  # MYPY
    from typing import Any, Dict, List, Optional


class Client(object):
    def __init__(self, host, auth=None):
        # type: (str, List[str]) -> None
        self._host = host
        self._auth = auth
        self._default_kwargs = {'verify': False}
        self._token = self.login()

    def login(self):
        # type: () -> Optional[str]
        if self._auth:
            params = {'username': self._auth[0], 'password': self._auth[1]}
            data = self.get('/login', params=params, use_token=False)
            if 'token' in data:
                return data['token']
            else:
                raise Exception('unexpected response {}'.format(data))
        else:
            return None

    def get(self, path, params=None, headers=None, use_token=True):
        # type: (str, Dict[str,Any], Dict[str,Any], bool) -> Any
        params = params or {}
        headers = headers or {}
        uri = 'https://{}{}'.format(self._host, path)
        if use_token and self._token:
            headers['Authorization'] = 'Bearer {}'.format(self._token)
            logger.debug('GET {} {}'.format(path, params))
        response = requests.get(uri, params=params, headers=headers, **self._default_kwargs)
        data = response.json()
        if isinstance(data, dict) and 'status' in data:
            assert data['status'], 'content={}'.format(response.content)
        return data


class Observer(object):
    def __init__(self, client):
        # type: (Client) -> None
        self._client = client
        self._last_received_at = 0.0
        self._last_data = {}  # type: Dict[str,Any]
        self._outputs = {}  # type: Dict[int,bool]
        self.update_events()

    def get_last_outputs(self):
        # type: () -> List[str]
        if self._last_data:
            outputs = self._last_data['events'][-1]['outputs']
            return ['?' if x is None else str(x) for x in outputs]
        else:
            return []

    def get(self, path, params=None, headers=None, use_token=True):
        # type: (str, Dict[str,Any], Dict[str,Any], bool) -> Any
        return self._client.get(path, params=params, headers=headers, use_token=use_token)

    def log_events(self):
        # type: () -> None
        for event in (x for x in self._last_data['events'] if 'output_id' in x):
            received_at, output_id, output_status, outputs = (event['received_at'], event['output_id'], event['output_status'], event['outputs'])
            timestamp = datetime.fromtimestamp(received_at).strftime('%y-%m-%d %H:%M:%S,%f')
            state = ' '.join('?' if x is None else str(x) for x in outputs)
            logger.error('{} received event o#{} -> {}    outputs={}'.format(timestamp, output_id, output_status, state))

    def update_events(self):
        # type: () -> bool
        data = self.get('/plugins/event_observer/events')
        self._last_data = data
        changed = False
        for event in (x for x in self._last_data['events'] if 'output_id' in x):
            received_at, output_id, output_status = (event['received_at'], event['output_id'], event['output_status'])
            if received_at >= self._last_received_at:
                changed = True
                self._last_received_at = received_at
                self._outputs[output_id] = bool(output_status)
        return changed

    def reset(self):
        # type: () -> None
        self._outputs = {}

    def receive_output_event(self, output_id, output_status, timeout):
        # type: (int, bool, float) -> bool
        since = time.time()
        while since > time.time() - timeout:
            if output_id in self._outputs and output_status == self._outputs[output_id]:
                logger.debug('received event o#{} -> {} after {:.2}s'.format(output_id, self._outputs[output_id], time.time() - since))
                return True
            if self.update_events():
                continue
            time.sleep(0.2)
        logger.error('receive event o#{} -> {}, timeout after {}'.format(output_id, output_status, time.time() - since))
        self.log_events()
        return False



class Toolbox(object):
    def __init__(self):
        # type: () -> None
        observer_auth = os.environ['OPENMOTICS_OBSERVER_AUTH'].split(':')
        observer_host = os.environ['OPENMOTICS_OBSERVER_HOST']
        target_auth = os.environ['OPENMOTICS_TARGET_AUTH'].split(':')
        target_host = os.environ['OPENMOTICS_TARGET_HOST']
        self.observer = Observer(Client(observer_host, auth=observer_auth))
        self.target = Client(target_host, auth=target_auth)

    def configure_output(self, output_id, config):
        # type: (int, Dict[str,Any]) -> None
        config_data = {'id': output_id}
        config_data.update(**config)
        self.target.get('/set_output_configuration', {'config': json.dumps(config_data)})

    def ensure_output(self, output_id, status, config=None):
        # type: (int, int, Optional[Dict[str,Any]]) -> None
        if config:
            self.configure_output(output_id, config)
        state = ' '.join(self.observer.get_last_outputs())
        logger.debug('ensure output o#{} is {}    outputs={}'.format(output_id, status, state))
        self.set_output(output_id, status)
        self.observer.reset()

    def set_output(self, output_id, status):
        # type: (int, int) -> None
        self.target.get('/set_output', {'id': output_id, 'is_on': status})

    def toggle_input(self, input_id):
        # type: (int) -> None
        self.observer.get('/set_output', {'id': input_id, 'is_on': False})  # ensure start status
        self.observer.reset()
        self.observer.get('/set_output', {'id': input_id, 'is_on': True})
        time.sleep(0.2)
        self.observer.get('/set_output', {'id': input_id, 'is_on': False})
        logger.debug('toggled i#{} -> True -> False'.format(input_id))

    def assert_output_event(self, output_id, status, timeout=5):
        # type: (int, bool, **Any) -> None
        if self.observer.receive_output_event(output_id, status, timeout=timeout):
            return
        raise AssertionError('expected event o#{} -> {}'.format(output_id, status))

    def assert_output_status(self, output_id, status, timeout=5):
        # type: (int, bool, **Any) -> None
        since = time.time()
        while since > time.time() - timeout:
            data = self.target.get('/get_output_status')
            current_status = data['status'][output_id]['status']
            if bool(status) == bool(current_status):
                return
            time.sleep(0.2)
        state = ' '.join(self.observer.get_last_outputs())
        logger.error('expected status o#{} {} == {}    outputs={}'.format(output_id, status, bool(current_status), state))
        self.observer.log_events()
        raise AssertionError('expected status o#{} {} == {}'.format(output_id, status, bool(current_status)))
