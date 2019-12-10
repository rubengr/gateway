import time
from threading import Thread, Lock
from simple_pid import PID
from wiring import inject


class Thermostat(object):

    DEFAULT_KP = 5.0
    DEFAULT_KI = 0.0
    DEFAULT_KD = 2.0

    @inject(gateway_api='gateway_api')
    def __init__(self, thermostat_id, thermostat_group, sensor, heating_valves, cooling_valves, setpoint, gateway_api):
        self._thermostat_id = thermostat_id
        self._sensor_id = sensor
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
            current_temperature = self._gateway_api.get_sensor_temperature_status(self._sensor_id)
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
