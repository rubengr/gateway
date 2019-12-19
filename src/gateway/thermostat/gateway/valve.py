import time
import logging
from threading import Lock
from wiring import provides, scope, inject, SingletonScope

from gateway.thermostat.gateway.pump import Pump

logger = logging.getLogger('openmotics')


class Valve(object):

    def __init__(self, valve, gateway_api):
        """ Create a valve object
        :param gateway_api: Gateway API Controller
        :type gateway_api: gateway.gateway_api.GatewayApi
        :param output: The output used to drive the valve
        :type output: int
        :param cycle_duration: The period of the PWM modulation in minutes
        :type cycle_duration: int
        """
        self._gateway_api = gateway_api
        self._valve = valve
        self._percentage = 0

        self._current_percentage = 0
        self._desired_percentage = 0
        self._time_state_changed = None
        self._state_change_lock = Lock()

    @property
    def pumps(self):
        return [pump for pump in self._valve.pumps]

    def is_open(self):
        _open = self._current_percentage > 0
        return _open if not self.in_transition() else False

    def in_transition(self):
        with self._state_change_lock:
            now = time.time()
            if self._time_state_changed is not None:
                return self._time_state_changed + self._valve.delay > now
            else:
                return False

    def update_state(self):
        with self._state_change_lock:
            if self._current_percentage != self._desired_percentage:
                output_nr = self._valve.output.number
                logger.info('Valve (output: {}) changing from {}% --> {}%'.format(output_nr,
                                                                                  self._current_percentage,
                                                                                  self._desired_percentage))
                output_status = self._desired_percentage > 0
                self._gateway_api.set_output_status(self._valve.output.number, output_status)
                try:
                    dimmable_output = self._gateway_api.get_output_configuration(output_nr, fields='module_type').get('module_type') in ['d', 'D']
                except Exception:
                    dimmable_output = False
                if dimmable_output or self._percentage == 100:
                    self._gateway_api.set_output_dimmer(self._valve.output.number, self._desired_percentage)
                else:
                    # TODO: implement PWM logic
                    logger.info('Valve (output: {}) using ON/OFF approximation - desired: {}%'.format(output_nr, self._desired_percentage))
                self._current_percentage = self._desired_percentage
                self._time_state_changed = time.time()

    def set(self, percentage):
        _percentage = int(percentage)
        logger.info('setting valve {} percentage to {}'.format(self._valve.output.number, _percentage))
        if self._current_percentage != self._desired_percentage:
            self._desired_percentage = _percentage
            self.update_state()
