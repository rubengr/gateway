import datetime
import json
import logging
import time

from peewee import PrimaryKeyField, IntegerField, FloatField, BooleanField, TextField, Model, ForeignKeyField, \
    CompositeKey, SqliteDatabase

logger = logging.getLogger('openmotics')


class Database(object):
    _db = SqliteDatabase('/opt/openmotics/etc/gateway.db', pragmas={'foreign_keys': 1})

    @classmethod
    def init(cls):
        cls._db.create_tables([Output, ThermostatGroup, OutputToThermostatGroup, Thermostat, Valve,
                               ValveToThermostat, Output, Preset, DaySchedule])
        # create default data entries
        ThermostatGroup.get_or_create(id=1, number=0, name='default', on=True)

    @classmethod
    def get_db(cls):
        return cls._db


class BaseModel(Model):
    class Meta:
        database = Database.get_db()


class Output(BaseModel):
    id = PrimaryKeyField()
    number = IntegerField(unique=True)


class ThermostatGroup(BaseModel):
    id = PrimaryKeyField()
    number = IntegerField(unique=True)
    name = TextField()
    on = BooleanField(default=True)
    threshold_temp = IntegerField(null=True, default=None)
    sensor = IntegerField(null=True, default=None)
    mode = TextField(default='heating')  # heating or cooling # TODO: add support for 'both'

    @staticmethod
    def v0_get_global():
        return ThermostatGroup.get(number=0)


class OutputToThermostatGroup(BaseModel):
    """ Outputs on a thermostat group are sometimes used for setting the pumpgroup in a certain state
        the index var is 0-4 of the output in setting this config """
    output = ForeignKeyField(Output, on_delete='CASCADE')
    thermostat_group = ForeignKeyField(ThermostatGroup, on_delete='CASCADE')
    index = IntegerField()
    mode = TextField()

    class Meta:
        primary_key = CompositeKey('output', 'thermostat_group')


class Valve(BaseModel):
    id = PrimaryKeyField()
    name = TextField()
    pwm = BooleanField(default=False)
    delay = IntegerField(default=60)
    output = ForeignKeyField(Output, backref='valve', on_delete='CASCADE', unique=True)


