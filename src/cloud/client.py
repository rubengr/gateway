from platform_utils import System
System.import_eggs()
import logging
import requests
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

    def __init__(self, gateway_uuid, cloud_endpoint=None, api_version=0):
        self._gateway_uuid = gateway_uuid
        self._cloud_endpoint = 'cloud.openmotics.com' if cloud_endpoint is None else cloud_endpoint
        self.api_version = api_version

        self._session = requests.Session()
        openmotics_adapter = HTTPAdapter(max_retries=3)
        self._session.mount(self._cloud_endpoint, openmotics_adapter)

    def send_event(self, event):
        # sending events over REST is only supported in the v0 API
        if self.api_version != 0:
            raise NotImplementedError('Sending events is not supported on this api version')

        # make request
        events_endpoint = 'https://{0}/{1}?uuid={2}'.format(self._cloud_endpoint, 'portal/events/', self._gateway_uuid)
        response = self._session.post(events_endpoint, data={'event': json.dumps(event.serialize())}, timeout=2)
        if not response:
            raise APIException('Error while sending event. Status code: {}'.format(response.status_code))