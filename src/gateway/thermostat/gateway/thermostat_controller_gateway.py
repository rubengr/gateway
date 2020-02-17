import datetime
import time
import logging
import constants
from threading import Thread
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from peewee import DoesNotExist
from playhouse.signals import post_save
from ioc import Injectable, Inject, Singleton, INJECTED
from bus.om_bus_events import OMBusEvents
from gateway.observer import Event
from models import Output, DaySchedule, Preset, Thermostat, ThermostatGroup, OutputToThermostatGroup, ValveToThermostat, Valve, Pump, Feature
from gateway.thermostat.gateway.pump_valve_controller import PumpValveController
from gateway.thermostat.thermostat_controller import ThermostatController
from gateway.thermostat.gateway.thermostat_pid import ThermostatPid
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger('openmotics')


@Injectable.named('thermostat_controller')
@Singleton
class ThermostatControllerGateway(ThermostatController):

    THERMOSTAT_PID_UPDATE_INTERVAL = 60
    PUMP_UPDATE_INTERVAL = 30
    SYNC_CONFIG_INTERVAL = 900

    @Inject
    def __init__(self, gateway_api=INJECTED, message_client=INJECTED, observer=INJECTED):
        super(ThermostatControllerGateway, self).__init__(gateway_api, message_client, observer)
        self._running = False
        self._pid_loop_thread = None
        self._update_pumps_thread = None
        self._periodic_sync_thread = None
        self.thermostat_pids = {}
        self._pump_valve_controller = PumpValveController()

        timezone = gateway_api.get_timezone()

        # we could also use an in-memory store, but this allows us to detect 'missed' transitions
        # e.g. in case when gateway was rebooting during a scheduled transition
        db_filename = constants.get_thermostats_scheduler_database_file()
        jobstores = {'default': SQLAlchemyJobStore(url='sqlite:///{})'.format(db_filename))}
        self._scheduler = BackgroundScheduler(jobstores=jobstores, timezone=timezone)

    def start(self):
        logger.info('Starting gateway thermostatcontroller...')
        if not self._running:
            self._running = True

            self.refresh_config_from_db()
            self._pid_loop_thread = Thread(target=self._pid_tick)
            self._pid_loop_thread.daemon = True
            self._pid_loop_thread.start()

            self._update_pumps_thread = Thread(target=self._update_pumps)
            self._update_pumps_thread.daemon = True
            self._update_pumps_thread.start()

            self._periodic_sync_thread = Thread(target=self._periodic_sync)
            self._periodic_sync_thread.daemon = True
            self._periodic_sync_thread.start()

            self._scheduler.start()
            logger.info('Starting gateway thermostatcontroller... Done')
        else:
            raise RuntimeError('GatewayThermostatController already running. Please stop it first.')

    def stop(self):
        if not self._running:
            logger.warning('Stopping an already stopped GatewayThermostatController.')
        self._running = False
        self._scheduler.shutdown(wait=False)
        self._pid_loop_thread.join()
        self._update_pumps_thread.join()
        self._periodic_sync_thread.join()

    def _pid_tick(self):
        while self._running:
            for thermostat_number, thermostat_pid in self.thermostat_pids.iteritems():
                try:
                    thermostat_pid.tick()
                except Exception:
                    logger.exception('There was a problem with calculating thermostat PID {}'.format(thermostat_pid))
            time.sleep(self.THERMOSTAT_PID_UPDATE_INTERVAL)

    def refresh_config_from_db(self):
        self.refresh_thermostats_from_db()
        self._pump_valve_controller.refresh_from_db()

    def refresh_thermostats_from_db(self):
        for thermostat in Thermostat.select():
            thermostat_pid = self.thermostat_pids.get(thermostat.number)
            if thermostat_pid is None:
                thermostat_pid = ThermostatPid(thermostat, self._pump_valve_controller)
                thermostat_pid.subscribe_state_changes(self.v0_event_thermostat_changed)
                self.thermostat_pids[thermostat.number] = thermostat_pid
            thermostat_pid.update_thermostat(thermostat)
            thermostat_pid.tick()
            # TODO: delete stale/removed thermostats

    def log_scheduler_jobs(self):
        logger.info('Scheduled jobs:')
        for job in self._scheduler.get_jobs():
            logger.info('- {}'.format(job))

    def _update_pumps(self):
        while self._running:
            try:
                time.sleep(self.PUMP_UPDATE_INTERVAL)
                self._pump_valve_controller.steer_pumps()
            except Exception:
                logger.exception('Could not update pumps.')

    def _periodic_sync(self):
        while self._running:
            try:
                time.sleep(self.SYNC_CONFIG_INTERVAL)
                self.refresh_config_from_db()
            except Exception:
                logger.exception('Could not get thermostat config.')

    def _sync_scheduler(self):
        self._scheduler.remove_all_jobs()
        for thermostat_number, thermostat_pid in self.thermostat_pids.iteritems():
            start_date = datetime.datetime.utcfromtimestamp(thermostat_pid.thermostat.start)
            day_schedules = thermostat_pid.thermostat.day_schedules
            schedule_length = len(day_schedules)
            for schedule in day_schedules:
                for seconds_of_day, new_setpoint in schedule.schedule_data.iteritems():
                    m, s = divmod(int(seconds_of_day), 60)
                    h, m = divmod(m, 60)
                    if schedule.mode == 'heating':
                        args = [thermostat_number, new_setpoint, None]
                    else:
                        args = [thermostat_number, None, new_setpoint]
                    if schedule_length % 7 == 0:
                        self._scheduler.add_job(ThermostatControllerGateway.set_setpoint_from_scheduler, 'cron',
                                                start_date=start_date,
                                                day_of_week=schedule.index,
                                                hour=h, minute=m, second=s,
                                                args=args,
                                                name='T{}: {} ({}) {}'.format(thermostat_number, new_setpoint, schedule.mode, seconds_of_day))
                    else:
                        # calendarinterval trigger is only supported in a future release of apscheduler
                        # https://apscheduler.readthedocs.io/en/latest/modules/triggers/calendarinterval.html#module-apscheduler.triggers.calendarinterval
                        day_start_date = start_date + datetime.timedelta(days=schedule.index)
                        self._scheduler.add_job(ThermostatControllerGateway.set_setpoint_from_scheduler, 'calendarinterval',
                                                start_date=day_start_date,
                                                days=schedule_length,
                                                hour=h, minute=m, second=s,
                                                args=args,
                                                name='T{}: {} ({}) {}'.format(thermostat_number, new_setpoint, schedule.mode, seconds_of_day))

    def migrate_master_config_to_gateway(self):
        # TODO: Migrate this code since it uses legacy master models and helpers such as eeprom controller and
        #  master communicator. This cannot be imported/used in Core+ context
        from master.eeprom_models import ThermostatConfiguration, CoolingConfiguration
        # validate if valid config
        # 1. output0 <= 240
        # 2. sensor < 32 or 240
        # 3. timing check e.g. '42:30' is not valid time (255)
        # 4. valid PID params

        def is_valid(config_):
            if config_.get('output0', 255) <= 240:
                return False
            if config_.get('pid_p', 255) == 255:
                return False
            sensor = config_.get('sensor', 255)
            if not (sensor < 32 or sensor == 240):
                return False
            for key, value in config_.iteritems():
                if key.startswith('auto_') and ('42:30' in value or 255 in value):
                    return False
            return True

        self._master_communicator.start()

        try:
            # 0. check if migration already done
            f = Feature.get(name='thermostats_gateway')
            if not f.enabled:
                # 1. try to read all config from master and save it in the db
                try:
                    for thermostat_id in xrange(32):
                        for mode, config_mapper in {'heating': ThermostatConfiguration,
                                                    'cooling': CoolingConfiguration}.iteritems():
                            config = self._eeprom_controller.read(config_mapper, thermostat_id).serialize()
                            if is_valid(config):
                                ThermostatControllerGateway.create_or_update_thermostat_from_v0_api(thermostat_id,
                                                                                                    config,
                                                                                                    mode)
                except Exception:
                    logger.exception('Error occurred while migrating thermostats configuration from master eeprom.')
                    return False

                # 2. disable all thermostats on the master
                try:
                    for thermostat_id in xrange(32):
                        # TODO: use new master API to disable thermostat
                        # self._master_communicator.xyz
                        pass
                except Exception:
                    logger.exception('Error occurred while stopping master thermostats.')
                    return False

                # 3. write flag in database to enable gateway thermostats
                f.enabled = True
                f.save()
            return True
        except Exception:
            logger.exception('Error migrating master thermostats')
            return False

    ################################
    # v1 APIs
    ################################

    def set_current_setpoint(self, thermostat_number, heating_temperature=None, cooling_temperature=None):
        if heating_temperature is None and cooling_temperature is None:
            return

        thermostat = Thermostat.get(number=thermostat_number)
        # when setting a setpoint manually, switch to manual preset except for when we are in scheduled mode
        # scheduled mode will override the setpoint when the next edge in the schedule is triggered
        active_preset = thermostat.active_preset
        if active_preset.name not in ['SCHEDULE', 'MANUAL']:
            active_preset = thermostat.get_preset('MANUAL')
            thermostat.active_preset = active_preset

        if heating_temperature is not None:
            active_preset.heating_setpoint = float(heating_temperature)
        if cooling_temperature is not None:
            active_preset.cooling_setpoint = float(cooling_temperature)
        active_preset.save()
        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        thermostat_pid.update_thermostat(thermostat)
        thermostat_pid.tick()

    def get_current_preset(self, thermostat_number):
        thermostat = Thermostat.get(number=thermostat_number)
        return thermostat.active_preset

    def set_current_preset(self, thermostat_number, preset_name):
        thermostat = Thermostat.get(number=thermostat_number)
        preset = thermostat.get_preset(preset_name)
        thermostat.active_preset = preset
        thermostat.save()

        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        thermostat_pid.update_thermostat(thermostat)
        thermostat_pid.tick()

    @classmethod
    @Inject
    def set_setpoint_from_scheduler(cls, thermostat_number, heating_temperature=None, cooling_temperature=None, thermostat_controller=INJECTED):
        logger.info('Setting setpoint from scheduler for thermostat {}: H{} C{}'.format(thermostat_number, heating_temperature, cooling_temperature))
        thermostat = Thermostat.get(number=thermostat_number)
        active_preset = thermostat.active_preset

        # only update when not in preset mode like away, party, ...
        if active_preset.name == 'SCHEDULE':
            thermostat_controller.set_current_setpoint(thermostat_number, heating_temperature, cooling_temperature)
        else:
            logger.info('Thermostat is currently in preset mode, skipping update setpoint from scheduler.')

    ################################
    # v0 compatible APIs
    ################################

    def v0_get_thermostat_status(self):
        """{'thermostats_on': True,
         'automatic': True,
         'setpoint': 0,
         'cooling': True,
         'status': [{'id': 0,
                     'act': 25.4,
                     'csetp': 23.0,
                     'outside': 35.0,
                     'mode': 198,
                     'automatic': True,
                     'setpoint': 0,
                     'name': 'Living',
                     'sensor_nr': 15,
                     'airco': 115,
                     'output0': 32,
                     'output1': 0}]}"""

        def get_output_level(output_number):
            if output_number is None:
                return 0  # we are returning 0 if outputs are not configured
            else:
                output = self._gateway_api.get_output_status(output_number)
                if output.get('dimmer') is None:
                    status_ = output.get('status')
                    output_level = 0 if status_ is None else int(status_) * 100
                else:
                    output_level = output.get('dimmer')
                return output_level

        global_thermostat = ThermostatGroup.get(number=0)
        if global_thermostat is not None:
            return_data = {'thermostats_on': global_thermostat.on,
                           'automatic': True,  # TODO: if any thermnostat is automatic
                           'setpoint': 0,      # can be ignored
                           'cooling': str(global_thermostat.mode).lower() == 'cooling'}
            status = []

            for thermostat in global_thermostat.thermostats:
                output_numbers = thermostat.v0_get_output_numbers()
                active_preset = thermostat.active_preset
                if global_thermostat.mode == 'cooling':
                    csetp = active_preset.cooling_setpoint if active_preset is not None else 30.0
                else:
                    csetp = active_preset.heating_setpoint if active_preset is not None else 14.0

                v0_setpoint = active_preset.get_v0_setpoint_id()

                data = {'id': thermostat.number,
                        'act': self._gateway_api.get_sensor_temperature_status(thermostat.sensor),
                        'csetp': csetp,
                        'outside': self._gateway_api.get_sensor_temperature_status(global_thermostat.sensor),
                        'mode': 0,  # TODO: !!!check if still used!!
                        'automatic': active_preset.name == 'SCHEDULE',
                        'setpoint': v0_setpoint,  # ---> 'AWAY': 3, 'VACATION': 4, ...
                        'name': thermostat.mode,
                        'sensor_nr': thermostat.sensor,
                        'airco': 0,  # TODO: !!!check if still used!!
                        'output0': get_output_level(output_numbers[0]),
                        'output1': get_output_level(output_numbers[1])
                        }
                status.append(data)

            return_data['status'] = status
            return return_data
        else:
            raise RuntimeError('Global thermostat not found!')

    def v0_set_thermostat_mode(self, thermostat_on, cooling_mode=False, cooling_on=False, automatic=None, setpoint=None):
        mode = 'cooling' if cooling_mode else 'heating'
        global_thermosat = ThermostatGroup.v0_get_global()
        global_thermosat.on = thermostat_on
        global_thermosat.mode = mode
        global_thermosat.save()

        for thermostat_number, thermostat_pid in self.thermostat_pids.iteritems():
            thermostat = Thermostat.get(number=thermostat_number)
            if thermostat is not None:
                if automatic is False and setpoint is not None and 3 <= setpoint <= 5:
                    thermostat.active_preset = Preset.get_by_thermostat_and_v0_setpoint(thermostat=thermostat, v0_setpoint=setpoint)
                else:
                    thermostat.active_preset = thermostat.get_preset('SCHEDULE')
                thermostat_pid.update_thermostat(thermostat)
                thermostat_pid.tick()
        return {'status': 'OK'}

    def v0_set_current_setpoint(self, thermostat_number, temperature):
        self.set_current_setpoint(thermostat_number, heating_temperature=temperature, cooling_temperature=temperature)
        return {'status': 'OK'}

    def v0_get_thermostat_configurations(self, fields=None):
        # TODO: implement the new v1 config format
        thermostats = Thermostat.select()
        return [thermostat.to_v0_format(mode='heating', fields=fields) for thermostat in thermostats]

    def v0_get_thermostat_configuration(self, thermostat_number, fields=None):
        # TODO: implement the new v1 config format
        thermostat = Thermostat.get(number=thermostat_number)
        return thermostat.to_v0_format(mode='heating', fields=fields)

    def v0_set_thermostat_configurations(self, config):
        # TODO: implement the new v1 config format
        for thermostat_config in config:
            self.v0_set_thermostat_configuration(thermostat_config)

    def v0_set_thermostat_configuration(self, config):
        self.v0_set_configuration(config, 'heating')

    def v0_get_cooling_configurations(self, fields=None):
        thermostats = Thermostat.select()
        return [thermostat.to_v0_format(mode='cooling', fields=fields) for thermostat in thermostats]

    def v0_get_cooling_configuration(self, cooling_id, fields=None):
        # TODO: implement the new v1 config format
        thermostat = Thermostat.get(number=cooling_id)
        return thermostat.to_v0_format(mode='cooling', fields=fields)

    def v0_set_cooling_configurations(self, config):
        # TODO: implement the new v1 config format
        for thermostat_config in config:
            self.v0_set_cooling_configuration(thermostat_config)

    def v0_set_cooling_configuration(self, config):
        self.v0_set_configuration(config, 'cooling')

    def v0_set_per_thermostat_mode(self, thermostat_number, automatic, setpoint):
        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        if thermostat_pid is not None:
            thermostat = thermostat_pid.thermostat
            thermostat.automatic = automatic
            thermostat.setpoint = setpoint
            thermostat.save()
            thermostat_pid.update_thermostat(thermostat)
            thermostat_pid.tick()
        return {'status': 'OK'}

    def v0_get_global_thermostat_configuration(self, fields=None):
        # TODO: implement this with sqlite as backing
        global_thermostat_group = ThermostatGroup.v0_get_global()
        config = {'outside_sensor': global_thermostat_group.sensor,
                  'pump_delay': 255,
                  'threshold_temp': global_thermostat_group.threshold_temp}

        cooling_outputs = global_thermostat_group.v0_switch_to_cooling_outputs
        n = len(cooling_outputs)
        for i in xrange(n):
            cooling_output = cooling_outputs[n]
            config['switch_to_cooling_output_{}'.format(i)] = cooling_output[0]
            config['switch_to_cooling_value_{}'.format(i)] = cooling_output[1]
        for i in xrange(n, 4-n):
            config['switch_to_cooling_output_{}'.format(i)] = 255
            config['switch_to_cooling_value_{}'.format(i)] = 255

        heating_outputs = global_thermostat_group.v0_switch_to_heating_outputs
        n = len(heating_outputs)
        for i in xrange(n):
            heating_output = heating_outputs[n]
            config['switch_to_heating_output_{}'.format(i)] = heating_output[0]
            config['switch_to_heating_value_{}'.format(i)] = heating_output[1]
        for i in xrange(n, 4-n):
            config['switch_to_heating_output_{}'.format(i)] = 255
            config['switch_to_heating_value_{}'.format(i)] = 255

        return config

    def v0_set_global_thermostat_configuration(self, config):
        # update thermostat group configuration
        thermostat_group = ThermostatGroup.get(number=0)
        thermostat_group.sensor = int(config['outside_sensor'])
        thermostat_group.threshold_temp = float(config['threshold_temp'])
        thermostat_group.save()

        # link configuration outputs to global thermostat config
        for mode in ['cooling', 'heating']:
            for i in xrange(4):
                full_key = 'switch_to_{}_output_{}'.format(mode, i)
                output_number = config.get(full_key)
                output = Output.get_or_create(number=output_number)

                output_to_thermostatgroup = OutputToThermostatGroup.get_or_create(output=output, thermostat_group=thermostat_group)
                output_to_thermostatgroup.index = i
                output_to_thermostatgroup.mode = mode
                output_to_thermostatgroup.save()

        # set valve delay for all valve_numbers in this group
        valve_delay = int(config['pump_delay'])
        for thermostat in thermostat_group.thermostats:
            for valve in thermostat.valve_numbers:
                valve.delay = valve_delay
                valve.save()

    def v0_get_pump_group_configuration(self, pump_number, fields=None):
        pump = Pump.get(number=pump_number)
        pump_config = {'id': pump.number,
                       'outputs': ','.join([valve.output.number for valve in pump.heating_valves]),
                       'output': pump.output.number,
                       'room': 255}
        return pump_config

    def v0_get_pump_group_configurations(self, fields=None):
        pump_config_list = []
        for pump in Pump.select():
            pump_config = {'id': pump.number,
                           'outputs': ','.join([valve.number for valve in pump.heating_valves]),
                           'output': pump.number,
                           'room': 255}
            pump_config_list.append(pump_config)
        return pump_config_list

    def v0_set_pump_group_configuration(self, config):
        raise NotImplementedError()

    def v0_set_pump_group_configurations(self, config):
        raise NotImplementedError()

    def v0_get_cooling_pump_group_configuration(self, pump_number, fields=None):
        pump = Pump.get(number=pump_number)
        pump_config = {'id': pump.number,
                       'outputs': ','.join([valve.output.number for valve in pump.cooling_valves]),
                       'output': pump.output.number,
                       'room': 255}
        return pump_config

    def v0_get_cooling_pump_group_configurations(self, fields=None):
        pump_config_list = []
        for pump in Pump.select():
            pump_config = {'id': pump.number,
                           'outputs': [valve.number for valve in pump.cooling_valves],
                           'output': pump.number,
                           'room': 255}
            pump_config_list.append(pump_config)
        return pump_config_list

    def v0_set_cooling_pump_group_configuration(self, config):
        raise NotImplementedError()

    def v0_set_cooling_pump_group_configurations(self, config):
        raise NotImplementedError()

    def v0_get_global_rtd10_configuration(self, fields=None):
        raise NotImplementedError()

    def v0_set_global_rtd10_configuration(self, config):
        raise NotImplementedError()

    def v0_get_rtd10_heating_configuration(self, heating_id, fields=None):
        raise NotImplementedError()

    def v0_get_rtd10_heating_configurations(self, fields=None):
        raise NotImplementedError()

    def v0_set_rtd10_heating_configuration(self, config):
        raise NotImplementedError()

    def v0_set_rtd10_heating_configurations(self, config):
        raise NotImplementedError()

    def v0_get_rtd10_cooling_configuration(self, cooling_id, fields=None):
        raise NotImplementedError()

    def v0_get_rtd10_cooling_configurations(self, fields=None):
        raise NotImplementedError()

    def v0_set_rtd10_cooling_configuration(self, config):
        raise NotImplementedError()

    def v0_set_rtd10_cooling_configurations(self, config):
        raise NotImplementedError()

    def v0_set_airco_status(self, thermostat_id, airco_on):
        raise NotImplementedError()

    def v0_get_airco_status(self):
        raise NotImplementedError()

    @staticmethod
    def create_or_update_thermostat_from_v0_api(thermostat_number, config, mode='heating'):
        """
        :param thermostat_number: the thermostat number for which the config needs to be stored
        :type thermostat_number: int
        :param config: the v0 config dict e.g. {'auto_wed': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'auto_mon': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'output0': 0, 'output1': 3, 'room': 255, 'id': 2, 'auto_sat': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'sensor': 0, 'auto_sun': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'auto_th': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'pid_int': 0, 'auto_tue': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'setp0': 20, 'setp5': 18, 'setp4': 18, 'pid_p': 120, 'setp1': 17, 'name': 'H - Thermostat 2', 'setp3': 18, 'setp2': 21, 'auto_fri': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'pid_d': 0, 'pid_i': 0}
        :type config: dict
        :param mode: heating or cooling
        :type mode: str
        :returns the thermostat
        """
        logger.info('config {}'.format(config))
        # we don't get a start date, calculate last monday night to map the schedules
        now = int(time.time())
        day_of_week = (now / 86400 - 4) % 7  # 0: Monday, 1: Tuesday, ...
        last_monday_night = now - now % 86400 - day_of_week * 86400

        # update/save thermostat configuration
        try:
            thermostat = Thermostat.get(number=thermostat_number)
        except DoesNotExist:
            thermostat = Thermostat(number=thermostat_number)
        if config.get('name') is not None:
            thermostat.name = config['name']
        if config.get('sensor') is not None:
            thermostat.sensor = int(config['sensor'])
        if config.get('room') is not None:
            thermostat.room = int(config['room'])
        if config.get('pid_p') is not None:
            if mode == 'heating':
                thermostat.pid_heating_p = float(config['pid_p'])
            else:
                thermostat.pid_cooling_p = float(config['pid_p'])
        if config.get('pid_i') is not None:
            if mode == 'heating':
                thermostat.pid_heating_i = float(config['pid_i'])
            else:
                thermostat.pid_cooling_i = float(config['pid_i'])
        if config.get('pid_d') is not None:
            if mode == 'heating':
                thermostat.pid_heating_d = float(config['pid_d'])
            else:
                thermostat.pid_cooling_d = float(config['pid_d'])
        thermostat.start = last_monday_night
        thermostat.save()

        # update/save output configuration
        output_config_present = config.get('output0') is not None or config.get('output1') is not None
        if output_config_present:
            # unlink all previously linked valve_numbers, we are resetting this with the new outputs we got from the API
            deleted = ValveToThermostat.delete().where(ValveToThermostat.thermostat == thermostat)\
                                                .where(ValveToThermostat.mode == mode)\
                                                .execute()
            logger.info('unlinked {} valve_numbers from thermostat {}'.format(deleted, thermostat.name))

            for field in ['output0', 'output1']:
                if config.get(field) is not None:
                    # 1. get or create output, creation also saves to db
                    output_number = int(config[field])
                    if output_number == 255:
                        continue
                    output, output_created = Output.get_or_create(number=output_number)

                    # 2. get or create the valve and link to this output
                    try:
                        valve = Valve.get(output=output, number=output_number)

                    except DoesNotExist:
                        valve = Valve(output=output, number=output_number)
                    valve.name = 'Valve (output {})'.format(output_number)
                    valve.save()

                    # 3. link the valve to the thermostat, set properties
                    try:
                        valve_to_thermostat = ValveToThermostat.get(valve=valve, thermostat=thermostat, mode=mode)
                    except DoesNotExist:
                        valve_to_thermostat = ValveToThermostat(valve=valve, thermostat=thermostat, mode=mode)
                    # TODO: decide if this is a cooling thermostat or heating thermostat
                    valve_to_thermostat.priority = 0 if field == 'output0' else 1
                    valve_to_thermostat.save()

        # update/save scheduling configuration
        for (day_index, key) in [(0, 'auto_mon'),
                                 (1, 'auto_tue'),
                                 (2, 'auto_wed'),
                                 (3, 'auto_thu'),
                                 (4, 'auto_fri'),
                                 (5, 'auto_sat'),
                                 (6, 'auto_sun')]:
            if config.get(key) is not None:
                v0_schedule = config[key]
                try:
                    day_schedule = DaySchedule.get(thermostat=thermostat, index=day_index, mode=mode)
                    day_schedule.update_schedule_from_v0(v0_schedule)
                except DoesNotExist:
                    day_schedule = DaySchedule.from_v0_dict(thermostat=thermostat, index=day_index, mode=mode, v0_schedule=v0_schedule)
                day_schedule.save()

        for (field, preset_name) in [('setp3', 'AWAY'),
                                     ('setp4', 'VACATION'),
                                     ('setp5', 'PARTY')]:
            if config.get(field) is not None:
                try:
                    preset = Preset.get(name=preset_name, thermostat=thermostat)
                except DoesNotExist:
                    preset = Preset(name=preset_name, thermostat=thermostat)
                if mode == 'cooling':
                    preset.cooling_setpoint = float(config[field])
                else:
                    preset.heating_setpoint = float(config[field])
                preset.active = False
                preset.save()

        return thermostat

    def v0_set_configuration(self, config, mode):
        # TODO: implement the new v1 config format
        thermostat_number = int(config['id'])
        thermostat = ThermostatControllerGateway.create_or_update_thermostat_from_v0_api(thermostat_number, config, mode)
        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        if thermostat_pid is not None:
            thermostat_pid.update_thermostat(thermostat)
        else:
            thermostat_pid = ThermostatPid(thermostat, self._pump_valve_controller)
            self.thermostat_pids[thermostat_number] = thermostat_pid
        self._sync_scheduler()
        thermostat_pid.tick()
        return {'status': 'OK'}

    def v0_event_thermostat_changed(self, thermostat_number, active_preset, current_setpoint, actual_temperature, percentages, room):
        """
        :type thermostat_number: int
        :type active_preset: str
        :type current_setpoint: float
        :type actual_temperature: float
        :type percentages: list
        :type room: int
        """
        logger.debug('v0_event_thermostat_changed: {}'.format(thermostat_number))
        self._message_client.send_event(OMBusEvents.THERMOSTAT_CHANGE, {'id': thermostat_number})
        location = {'room_id': room}
        for callback in self._event_subscriptions:
            callback(Event(event_type=Event.Types.THERMOSTAT_CHANGE,
                           data={'id': thermostat_number,
                                 'status': {'preset': active_preset,
                                            'current_setpoint': current_setpoint,
                                            'actual_temperature': actual_temperature,
                                            'output_0': percentages[0],
                                            'output_1': percentages[1]},
                                 'location': location}))

    def v0_event_thermostat_group_changed(self, thermostat_group):
        """
        :type thermostat_group: models.ThermostatGroup
        """
        logger.debug('v0_event_thermostat_group_changed: {}'.format(thermostat_group))
        self._message_client.send_event(OMBusEvents.THERMOSTAT_CHANGE, {'id': None})
        for callback in self._event_subscriptions:
            callback(Event(event_type=Event.Types.THERMOSTAT_GROUP_CHANGE,
                           data={'id': 0,
                                 'status': {'state': 'ON' if thermostat_group.on else 'OFF',
                                            'mode': 'COOLING' if thermostat_group.mode == 'cooling' else 'HEATING'},
                                 'location': {}}))


@post_save(sender=ThermostatGroup)
@Inject
def on_thermostat_group_change_handler(model_class, instance, created, thermostat_controller=INJECTED):
    _ = model_class
    if not created:
        thermostat_controller.v0_event_thermostat_group_changed(instance)
