import time

from peewee import DoesNotExist

from gateway.thermostat.models import Output, DaySchedule, Preset, Thermostat
from gateway.thermostat.thermostat_controller import ThermostatController


class GatewayThermostatController(ThermostatController):

    def get_thermostat_configurations(self, fields=None):
        # TODO: implement the new config format
        for thermostat_id in xrange(32):
            self.get_thermostat_configuration(thermostat_id, fields)

    def get_thermostat_configuration(self, thermostat_id, fields=None):
        # TODO: implement the new config format
        GatewayThermostatController._get_thermostat_for_vo_api(thermostat_id, fields)

    def set_thermostat_configurations(self, config):
        # TODO: implement the new config format
        for thermostat_config in config:
            self.set_thermostat_configuration(thermostat_config)

    def set_thermostat_configuration(self, config):
        """
        Set one thermostat_configuration.

        :param config: The thermostat_configuration to set
        :type config: thermostat_configuration dict: contains 'id' (Id), 'auto_fri' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_mon' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sat' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sun' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_thu' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_tue' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_wed' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'name' (String[16]), 'output0' (Byte), 'output1' (Byte), 'permanent_manual' (Boolean), 'pid_d' (Byte), 'pid_i' (Byte), 'pid_int' (Byte), 'pid_p' (Byte), 'room' (Byte), 'sensor' (Byte), 'setp0' (Temp), 'setp1' (Temp), 'setp2' (Temp), 'setp3' (Temp), 'setp4' (Temp), 'setp5' (Temp)
        """
        # TODO: implement the new config format
        GatewayThermostatController._create_thermostat_from_vo_api(config)

    def set_thermostat_mode(self, thermostat_on, cooling_mode=False, cooling_on=False, automatic=None, setpoint=None):
        pass

    def set_current_setpoint(self, thermostat, temperature):
        pass

    def get_thermostats(self):
        pass

    @staticmethod
    def _create_thermostat_from_vo_api(config):
        # we don't get a start date, calculate last monday night to map the schedules
        now = int(time.time())
        day_of_week = (now / 86400 - 4) % 7  # 0: Monday, 1: Tuesday, ...
        last_monday_night = now - now % 86400 - day_of_week * 86400

        thermostat_id = int(config['id'])
        Thermostat.delete_by_id(thermostat_id)

        thermo = Thermostat(id=thermostat_id,
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

        away = Preset(name='away', temperature=float(config['setp3']), thermostat=thermo)
        away.save()
        vacation = Preset(name='vacation', temperature=float(config['setp4']), thermostat=thermo)
        vacation.save()
        party = Preset(name='party', temperature=float(config['setp5']), thermostat=thermo)
        party.save()

    @classmethod
    def _serialize_to_v0(cls, thermostat_id, fields):
        """
        :returns: thermostat_configuration dict: contains 'id' (Id), 'auto_fri' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_mon' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sat' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sun' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_thu' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_tue' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_wed' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'name' (String[16]), 'output0' (Byte), 'output1' (Byte), 'permanent_manual' (Boolean), 'pid_d' (Byte), 'pid_i' (Byte), 'pid_int' (Byte), 'pid_p' (Byte), 'room' (Byte), 'sensor' (Byte), 'setp0' (Temp), 'setp1' (Temp), 'setp2' (Temp), 'setp3' (Temp), 'setp4' (Temp), 'setp5' (Temp)
        """
        try:
            thermo = Thermostat.get_by_id(thermostat_id)

            data = {}
            data['id'] = thermo.id
            data['name'] = thermo.name
            data['sensor'] = thermo.sensor
            data['pid_p'] = thermo.pid_p
            data['pid_i'] = thermo.pid_i
            data['pid_d'] = thermo.pid_d
            data['automatic'] = thermo.automatic
            data['room'] = thermo.room
            data['automatic'] = thermo.automatic



            start = IntegerField()


            id = PrimaryKeyField()
            name = TextField()
            sensor = IntegerField()
            pid_p = FloatField()
            pid_i = FloatField()
            pid_d = FloatField()
            automatic = BooleanField()
            room = IntegerField()
            start = IntegerField()
            return thermo
        except DoesNotExist:
            return None

