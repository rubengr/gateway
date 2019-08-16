import requests
import logging

from requests import Timeout

try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger('openmotics')


class Client(object):
    """
    The openmotics cloud client
    """

    API_TIMEOUT = 5.0

    def __init__(self, gateway_uuid, cloud_endpoint=None, api_version=0):
        self._gateway_uuid = gateway_uuid
        self._cloud_endpoint = 'cloud.openmotics.com' if cloud_endpoint is None else cloud_endpoint
        self.api_version = api_version
        self.api_retries = 3

    def send_event(self, event):
        if self.api_version != 0:
            raise NotImplementedError('Sending events is not supported on this api version')
        events_endpoint = 'https://{0}/{1}?uuid={2}'.format(self._cloud_endpoint, 'portal/events/', self._gateway_uuid)
        return self._post(events_endpoint, data={'event': json.dumps(event.serialize())})

    def _post(self, endpoint, data, timeout=API_TIMEOUT):
        logger.debug('POST {0}'.format(endpoint))
        for attempt in xrange(1, self.api_retries+1):
            try:
                response = requests.post(endpoint,
                                         data=data,
                                         timeout=timeout)
                return json.loads(response)
            except Exception:
                logger.warning('Retrying {}/{}: POST {}'.format(attempt, self.api_retries, endpoint))
                if attempt >= self.api_retries:
                    raise

