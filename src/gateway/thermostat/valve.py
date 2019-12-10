import time
from threading import Lock

from gateway.thermostat.pwm_modulator import PwmModulator


class Valve(object):

    VALVE_DELAY = 60  # opening of the valve might take a while

    def __init__(self, output_nr, gateway_api, use_pwm=True):
        """ Create a valve object
        :param gateway_api: The gateway HAL
        :type gateway_api: gateway.gateway_api.GatewayApi
        :param output: The output used to drive the valve
        :type output: int
        :param cycle_duration: The period of the PWM modulation in minutes
        :type cycle_duration: int
        """
        self._gateway_api = gateway_api
        self._output_nr = output_nr
        self._pwm_modulator = None

        self._percentage = 0

        # helper variables for determining if the valve is physically open (real world delay) e.g. when using PWM
        self._open = False
        self._time_state_changed = None
        self._state_change_lock = Lock()

        if use_pwm:
            min_on_time = 2 * self.VALVE_DELAY
            self._pwm_modulator = PwmModulator(min_on_time=min_on_time)
            self._pwm_modulator.register_state_change_callback(self._change_state)
            self._pwm_modulator.start()

    def _change_state(self, open):
        with self._state_change_lock:
            if self._open != open:
                self._open = open
                self._time_state_changed = time.time()

    def is_open(self):
        return self._open if not self.in_transition() else False

    def in_transition(self):
        with self._state_change_lock:
            now = time.time()
            if self._time_state_changed is not None:
                return self._time_state_changed + self.VALVE_DELAY > now
            else:
                return False

    def set(self, percentage):
        if self._percentage != percentage:
            self._percentage = percentage
            if self._pwm_modulator is not None:
                self._pwm_modulator.duty_cycle = self._percentage
                # self._change_state needs to be triggered by PWM callback
            else:
                is_open = percentage > 0
                self._change_state(is_open)
                self._gateway_api.set_output_dimmer(self._output_nr, self._percentage)
