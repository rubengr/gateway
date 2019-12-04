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
Cloud API Client
"""
import logging
import requests
import ujson as json
from wiring import inject, provides
from requests import ConnectionError
from requests.adapters import HTTPAdapter

logger = logging.getLogger('openmotics')


class APIException(Exception):
    """ Raised when there was en error communicating with the cloud """
    def __init__(self, message):
        super(APIException, self).__init__(message)


class CloudAPIClient(object):
    """
    The openmotics cloud client
    """

    API_TIMEOUT = 5.0

    @provides('cloud_api_client')
    @inject('gateway_uuid', endpoint='cloud_endpoint', port='cloud_port', api_version='cloud_api_version', ssl='cloud_ssl')
    def __init__(self, gateway_uuid, endpoint=None, port=443, api_version=0, ssl=True):
        self._gateway_uuid = gateway_uuid
        self._hostname = 'cloud.openmotics.com' if endpoint is None else endpoint
        self._ssl = True if ssl is None else ssl
        self._port = 443 if port is None else port
        self.api_version = 0 if api_version is None else api_version

        self._session = requests.Session()
        openmotics_adapter = HTTPAdapter(max_retries=3)
        self._session.mount(self._hostname, openmotics_adapter)

    def set_port(self, port):
        self._port = port

    def set_ssl(self, ssl):
        self._ssl = ssl

    def _get_endpoint(self, path):
        return '{0}://{1}:{2}/{3}'.format('https' if self._ssl else 'http', self._hostname, self._port, path)

    def send_event(self, event):
        self.send_events([event])

    def send_events(self, events):
        # sending events over REST is only supported in the v0 API
        if self.api_version != 0:
            raise NotImplementedError('Sending events is not supported on this api version')

        # make request
        events_endpoint = self._get_endpoint('portal/events/')
        query_params = {'uuid': self._gateway_uuid}
        try:
            response = self._session.post(events_endpoint, params=query_params, data={'events': json.dumps([event.serialize() for event in events])}, timeout=2)
            if not response:
                raise APIException('Error while sending events to {}. HTTP Status: {}'.format(self._hostname, response.status_code))
        except APIException:
            raise
        except ConnectionError as ce:
            raise APIException('Error while sending events to {}. Reason: {}'.format(self._hostname, ce))
        except Exception as e:
            logger.exception(e)
            raise APIException('Unknown error while executing API request on {}. Reason: {}'.format(self._hostname, e))