class Thermostat(BaseModel):
    id = PrimaryKeyField()
    number = IntegerField(unique=True)
    name = TextField(default='Thermostat')
    sensor = IntegerField()

    pid_heating_p = FloatField(default=120)
    pid_heating_i = FloatField(default=0)
    pid_heating_d = FloatField(default=0)
    pid_cooling_p = FloatField(default=120)
    pid_cooling_i = FloatField(default=0)
    pid_cooling_d = FloatField(default=0)

    automatic = BooleanField(default=True)
    room = IntegerField()
    start = IntegerField()
    setpoint = FloatField(default=14.0)
    thermostat_group = ForeignKeyField(ThermostatGroup, backref='thermostats', on_delete='CASCADE', default=1)

    def get_preset(self, name, mode=None):
        mode = self.thermostat_group.mode if mode is None else mode
        presets = Preset.select().where(name=name, mode=mode, thermostat=self.id)
        return presets[0]

    @property
    def mode(self):
        return self.thermostat_group.mode

    @property
    def heating_valves(self):
        return [valve for valve in Valve.select(Valve, ValveToThermostat.mode, ValveToThermostat.priority)
                                        .join(ValveToThermostat)
                                        .where(ValveToThermostat.thermostat == self.id)
                                        .where(ValveToThermostat.mode == 'heating')
                                        .order_by(ValveToThermostat.priority)]

    @property
    def cooling_valves(self):
        return [valve for valve in Valve.select(Valve, ValveToThermostat.mode, ValveToThermostat.priority)
                                        .join(ValveToThermostat)
                                        .where(ValveToThermostat.thermostat == self.id)
                                        .where(ValveToThermostat.mode == 'cooling')
                                        .order_by(ValveToThermostat.priority)]

    @property
    def heating_presets(self):
        return [preset for preset in Preset.select(Preset, PresetToThermostat.mode)
                                           .join(PresetToThermostat)
                                           .where(PresetToThermostat.thermostat == self.id)
                                           .where(PresetToThermostat.mode == 'heating')]

    @property
    def cooling_presets(self):
        return [preset for preset in Preset.select(Preset, PresetToThermostat.mode)
                                           .join(PresetToThermostat)
                                           .where(PresetToThermostat.thermostat == self.id)
                                           .where(PresetToThermostat.mode == 'cooling')]

    def v0_get_output_numbers(self, mode=None):
        if mode is None:
            mode = self.thermostat_group.mode
        valves = self.cooling_valves if mode == 'cooling' else self.heating_valves
        db_outputs = [valve.output.number for valve in valves]
        number_of_outputs = len(db_outputs)

        if number_of_outputs > 2:
            logger.warning('Only 2 outputs are supported in the old format. Total: {} outputs.'.format(number_of_outputs))

        output0 = db_outputs[0] if number_of_outputs > 0 else None
        output1 = db_outputs[1] if number_of_outputs > 1 else None
        return [output0, output1]

    def to_v0_format(self, mode='heating', fields=None):
        """
        :returns: thermostat_configuration dict: contains 'id' (Id), 'auto_fri' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_mon' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sat' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sun' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_thu' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_tue' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_wed' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'name' (String[16]), 'output0' (Byte), 'output1' (Byte), 'permanent_manual' (Boolean), 'pid_d' (Byte), 'pid_i' (Byte), 'pid_int' (Byte), 'pid_p' (Byte), 'room' (Byte), 'sensor' (Byte), 'setp0' (Temp), 'setp1' (Temp), 'setp2' (Temp), 'setp3' (Temp), 'setp4' (Temp), 'setp5' (Temp)
        """
        data = {}
        data['id'] = self.number
        data['name'] = self.name
        data['sensor'] = self.sensor
        if mode == 'heating':
            data['pid_p'] = self.pid_heating_p
            data['pid_i'] = self.pid_heating_i
            data['pid_d'] = self.pid_heating_d
            presets = self.heating_presets
        else:
            data['pid_p'] = self.pid_cooling_p
            data['pid_i'] = self.pid_cooling_i
            data['pid_d'] = self.pid_cooling_d
            presets = self.cooling_presets

        for preset in presets:
            if preset.name == 'AWAY':
                data['setp3'] = preset.setpoint
            if preset.name == 'VACATION':
                data['setp4'] = preset.setpoint
            if preset.name == 'PARTY':
                data['setp5'] = preset.setpoint

        data['permanent_manual'] = self.automatic
        data['room'] = self.room
        data['output0'], data['output1'] = self.v0_get_output_numbers(mode=mode)

        day_schedules = sorted(self.day_schedules, key=lambda schedule: schedule.index, reverse=False)
        start_day_of_week = (self.start / 86400 - 4) % 7  # 0: Monday, 1: Tuesday, ...
        for (day_index, key) in [(0, 'auto_mon'),
                                 (1, 'auto_tue'),
                                 (2, 'auto_wed'),
                                 (3, 'auto_thu'),
                                 (4, 'auto_fri'),
                                 (5, 'auto_sat'),
                                 (6, 'auto_sun')]:
            index = (7 - start_day_of_week + day_index) % 7
            data[key] = day_schedules[index].to_v0_dict()
        return data


class ValveToThermostat(BaseModel):
    valve = ForeignKeyField(Valve, on_delete='CASCADE')
    thermostat = ForeignKeyField(Thermostat, on_delete='CASCADE')
    mode = TextField(default='heating')
    priority = IntegerField(default=0)

    class Meta:
        table_name = 'valve_to_thermostat'


