import logging
import time
from threading import Thread

logger = logging.getLogger('openmotics')


class PumpDriver(object):

    def __init__(self, pump, gateway_api):
        """ Create a pump object
        :param pump: the pump object
        :type pump: gateway.thermostat.gateway.models.Pump
        :param gateway_api: Gateway API Controller
        :type gateway_api: gateway.gateway_api.GatewayApi
        """
        self._pump = pump
        self._gateway_api = gateway_api
        self._state = None
        self._error = False

    def _set_state(self, active):
        output_number = self._pump.output.number
        dimmable_output = self._gateway_api.get_output_configuration(output_number, fields='module_type').get('module_type') in ['d', 'D']
        if dimmable_output:
            dimmer = 100 if active else 0
            self._gateway_api.set_output_dimmer(output_number, dimmer=dimmer)
        self._gateway_api.set_output_status(output_number, active)

    def turn_on(self):
        logger.info('turning on pump {}'.format(self._pump.number))
        try:
            self._set_state(True)
            self._state = True
            self._error = False
        except Exception as e:
            logger.exception('There was a problem turning on pump {}'.format(self._pump.number))
            self._error = True
            raise RuntimeError('Error turning on pump {}: {}'.format(self._pump.number, str(e)))

    def turn_off(self):
        logger.info('turning off pump {}'.format(self._pump.number))
        try:
            self._set_state(False)
            self._state = False
            self._error = False
        except Exception as e:
            logger.exception('There was a problem turning off pump {}'.format(self._pump.number))
            self._error = True
            raise RuntimeError('Error turning off pump {}: {}'.format(self._pump.number, str(e)))

    @property
    def state(self):
        return self._state

    @property
    def error(self):
        return self._error

    @property
    def number(self):
        return self._pump.number

    def __eq__(self, other):
        if not isinstance(other, PumpDriver):
            # don't attempt to compare against unrelated types
            return NotImplemented

        return self._pump.number == other.number
