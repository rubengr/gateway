import time
import logging
from threading import Thread
from peewee import DoesNotExist
from wiring import provides, scope, inject, SingletonScope
from bus.om_bus_events import OMBusEvents
from gateway.observer import Event
from gateway.thermostat.gateway.models import Output, DaySchedule, Preset, Thermostat, ThermostatGroup, \
    OutputToThermostatGroup, ValveToThermostat, Valve
from gateway.thermostat.gateway.pump_valve_controller import PumpValveController
from gateway.thermostat.thermostat_controller import ThermostatController
from gateway.thermostat.gateway.thermostat_pid import ThermostatPid

logger = logging.getLogger('openmotics')


class ThermostatControllerGateway(ThermostatController):

    THERMOSTAT_PID_UPDATE_INTERVAL = 5
    PUMP_UPDATE_INTERVAL = 30
    SYNC_CONFIG_INTERVAL = 900

    @provides('thermostat_controller')
    @scope(SingletonScope)
    @inject(gateway_api='gateway_api', message_client='message_client', observer='observer',
            master_communicator='master_communicator', eeprom_controller='eeprom_controller')
    def __init__(self, gateway_api, message_client, observer, master_communicator, eeprom_controller):
        super(ThermostatControllerGateway, self).__init__(gateway_api, message_client, observer, master_communicator,
                                                          eeprom_controller)

        self._running = False
        self._pid_loop_thread = None
        self._update_pumps_thread = None
        self._periodic_sync_thread = None
        self.thermostat_pids = {}
        self.pump_ = {}
        self._pump_valve_controller = PumpValveController(self._gateway_api)

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
            logger.info('Starting gateway thermostatcontroller... Done')
        else:
            raise RuntimeError('GatewayThermostatController already running. Please stop it first.')

    def stop(self):
        if not self._running:
            logger.warning('Stopping an already stopped GatewayThermostatController.')
        self._running = False

    def refresh_thermostats_from_db(self):
        for thermostat in Thermostat.select():
            thermostat_pid = self.thermostat_pids.get(thermostat.number)
            if thermostat_pid is None:
                thermostat_pid = ThermostatPid(thermostat, self._pump_valve_controller, self._gateway_api)
                self.thermostat_pids[thermostat.number] = thermostat_pid
            thermostat_pid.update_thermostat(thermostat)

    def refresh_config_from_db(self):
        self.refresh_thermostats_from_db()
        self._pump_valve_controller.refresh_from_db()

    def _pid_tick(self):
        while self._running:
            for thermostat_number, thermostat_pid in self.thermostat_pids.iteritems():
                try:
                    thermostat_pid.tick()
                    self._pump_valve_controller.steer()
                except Exception:
                    logger.exception('There was a problem with calculating thermostat PID {}'.format(thermostat_pid))
            time.sleep(self.THERMOSTAT_PID_UPDATE_INTERVAL)

    def _update_pumps(self):
        while self._running:
            time.sleep(self.PUMP_UPDATE_INTERVAL)
            self._pump_valve_controller.steer_pumps()

    def _periodic_sync(self):
        while self._running:
            time.sleep(self.SYNC_CONFIG_INTERVAL)
            self.refresh_config_from_db()


    ################################
    # v1 APIs
    ################################

    # TODO: implement v1 APIs

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
                           'automatic': True,  #TODO: if any thermnostat is automatic
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

                try:
                    v0_setpoint = Preset.get(thermostat=thermostat, active=True).get_v0_setpoint_id()
                except (ValueError, DoesNotExist):
                    v0_setpoint = 0

                data = {'id': thermostat.number,
                        'act': self._gateway_api.get_sensor_temperature_status(thermostat.sensor),
                        'csetp': csetp,
                        'outside': self._gateway_api.get_sensor_temperature_status(global_thermostat.sensor),
                        'mode': 0,  # TODO: !!!check if still used!!
                        'automatic': active_preset.name == 'SCHEDULE' if active_preset is not None else False,
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
        return {'status': 'OK'}

    def v0_set_current_setpoint(self, thermostat_number, temperature):
        thermostat = Thermostat.get(number=thermostat_number)
        # when setting a setpoint manually, switch to manual preset except for when we are in scheduled mode
        # scheduled mode will override the setpoint when the next edge in the schedule is triggered
        active_preset = thermostat.active_preset
        if active_preset.name != 'SCHEDULE':
            active_preset = thermostat.get_preset('MANUAL')
            thermostat.active_preset = active_preset

        if thermostat.mode == 'heating':
            active_preset.heating_setpoint = float(temperature)
        else:
            active_preset.cooling_setpoint = float(temperature)
        active_preset.save()
        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        thermostat_pid.update_thermostat(thermostat)
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
        return {'status': 'OK'}

    def v0_get_pump_group_configurations(self, fields=None):
        config = {'id': 1,
                  'outputs': 1,
                  'output': 2,
                  'room': 255}
        return {'config': config}

    def v0_get_global_thermostat_configuration(self, fields=None):
        pass

    def v0_set_global_thermostat_configuration(self, config):
        # update thermostat group configuration
        thermostat_group = ThermostatGroup.get_or_create(number=0)
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

    @staticmethod
    def _create_or_update_thermostat_from_v0_api(thermostat_number, config, mode='heating'):
        """
        :param thermostat_number: the thermostat number for which the config needs to be stored
        :type thermostat_number: int
        :param config: the v0 config dict e.g. {'auto_wed': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'auto_mon': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'output0': 0, 'output1': 3, 'room': 255, 'id': 2, 'auto_sat': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'sensor': 0, 'auto_sun': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'auto_th': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'pid_int': 0, 'auto_tue': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'setp0': 20, 'setp5': 18, 'setp4': 18, 'pid_p': 120, 'setp1': 17, 'name': 'H - Thermostat 2', 'setp3': 18, 'setp2': 21, 'auto_fri': [17, '06:30', '08:30', 20, '17:00', '23:30', 21], 'pid_d': 0, 'pid_i': 0}
        :type config: dict
        :returns the thermostat
        """
        logger.info('config {}'.format(config))
        # we don't get a start date, calculate last monday night to map the schedules
        now = int(time.time())
        day_of_week = (now / 86400 - 4) % 7  # 0: Monday, 1: Tuesday, ...
        last_monday_night = now - now % 86400 - day_of_week * 86400

        # update/save thermostat configuration
        try:
            thermo = Thermostat.get(number=thermostat_number)
        except DoesNotExist:
            thermo = Thermostat(number=thermostat_number)
        if config.get('name') is not None:
            thermo.name = config['name']
        if config.get('sensor') is not None:
            thermo.sensor = int(config['sensor'])
        if config.get('room') is not None:
            thermo.room = int(config['room'])
        if config.get('pid_p') is not None:
            if mode == 'heating':
                thermo.pid_heating_p = float(config['pid_p'])
            else:
                thermo.pid_cooling_p = float(config['pid_p'])
        if config.get('pid_i') is not None:
            if mode == 'heating':
                thermo.pid_heating_i = float(config['pid_i'])
            else:
                thermo.pid_cooling_i = float(config['pid_i'])
        if config.get('pid_d') is not None:
            if mode == 'heating':
                thermo.pid_heating_d = float(config['pid_d'])
            else:
                thermo.pid_cooling_d = float(config['pid_d'])
        thermo.start = last_monday_night
        thermo.save()

        # update/save output configuration
        output_config_present = config.get('output0') is not None or config.get('output1') is not None
        if output_config_present:
            # unlink all previously linked valve_numbers, we are resetting this with the new outputs we got from the API
            deleted = ValveToThermostat.delete().where(ValveToThermostat.thermostat == thermo)\
                                                .where(ValveToThermostat.mode == mode)\
                                                .execute()
            logger.info('unlinked {} valve_numbers from thermostat {}'.format(deleted, thermo.name))

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
                        valve_to_thermostat = ValveToThermostat.get(valve=valve, thermostat=thermo, mode=mode)
                    except DoesNotExist:
                        valve_to_thermostat = ValveToThermostat(valve=valve, thermostat=thermo, mode=mode)
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
                    day_schedule = DaySchedule.get(thermostat=thermo, index=day_index, mode=mode)
                    day_schedule.update_schedule_from_v0(v0_schedule)
                except DoesNotExist:
                    day_schedule = DaySchedule.from_v0_dict(thermostat=thermo, index=day_index, mode=mode, v0_schedule=v0_schedule)
                day_schedule.save()

        for (field, preset_name) in [('setp3', 'AWAY'),
                                     ('setp4', 'VACATION'),
                                     ('setp5', 'PARTY')]:
            if config.get(field) is not None:
                try:
                    preset = Preset.get(name=preset_name, thermostat=thermo)
                except DoesNotExist:
                    preset = Preset(name=preset_name, thermostat=thermo)
                if mode == 'cooling':
                    preset.cooling_setpoint = float(config[field])
                else:
                    preset.heating_setpoint = float(config[field])
                preset.active = False
                preset.save()

        return thermo

    def _v0_event_thermostat_changed(self, thermostat):
        """
        :type thermostat: gateway.thermostat.models.Thermostat
        """
        """ Executed by the Thermostat Status tracker when an output changed state """
        self._message_client.send_event(OMBusEvents.THERMOSTAT_CHANGE, {'id': thermostat.number})
        location = {'room_id': thermostat.room}
        for callback in self._event_subscriptions:
            callback(Event(event_type=Event.Types.THERMOSTAT_CHANGE,
                           data={'id': thermostat.number,
                                 'status': {'preset': 'AWAY',  # TODO: get real value from somewhere
                                            'current_setpoint': thermostat.setpoint,
                                            'actual_temperature': 21,  # TODO: get real value from somewhere
                                            'output_0': thermostat.heating_valves[0],
                                            'output_1': thermostat.heating_valves[1]},
                                 'location': location}))

    def _v0_event_thermostat_group_changed(self, thermostat_group):
        """
        :type thermostat_group: gateway.thermostat.models.ThermostatGroup
        """
        self._message_client.send_event(OMBusEvents.THERMOSTAT_CHANGE, {'id': None})
        for callback in self._event_subscriptions:
            callback(Event(event_type=Event.Types.THERMOSTAT_GROUP_CHANGE,
                           data={'id': 0,
                                 'status': {'state': 'ON' if thermostat_group.on else 'OFF',
                                            'mode': 'COOLING' if thermostat_group.mode == 'cooling' else 'HEATING'},
                                 'location': {}}))

    def v0_set_configuration(self, config, mode):
        # TODO: implement the new v1 config format
        thermostat_number = int(config['id'])
        thermostat = ThermostatControllerGateway._create_or_update_thermostat_from_v0_api(thermostat_number, config, mode)
        thermostat_pid = self.thermostat_pids.get(thermostat_number)
        if thermostat_pid is not None:
            thermostat_pid.update_thermostat(thermostat)
        else:
            self.thermostat_pids[thermostat_number] = ThermostatPid(thermostat, self._pump_valve_controller, self._gateway_api)
        return {'status': 'OK'}