class Preset(BaseModel):
    id = PrimaryKeyField()
    name = TextField()
    setpoint = FloatField()
    mode = TextField(default='heating')
    thermostat = ForeignKeyField(Thermostat, on_delete='CASCADE')

    @classmethod
    def from_v0(cls, thermostat, v0_setpoint, mode='heating'):
        if mode not in ['heating', 'cooling']:
            raise ValueError('Preset mode should be cooling or heating')
        mapping = {3: 'AWAY',
                   4: 'VACATION',
                   5: 'PARTY'}
        name = mapping.get(v0_setpoint)
        if name is None:
            raise ValueError('Preset v0_setpoint {} unknown'.format(v0_setpoint))
        return Preset(name=name, thermostat=thermostat, mode=mode).save()


class DaySchedule(BaseModel):
    id = PrimaryKeyField()
    index = IntegerField()
    content = TextField()
    mode = TextField(default='heating')
    thermostat = ForeignKeyField(Thermostat, backref='day_schedules', on_delete='CASCADE')

    @classmethod
    def from_dict(cls, thermostat, day_index, mode, data):
        """
        "data":
            {
                "0": <temperature from this timestamp>,
                "23400": <temperature from this timestamp>,
                "30600": <temperature from this timestamp>,
                "61200": <temperature from this timestamp>,
                "84600": <temperature from this timestamp>
            }
        """
        # convert relative timestamps to int and temperature values to float
        for key, value in data.iteritems():
            relative_timestamp = int(key)
            if relative_timestamp < 86400:
                data[relative_timestamp] = float(value)
        return cls(thermostat=thermostat, index=day_index, mode=mode, content=json.dumps(data))

    def to_dict(self):
        return json.loads(self.content)

    @classmethod
    def _schedule_data_from_v0(cls, v0_schedule):
        def get_seconds(hour_timestamp):
            x = time.strptime(hour_timestamp, '%H:%M')
            return int(datetime.timedelta(hours=x.tm_hour, minutes=x.tm_min, seconds=x.tm_sec).total_seconds())
        # e.g. [17, u'06:30', u'08:30', 20, u'17:00', u'23:30', 21]
        temp_n, start_d1, stop_d1, temp_d1, start_d2, stop_d2, temp_d2 = v0_schedule

        data = {0: temp_n,
                get_seconds(start_d1): temp_d1,
                get_seconds(stop_d1):  temp_n,
                get_seconds(start_d2): temp_d2,
                get_seconds(stop_d2):  temp_n}
        return data

    def update_schedule_from_v0(self, v0_schedule):
        data = DaySchedule._schedule_data_from_v0(v0_schedule)
        self.content = json.dumps(data)

    @classmethod
    def from_v0_dict(cls, thermostat, index, mode, v0_schedule,):
        data = cls._schedule_data_from_v0(v0_schedule)
        return cls.from_dict(thermostat, index, mode, data)

    def to_v0_dict(self):
        return_data = {}
        data = self.to_dict()
        n_entries = len(data)
        if n_entries == 0:
            logger.error('Serializing an empty temperature day schedule.')
        elif n_entries < 4:
            logger.warning('Not enough data to serialize day schedule in old format. Returning best effort data.')
            first_value = data.itervalues().next()
            return_data['temp_n'] = first_value
            return_data['temp_d1'] = first_value
            return_data['temp_d2'] = first_value
        else:
            index = 0
            schedule = self.to_dict()
            for timestamp in sorted(schedule.keys()):
                temperature = schedule[timestamp]
                if index == 0:
                    return_data['temp_n'] = temperature
                elif index == 1:
                    return_data['temp_d1'] = temperature
                elif index == 3:
                    return_data['temp_d2'] = temperature
                index += 1
        return return_data

    def get_scheduled_temperature(self, seconds_in_day):
        seconds_in_day = seconds_in_day % 86400
        data = self.to_dict()
        last_value = data.get(0)
        for key in sorted(data):
            if key > seconds_in_day:
                break
            last_value = data[key]
        return last_value
