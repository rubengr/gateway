import requests
import logging

try:
    import json
except ImportError:
    import simplejson as json

logger = logging.getLogger('openmotics')


class Client(object):
    """
    The openmotics cloud client
    """

    def __init__(self, config_controller):
        self._config_controller = config_controller

    def send_event(self, gateway_uuid, event):
        events_endpoint = 'https://{0}/{1}?uuid={2}'.format(
            self._config_controller.get_setting('cloud_endpoint'),
            self._config_controller.get_setting('cloud_endpoint_events'),
            gateway_uuid
        )
        logger.debug('POST {0}'.format(events_endpoint))
        request = requests.post(events_endpoint,
                                data={'event': json.dumps(event.serialize())},
                                timeout=3.0)
