import time
from threading import Thread


class PumpController(object):

    def __init__(self, output, gateway_api):
        """ Create a pump object
        :param output: The output used to drive the valve
        :type output: int
        :param gateway_api: The gateway HAL
        :type gateway_api: gateway.gateway_api
        """
        self._output = output
        self._gateway_api = gateway_api
        self._pumps = []

    def turn_on(self, pump_id):
        pump = self._pumps[pump_id]

        pump.check_valves()


    def turn_off(self, pump_id):
        pump = self._pumps[pump_id]

    def run(self):
        if not self._running:
            self._loop_thread = Thread(target=self._loop)
            self._loop_thread.daemon = True
            self._loop_thread.start()
        else:
            raise RuntimeError('PumpController already running. Please stop it first.'.format(self._output))

    def _loop(self):
        while self._running:
            now = time.time()
            if now > self._cycle_end or self._reset:
                self._reset = False
                self._calc_pwm_timings()
            if self._cycle_start <= now < self._cycle_end:
                desired_state = True if now < self._cycle_toggle else False
                self._gateway_api.set_output(self._output, desired_state)
            time.sleep(self._cycle_min_on_time)


class Pump(object):

    def __init__(self, output, valves, gateway_api):
        """ Create a pump object
        :param output: The output used to drive the valve
        :type output: int
        :param valves: The list of valves connected to this pump
        :type valves: list
        :param gateway_api: The gateway HAL
        :type gateway_api: gateway.gateway_api
        """
        self._output = output
        self._valves = valves
        self._gateway_api = gateway_api

    def valves_open(self):
        return any([valve.is_open() for valve in self._valves])

    def _set_active(self, active):
        dimmable_output = self._gateway_api.get_output_configuration(self._output, fields='module_type').get('module_type') not in ['d', 'D']
        if dimmable_output:
            dimmer = 100 if active else 0
            self._gateway_api.set_output(self._output, is_on=active, dimmer=dimmer)
        else:
            self._gateway_api.set_output(self._output, is_on=active)

    def turn_on(self):
        if self.valves_open():
            self._set_active(True)
        else:
            raise RuntimeError('Cannot turn on pump {} since no attached valves are open.'.format(self._output))

    def turn_off(self):
        self._set_active(False)
