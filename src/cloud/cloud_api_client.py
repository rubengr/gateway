from platform_utils import System
System.import_eggs()
import logging
import requests
from wiring import inject, provides, SingletonScope, scope
from requests import ConnectionError
from requests.adapters import HTTPAdapter
try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger('openmotics')


class APIException(Exception):
    """Raised when there was en error communicating with the cloud"""
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

    def send_event(self, event, timeout=2.0):
        # sending events over REST is only supported in the v0 API
        if self.api_version != 0:
            raise NotImplementedError('Sending events is not supported on this api version')

        # make request
        events_endpoint = self._get_endpoint('portal/events/')
        query_params = {'uuid': self._gateway_uuid}
        try:
            response = self._session.post(events_endpoint, params=query_params, data={'event': json.dumps(event.serialize())}, timeout=timeout)
            if not response:
                raise APIException('Error while sending {} to {}. HTTP Status: {}'.format(event.type, self._hostname, response.status_code))
            return json.loads(response.text)
        except APIException:
            raise
        except ConnectionError as ce:
            raise APIException('Error while sending {} to {}. Reason: {}'.format(event.type, self._hostname, ce))
        except Exception as e:
            logger.exception(e)
            raise APIException('Unknown error while executing API request on {}. Reason: {}'.format(self._hostname, e))

    def send_metrics(self, metrics, timeout=30.0):
        # sending events over REST is only supported in the v0 API
        if self.api_version != 0:
            raise NotImplementedError('Sending metrics is not supported on this api version')

        # make request
        metrics_endpoint = self._get_endpoint('portal/metrics/')
        query_params = {'uuid': self._gateway_uuid}
        try:
            metrics = [[metric] for metric in metrics] # backwards compatibility format (list of lists)
            response = self._session.post(metrics_endpoint, params=query_params, data={'metrics': json.dumps(metrics)}, timeout=timeout)
            if not response:
                raise APIException('Error while sending {} metrics to {}. HTTP Status: {}'.format(len(metrics), self._hostname, response.status_code))
            return_data = json.loads(response.text)
            if return_data.get('success', False) is False:
                raise APIException('Error while sending {} metrics to {}. Error: {}'.format(len(metrics), self._hostname, return_data.get('error', 'unknown')))
            return return_data
        except APIException:
            raise
        except ConnectionError as ce:
            raise APIException('Error while sending {} metrics to {}. Reason: {}'.format(len(metrics), self._hostname, ce))
        except Exception as e:
            logger.exception(e)
            raise APIException('Unknown error while executing API request on {}. Reason: {}'.format(self._hostname, e))
