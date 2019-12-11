import time
import logging
from threading import Thread
from peewee import DoesNotExist
from wiring import provides, scope, inject, SingletonScope

from gateway.thermostat.models import Output, DaySchedule, Preset, Thermostat, Database
from gateway.thermostat.thermostat_controller import ThermostatController
from gateway.thermostat.thermostat_pid import ThermostatPid

logger = logging.getLogger('openmotics')


class ThermostatControllerGateway(ThermostatController):

    THERMOSTAT_PID_UPDATE_INTERVAL = 5

    @provides('thermostat_controller')
    @scope(SingletonScope)
    @inject(gateway_api='gateway_api', message_client='message_client', observer='observer',
            master_communicator='master_communicator', eeprom_controller='eeprom_controller')
    def __init__(self, gateway_api, message_client, observer, master_communicator, eeprom_controller):
        super(ThermostatControllerGateway, self).__init__(gateway_api, message_client, observer, master_communicator,
                                                          eeprom_controller)
        self._running = False
        self._loop_thread = None
        self.thermostat_pids = {}

    def start(self):
        if not self._running:
            self.refresh_thermostats()
            self._running = True
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
        thermostat_number = int(config['id'])
        thermostat = ThermostatControllerGateway._create_or_update_thermostat_from_vo_api(thermostat_number, config)
        self._refresh_thermostat_pid(thermostat_number, thermostat)

    def get_pump_group_configurations(self, fields=None):
        pass

    def _refresh_thermostat_pid(self, thermostat_number, thermostat):
        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        if thermostat_pid is not None:
            thermostat_pid.stop()
        self.thermostat_pids[thermostat_number] = ThermostatPid(thermostat, self._gateway_api)

    @staticmethod
    def _create_or_update_thermostat_from_vo_api(thermostat_number, config):
        """
        :param thermostat_number: the thermostat number for which the config needs to be stored
        :type thermostat_number: int
        :param config: the v0 config dict e.g. {'auto_wed': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'auto_mon': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'output0': 0, 'output1': 3, 'room': 255, 'id': 2, 'auto_sat': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'sensor': 0, 'auto_sun': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'auto_th': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'pid_int': 0, 'auto_tue': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'setp0': 20, 'setp5': 18, 'setp4': 18, 'pid_p': 120, 'setp1': 17, 'name': 'H - Thermostat 2', 'setp3': 18, 'setp2': 21, 'auto_fri': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'pid_d': 0, 'pid_i': 0}
        :type config: dict
        :returns the thermostat
        """

        {u'auto_wed': [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21],
         u'auto_mon': [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21],
         u'auto_thu': [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21],
         u'auto_sun': [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21],
         u'auto_sat': [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21],
         u'auto_tue': [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21],
         u'auto_fri': [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21], u'id': 1}

        logger.info('config {}'.format(config))
        # we don't get a start date, calculate last monday night to map the schedules
        now = int(time.time())
        day_of_week = (now / 86400 - 4) % 7  # 0: Monday, 1: Tuesday, ...
        last_monday_night = now - now % 86400 - day_of_week * 86400

        try:
            thermo = Thermostat.get(number=thermostat_number)
        except DoesNotExist:
            thermo = Thermostat(number=thermostat_number)
        thermo.name = config['name']
        thermo.sensor = int(config['sensor'])
        thermo.pid_p = float(config['pid_p'])
        thermo.pid_i = float(config['pid_i'])
        thermo.pid_d = float(config['pid_d'])
        thermo.room = int(config['room'])
        thermo.start = last_monday_night
        thermo.save()

        for field in ['output0', 'output1']:
            try:
                output = Output.get(output_nr=int(config[field]))
            except DoesNotExist:
                output = Output(output_nr=int(config[field]))
            output.thermostat = thermo
            output.priority = 0 if field == 'output0' else 1
            output.save()

        for (day_index, key) in [(0, 'auto_mon'),
                                 (1, 'auto_tue'),
                                 (2, 'auto_wed'),
                                 (3, 'auto_thu'),
                                 (4, 'auto_fri'),
                                 (5, 'auto_sat'),
                                 (6, 'auto_sun')]:
            v0_schedule = config[key]
            day_schedule = DaySchedule.from_v0_dict(thermostat=thermo, day_index=day_index, v0_schedule=v0_schedule)
            day_schedule.save()

        for (field, preset_name) in [('setp3', 'AWAY'),
                                     ('setp4', 'VACATION'),
                                     ('setp5', 'PARTY')]:
            try:
                preset = Preset.get(name=preset_name, thermostat=thermo)
            except DoesNotExist:
                preset = Preset(name=preset_name, thermostat=thermo)
            preset.temperature = float(config[field])
            preset.save()

        return thermo
