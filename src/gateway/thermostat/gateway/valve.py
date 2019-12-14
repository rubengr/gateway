import time
import logging
from threading import Lock
from gateway.thermostat.gateway.pwm_modulator import PwmModulator

logger = logging.getLogger('openmotics')


class Valve(object):

    def __init__(self, valve, gateway_api):
        """ Create a valve object
        :param gateway_api: The gateway HAL
        :type gateway_api: gateway.gateway_api.GatewayApi
        :param output: The output used to drive the valve
        :type output: int
        :param cycle_duration: The period of the PWM modulation in minutes
        :type cycle_duration: int
        """
        self._gateway_api = gateway_api
        self._valve = valve
        self._pwm_modulator = None

        self._percentage = 0

        # helper variables for determining if the valve is physically open (real world delay) e.g. when using PWM
        self._open = False
        self._time_state_changed = None
        self._state_change_lock = Lock()

        if valve.pwm:
            min_on_time = 2 * self._valve.delay
            self._pwm_modulator = PwmModulator(min_on_time=min_on_time)
            self._pwm_modulator.register_state_change_callback(self._change_state)
            self._pwm_modulator.start()

    def _change_state(self, open):
        with self._state_change_lock:
            if self._open != open:
                logger.info('changed valve state to {}'.format(open))
                self._open = open
                self._time_state_changed = time.time()

    def is_open(self):
        return self._open if not self.in_transition() else False

    def in_transition(self):
        with self._state_change_lock:
            now = time.time()
            if self._time_state_changed is not None:
                return self._time_state_changed + self._valve.delay > now
            else:
                return False

    def set(self, percentage):
        logger.info('setting valve percentage to {}'.format(percentage))
        if self._percentage != percentage:
            self._percentage = percentage
            if self._pwm_modulator is not None:
                self._pwm_modulator.duty_cycle = self._percentage
                # self._change_state needs to be triggered by PWM callback
            else:
                is_open = percentage > 0
                self._change_state(is_open)
                self._gateway_api.set_output_status(self._valve.output.number, is_open)
                self._gateway_api.set_output_dimmer(self._valve.output.number, self._percentage)
