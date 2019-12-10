import time
import logging
from threading import Thread
from peewee import DoesNotExist
from gateway.thermostat.models import Output, DaySchedule, Preset, Thermostat
from gateway.thermostat.thermostat_controller import ThermostatController
from gateway.thermostat.thermostat_pid import ThermostatPid

logger = logging.getLogger('openmotics')


class GatewayThermostatController(ThermostatController):

    THERMOSTAT_PID_UPDATE_INTERVAL = 60

    def __init__(self, gateway_api, message_client, observer, master_communicator, eeprom_controller):
        super(GatewayThermostatController, self).__init__(gateway_api, message_client, observer, master_communicator,
                                                          eeprom_controller)
        self._running = False
        self._loop_thread = None
        self.thermostats = {}

    def start(self):
        if not self._running:
            self._loop_thread = Thread(target=self._tick)
            self._loop_thread.daemon = True
            self._loop_thread.start()
        else:
            raise RuntimeError('GatewayThermostatController already running. Please stop it first.')

    def stop(self):
        if not self._running:
            logger.warning('Stopping an already stopped GatewayThermostatController.')
        self._running = False

    def refresh_thermostats(self):
        configured_thermostats = set([thermostat.number for thermostat in Thermostat.select()])
        running_thermostats = set([thermostat_pid.number for thermostat_pid in self.thermostat_pids])

        thermostat_numbers_to_add = configured_thermostats.difference(running_thermostats)
        thermostat_numbers_to_remove = running_thermostats.difference(configured_thermostats)

        for number in thermostat_numbers_to_remove:
            thermostat_pid = self.thermostat_pids.get(number)
            thermostat_pid.stop()
            del thermostat_pid[number]

        for number in thermostat_numbers_to_add:
            new_thermostat = Thermostat.get(number=number)
            new_thermostat_pid = ThermostatPid(new_thermostat, self._gateway_api)
            self.thermostat_pids[number] = new_thermostat_pid

        self.thermostat_pids =

    def _tick(self):
        while self._running:
            for thermostat_number, thermostat_pid in self.thermostat_pids.iteritems():
                try:
                    thermostat_pid.tick()
                except Exception:
                    logger.exception('There was a problem with calculating thermostat PID {}'.format(thermostat_pid))
            time.sleep(self.THERMOSTAT_PID_UPDATE_INTERVAL)

    def set_thermostat_mode(self, thermostat_on, cooling_mode=False, cooling_on=False, automatic=None, setpoint=None):
        for thermostat_number, thermostat_pid in self.thermostat_pids.iteritems():
            thermostat_pid.enabled = thermostat_on
            thermostat_pid.mode = 'cooling' if cooling_mode else 'heating'
            if automatic:
                thermostat_pid.automatic = automatic

            thermostat = thermostat_pid.thermostat
            thermostat.enabled = thermostat_on


    def set_current_setpoint(self, thermostat_number, temperature):
        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        thermostat_pid.setpoint = temperature
        return {'status': 'OK'}

    def get_thermostat_configurations(self, fields=None):
        # TODO: implement the new v1 config format
        thermostats = Thermostat.select()
        return [thermostat.to_v0_format(fields) for thermostat in thermostats]

    def get_thermostat_configuration(self, thermostat_number, fields=None):
        # TODO: implement the new v1 config format
        thermostat = Thermostat.get(number=thermostat_number)
        return thermostat.to_v0_format(fields)

    def set_thermostat_configurations(self, config):
        # TODO: implement the new v1 config format
        for thermostat_config in config:
            self.set_thermostat_configuration(thermostat_config)

    def set_thermostat_configuration(self, config):
        # TODO: implement the new v1 config format
        GatewayThermostatController._create_or_update_thermostat_from_vo_api(config)

    def _refresh_thermostat_pid(self, thermostat):
        thermostat_pid = self.thermostat_pids.get(thermostat.number)
        if thermostat_pid is None:
            self.thermostat_pids[thermostat.number] = Thermostat(thermostat, self._gateway_api)
        else:
            thermostat_pid.switch_off()

    @staticmethod
    def _create_or_update_thermostat_from_vo_api(config):
        # we don't get a start date, calculate last monday night to map the schedules
        now = int(time.time())
        day_of_week = (now / 86400 - 4) % 7  # 0: Monday, 1: Tuesday, ...
        last_monday_night = now - now % 86400 - day_of_week * 86400

        thermostat_number = int(config['id'])
        thermo = Thermostat.get_or_create(number=thermostat_number)

        thermo.number = thermostat_number
        thermo.name = config['name']
        thermo.sensor = int(config['sensor'])
        thermo.pid_p = float(config['pid_p'])
        thermo.pid_i = float(config['pid_i'])
        thermo.pid_d = float(config['pid_d'])
        thermo.automatic = bool(config['permanent_manual'])
        thermo.room = int(config['room'])
        thermo.start = last_monday_night

        thermo = Thermostat(number=thermostat_number,
                            name=config['name'],
                            sensor=int(config['sensor']),
                            pid_p=float(config['pid_p']),
                            pid_i=float(config['pid_i']),
                            pid_d=float(config['pid_d']),
                            automatic=bool(config['permanent_manual']),
                            room=int(config['room']),
                            start=last_monday_night)
        thermo.save()

        for field in ['output0', 'output1']:
            output = Output.get_or_create(output_nr=int(config[field]))
            output.thermostat = thermo
            output.save()

        for (day_index, key) in [(0, 'auto_mon'),
                                 (1, 'auto_tue'),
                                 (2, 'auto_wed'),
                                 (3, 'auto_thu'),
                                 (4, 'auto_fri'),
                                 (5, 'auto_sat'),
                                 (6, 'auto_sun')]:
            v0_dict = config[key]
            day_schedule = DaySchedule.from_v0_dict(thermostat=thermo, day_index=day_index, v0_dict=v0_dict)
            day_schedule.save()

        away = Preset(name='AWAY', temperature=float(config['setp3']), thermostat=thermo)
        away.save()
        vacation = Preset(name='VACATION', temperature=float(config['setp4']), thermostat=thermo)
        vacation.save()
        party = Preset(name='PARTY', temperature=float(config['setp5']), thermostat=thermo)
        party.save()
