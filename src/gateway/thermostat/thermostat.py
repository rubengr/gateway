#!/usr/bin/env python
import time
from threading import Thread, Lock
from simple_pid import PID
from wiring import inject


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


class Valve(object):

    VALVE_DELAY = 60  # opening of the valve might take a while

    def __init__(self, gateway_api, output, use_pwm=True):
        """ Create a valve object
        :param gateway_api: The gateway HAL
        :type gateway_api: gateway.gateway_api
        :param output: The output used to drive the valve
        :type output: int
        :param cycle_duration: The period of the PWM modulation in minutes
        :type cycle_duration: int
        """
        self._gateway_api = gateway_api
        self._output = output
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
                self._gateway_api.set_output_dimmer(self._output, self._percentage)


class Thermostat(object):

    DEFAULT_KP = 5.0
    DEFAULT_KI = 0.0
    DEFAULT_KD = 2.0

    @inject(gateway_api='gateway_api')
    def __init__(self, thermostat_id, thermostat_group, sensor, heating_valves, cooling_valves, setpoint, gateway_api):
        self._thermostat_id = thermostat_id
        self._sensor = sensor
        self._heating_valves = heating_valves
        self._cooling_valves = cooling_valves
        self._pid = PID(self.DEFAULT_KP, self.DEFAULT_KI, self.DEFAULT_KD, setpoint=setpoint)
        self._running = False
        self._gateway_api = gateway_api
        self._loop_thread = False
        self.cooling_mode = False
        self.automatic = False
        self.thermostat_group = thermostat_group

    def run(self):
        if not self._running:
            self._pid.output_limits = (-100, 100)
            self._loop_thread = Thread(target=self._loop)
            self._loop_thread.daemon = True
            self._loop_thread.start()
        else:
            raise RuntimeError('Thermostat {} already running. Please stop it first.'.format(self._thermostat_id))

    def stop(self):
        self._running= False

    def _open_valves_cascade(self, total_percentage, valves):
        n_valves = len(valves)
        percentage_per_valve = 100.0 / n_valves
        n_valves_fully_open = int(total_percentage / percentage_per_valve)
        last_valve_open_percentage = (total_percentage - n_valves_fully_open * percentage_per_valve) / percentage_per_valve
        for n in xrange(n_valves_fully_open):
            valve = valves[n]
            valve.set(100)
        for n in xrange(n_valves_fully_open, n_valves):
            valve = valves(n)
            percentage = last_valve_open_percentage if n == n_valves_fully_open else 0
            valve.set(percentage)

    def _open_valves_equal(self, percentage, valves):
        n_valves = len(valves)
        for n in xrange(n_valves):
            valve = valves[n]
            valve.set(percentage)

    def _open_valves(self, percentage, valves):
        self._open_valves_equal(percentage, valves)

    def steer(self, power):
        if power > 0:
            # TODO: check union to avoid opening same valves in heating and cooling
            self._open_valves(0, self._cooling_valves)
            self._open_valves(power, self._heating_valves)
        else:
            self._open_valves(0, self._heating_valves)
            self._open_valves(power, self._cooling_valves)

    def switch_off(self):
        self.steer(0)

    def _loop(self):
        while self._running:
            current_temperature = self._sensor.read_temperature()
            output_power = self._pid(current_temperature)

            # heating needed while in cooling mode OR
            # cooling needed while in heating mode
            # -> no active aircon required, rely on losses of system to reach equilibrium
            if (self.cooling_mode and output_power > 0) or (not self.cooling_mode and output_power < 0):
                output_power = 0
            self.steer(output_power)
            time.sleep(60)
        self.switch_off()

    @property
    def setpoint(self):
        return self._pid.setpoint

    @setpoint.setter
    def setpoint(self, setpoint):
        self._pid.setpoint = setpoint

    @property
    def is_on(self):
        return self._running

    def set_thermostat_mode(self, thermostat_on, cooling_mode=False, automatic=None, setpoint=None):
        """ Set the mode of the thermostats.
        :param thermostat_on: Whether the thermostats are on
        :type thermostat_on: boolean
        :param cooling_mode: Cooling mode (True) of Heating mode (False)
        :type cooling_mode: boolean | None
        :param automatic: Indicates whether the thermostat system should be set to automatic
        :type automatic: boolean | None
        :param setpoint: Requested setpoint (integer 0-5)
        :type setpoint: int | None
        :returns: dict with 'status'
        """
        self._running = thermostat_on
        self.cooling_mode = cooling_mode
        self.automatic = automatic
        self.setpoint(setpoint)

    @property
    def Kp(self):
        return self._pid.Kp

    @Kp.setter
    def Kp(self, Kp):
        self._pid.Kp = Kp

    @property
    def Ki(self):
        return self._pid.Ki

    @Ki.setter
    def Ki(self, Ki):
        self._pid.Ki = Ki

    @property
    def Kd(self):
        return self._pid.Kd

    @Kd.setter
    def Kd(self, Kd):
        self._pid.Kd = Kd

    def update_pid_params(self, Kp, Ki, Kd):
        self._pid.tunings = (Kp, Ki, Kd)
