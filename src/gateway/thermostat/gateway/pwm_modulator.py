import time
from threading import Thread


class PwmModulator(object):

    def __init__(self, cycle_duration=15):
        """ Create a PWM modulator for a given output
        :param cycle_duration: The period of the PWM modulation in minutes
        :type cycle_duration: int
        """
        self._running = False
        self._reset = False
        self._loop_thread = False

        self._cycle_start = 0
        self._cycle_end = 0
        self._cycle_duration = int(cycle_duration) * 60

        self._t_step = self._cycle_duration / 100.0

        # avoid switching the output on for less than e.g. a minute
        self._state_change_timings = {}
        self._state_change_callbacks = {}

    def start(self):
        if not self._running:
            self._loop_thread = Thread(target=self._loop)
            self._loop_thread.daemon = True
            self._loop_thread.start()
        else:
            raise RuntimeError('PwmModulator already running. Please stop it first.')

    def stop(self):
        self._running = False

    def is_active(self):
        return self._status_active

    def _calc_pwm_timings(self):
        now = time.time()
        self._cycle_start = now
        self._cycle_end = now + self._cycle_duration

    def _loop(self):
        while self._running:
            now = time.time()
            if now > self._cycle_end or self._reset:
                self._reset = False
                self._calc_pwm_timings()

            if self._cycle_start <= now < self._cycle_end:
                # clamp percentage between 0 and 100
                elapsed_percentage = (now - self._cycle_start) / self._cycle_duration
                elapsed_percentage = int(max(min(elapsed_percentage, 100), 0))

                if elapsed_percentage != 0 and elapsed_percentage != 100:
                    callbacks = self._state_change_callbacks[elapsed_percentage]
                    self._call_back(callbacks)
            time.sleep(self._t_step)

    def _call_back(self, callbacks, value):
        if self._status_active != desired_state:
            self._status_active = desired_state
            for callback in self._state_change_callbacks:
                callback(self._status_active)

    def register_callback(self, method, duty_cycle):
        duty_cycle = int(duty_cycle)
        if 0 <= duty_cycle <= 100:
            self._state_change_callbacks.setdefault(duty_cycle, []).append(method)
        else:
            raise ValueError('Duty cycle must be a value between 0 and 100')