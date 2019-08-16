from platform_utils import System
System.import_eggs()
import logging
import requests
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


class Client(object):
    """
    The openmotics cloud client
    """

    API_TIMEOUT = 5.0

    def __init__(self, gateway_uuid, hostname=None, port=443, api_version=0, ssl=True):
        self._gateway_uuid = gateway_uuid
        self._hostname = 'cloud.openmotics.com' if hostname is None else hostname
        self._ssl = ssl
        self._port = port
        self.api_version = api_version

        self._session = requests.Session()
        openmotics_adapter = HTTPAdapter(max_retries=3)
        self._session.mount(self._hostname, openmotics_adapter)

    def _get_endpoint(self, path):
        return '{0}://{1}:{2}/{3}'.format('https' if self._ssl else 'http', self._hostname, self._port, path)

    def send_event(self, event):
        # sending events over REST is only supported in the v0 API
        if self.api_version != 0:
            raise NotImplementedError('Sending events is not supported on this api version')

        # make request
        events_endpoint = self._get_endpoint('portal/events/')
        query_params = {'uuid': self._gateway_uuid}
        try:
            response = self._session.post(events_endpoint, params=query_params, data={'event': json.dumps(event.serialize())}, timeout=2)
            if not response:
                raise APIException('Error while sending {} to {}. HTTP Status: {}'.format(event.type, self._hostname, response.status_code))
        except ConnectionError as ce:
            raise APIException('Error while sending {} to {}. Reason: {}'.format(event.type, self._hostname, ce))
