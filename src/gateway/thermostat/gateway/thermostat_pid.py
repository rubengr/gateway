import logging
from threading import Lock
from simple_pid import PID
from serial_utils import CommunicationTimedOutException

logger = logging.getLogger('openmotics')


class ThermostatPid(object):

    DEFAULT_KP = 5.0
    DEFAULT_KI = 0.0
    DEFAULT_KD = 2.0

    def __init__(self, thermostat, pump_valve_controller, gateway_api):
        self._gateway_api = gateway_api
        self._pump_valve_controller = pump_valve_controller
        self._thermostat_change_lock = Lock()
        self._heating_valve_numbers = []
        self._cooling_valve_numbers = []
        self._report_state_callbacks = []
        self._pid = None
        self._thermostat = None
        self._mode = None
        self._active_preset = None
        self._current_temperature = None
        self._errors = 0
        self.update_thermostat(thermostat)

    @property
    def enabled(self):
        # 1. PID loop is initialized
        # 2. sensor is valid
        # 3. outputs configured (heating or cooling)
        if self._mode is None or self._pid is None:
            return False
        if self._active_preset is None:
            return False
        if self._thermostat.sensor == 255:
            return False
        if len(self._heating_valve_numbers) == 0 and len(self._cooling_valve_numbers) == 0:
            return False
        if not self._thermostat.thermostat_group.on:
            return False
        if self._errors > 5:
            return False
        return True

    @property
    def valve_numbers(self):
        return self.heating_valve_numbers + self.cooling_valve_numbers

    @property
    def heating_valve_numbers(self):
        return self._heating_valve_numbers

    @property
    def cooling_valve_numbers(self):
        return self._cooling_valve_numbers

    def update_thermostat(self, thermostat):
        with self._thermostat_change_lock:
            # cache these values to avoid DB lookups on every tick
            self._mode = thermostat.mode
            self._active_preset = thermostat.active_preset

            self._heating_valve_numbers = [valve.number for valve in thermostat.heating_valves]
            self._cooling_valve_numbers = [valve.number for valve in thermostat.cooling_valves]

            if thermostat.mode == 'heating':
                pid_p = thermostat.pid_heating_p if thermostat.pid_heating_p else self.DEFAULT_KP
                pid_i = thermostat.pid_heating_i if thermostat.pid_heating_i else self.DEFAULT_KI
                pid_d = thermostat.pid_heating_d if thermostat.pid_heating_d else self.DEFAULT_KD
                setpoint = self._active_preset.heating_setpoint if self._active_preset is not None else 14.0
            else:
                pid_p = thermostat.pid_cooling_p if thermostat.pid_cooling_p else self.DEFAULT_KP
                pid_i = thermostat.pid_cooling_i if thermostat.pid_cooling_i else self.DEFAULT_KI
                pid_d = thermostat.pid_cooling_d if thermostat.pid_cooling_d else self.DEFAULT_KD
                setpoint = self._active_preset.cooling_setpoint if self._active_preset is not None else 30.0

            if self._pid is None:
                self._pid = PID(pid_p, pid_i, pid_d, setpoint=setpoint)
            else:
                self._pid.tunings = (pid_p, pid_i, pid_d)
                self._pid.setpoint = setpoint
            self._pid.output_limits = (-100, 100)
            self._thermostat = thermostat
            self._errors = 0

    @property
    def thermostat(self):
        return self._thermostat

    def subscribe_state_changes(self, callback):
        """
        Subscribes a callback to generic events
        :param callback: the callback to call
        """
        self._report_state_callbacks.append(callback)

    def report_state_change(self):
        for callback in self._report_state_callbacks:
            callback(self.number, self._active_preset.name, self.setpoint, self.current_temperature,
                     self.get_active_valves_percentage(), self.thermostat.room)

    def tick(self):
        logger.info('_pid_tick - thermostat {} is {} enabled in {} mode'.format(self.thermostat.number, '' if self.enabled else 'not', self._mode))
        if self.enabled:
            logger.info('_pid_tick - thermostat {}: preset {} with setpoint {}'.format(self.thermostat.number,
                                                                                       self._active_preset.name,
                                                                                       self._pid.setpoint))
            try:
                current_temperature = self._gateway_api.get_sensor_temperature_status(self.thermostat.sensor)
                if current_temperature is not None:
                    self._current_temperature = current_temperature
                else:
                    # keep using old temperature reading and count the errors
                    logger.warning('_pid_tick - thermostat {}: invalid temperature reading {}, using last known value {}'
                                   .format(self.thermostat.number, current_temperature, self._current_temperature))
                    self._errors += 1

                if self._current_temperature is not None:
                    output_power = self._pid(self._current_temperature)
                else:
                    logger.error('_pid_tick - thermostat {}: cannot calculate thermostat output power due to invalid temperature reading: {}'
                                 .format(self.thermostat.number, self._current_temperature))
                    self._errors += 1
                    output_power = 0

                # heating needed while in cooling mode OR
                # cooling needed while in heating mode
                # -> no active aircon required, rely on losses of system to reach equilibrium
                if (self._mode == 'cooling' and output_power > 0) or \
                   (self._mode == 'heating' and output_power < 0):
                    output_power = 0
                self.steer(output_power)
                self.report_state_change()
            except CommunicationTimedOutException as ex:
                logger.error('Error in PID tick for thermostat {}: {}'.format(self.thermostat.number, str(ex)))
                self._errors += 1
        else:
            self.switch_off()

    def get_active_valves_percentage(self):
        return [self._pump_valve_controller.get_valve_driver(valve.number).percentage for valve in self.thermostat.active_valves]

    @property
    def errors(self):
        return self._errors

    @property
    def number(self):
        return self.thermostat.number

    @property
    def setpoint(self):
        return self._pid.setpoint

    @property
    def current_temperature(self):
        return self._current_temperature

    def steer(self, power):
        logger.info('PID steer - power {} '.format(power))

        # configure valves and set desired opening
        if power > 0:
            # TODO: check union to avoid opening same valve_numbers in heating and cooling
            self._pump_valve_controller.set_valves(0, self.cooling_valve_numbers, mode=self.thermostat.valve_config)
            self._pump_valve_controller.set_valves(power, self.heating_valve_numbers, mode=self.thermostat.valve_config)
        else:
            self._pump_valve_controller.set_valves(0, self.heating_valve_numbers, mode=self.thermostat.valve_config)
            # convert power to positive value for opening cooling valve_numbers
            self._pump_valve_controller.set_valves(abs(power), self.cooling_valve_numbers, mode=self.thermostat.valve_config)

        # effectively steer pumps and valves according to needs
        self._pump_valve_controller.steer()

    def switch_off(self):
        self.steer(0)

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
