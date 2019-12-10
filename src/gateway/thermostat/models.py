import json
import logging
from peewee import *

db = SqliteDatabase('gateway.db', pragmas={'foreign_keys': 1})

logger = logging.getLogger('openmotics')


class BaseModel(Model):
    class Meta:
        database = db


class ThermostatGroup(BaseModel):
    id = PrimaryKeyField()
    name = TextField()


class Thermostat(BaseModel):
    id = PrimaryKeyField()
    number = IntegerField(unique=True)
    name = TextField(default='Thermostat')
    sensor = IntegerField()
    pid_p = FloatField(default=120)
    pid_i = FloatField(default=0)
    pid_d = FloatField(default=0)
    enabled = BooleanField(default=False)
    automatic = BooleanField(default=False)
    room = IntegerField()
    start = IntegerField()
    setpoint = FloatField(default=21.0)
    mode = TextField(default='heating')        # heating or cooling
    thermostat_group = ForeignKeyField(ThermostatGroup, backref='thermostats', on_delete='CASCADE')

    def get_preset(self, name):
        return Preset.select().where(Preset.name == name, Preset.thermostat == self.id)

    def get_schedule_length(self):
        return len(self._day_schedules)

    def set_day_schedule(self, day, thermostat_day_schedule):
        self._day_schedules[day] = thermostat_day_schedule

    def get_day_schedule(self, day):
        return self._day_schedules.get(day)

    @property
    def heating_outputs(self):
        return [heating_output for heating_output in
                Output.select().join(OutputToThermostat).where(OutputToThermostat.thermostat == self, OutputToThermostat.mode == 'heating')]

    @property
    def cooling_outputs(self):
        return [cooling_output for cooling_output in
                Output.select().join(OutputToThermostat).where(OutputToThermostat.thermostat == self, OutputToThermostat.mode == 'cooling')]

    def to_v0_format(self, fields):
        """
        :returns: thermostat_configuration dict: contains 'id' (Id), 'auto_fri' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_mon' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sat' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_sun' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_thu' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_tue' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'auto_wed' ([temp_n(Temp),start_d1(Time),stop_d1(Time),temp_d1(Temp),start_d2(Time),stop_d2(Time),temp_d2(Temp)]), 'name' (String[16]), 'output0' (Byte), 'output1' (Byte), 'permanent_manual' (Boolean), 'pid_d' (Byte), 'pid_i' (Byte), 'pid_int' (Byte), 'pid_p' (Byte), 'room' (Byte), 'sensor' (Byte), 'setp0' (Temp), 'setp1' (Temp), 'setp2' (Temp), 'setp3' (Temp), 'setp4' (Temp), 'setp5' (Temp)
        """
        data = {}
        data['id'] = self.number
        data['name'] = self.name
        data['sensor'] = self.sensor
        data['pid_p'] = self.pid_p
        data['pid_i'] = self.pid_i
        data['pid_d'] = self.pid_d
        data['permanent_manual'] = self.automatic
        data['room'] = self.room

        db_outputs = [db_output for db_output in self.outputs]
        number_of_outputs = len(db_outputs)

        data['output0'] = db_outputs[0].output_nr if number_of_outputs > 0 else None
        data['output1'] = db_outputs[1].output_nr if number_of_outputs > 1 else None
        if number_of_outputs > 2:
            logger.warning(
                'Only 2 outputs are supported in the old format. Total: {} outputs.'.format(number_of_outputs))

        data['setp3'] = Preset.select().where(thermostat=self, name='AWAY')['temperature']
        data['setp4'] = Preset.select().where(thermostat=self, name='VACATION')['temperature']
        data['setp5'] = Preset.select().where(thermostat=self, name='PARTY')['temperature']

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


class Output(BaseModel):
    id = PrimaryKeyField()
    output_nr = IntegerField(unique=True)
    thermostat = ForeignKeyField(Thermostat, backref='outputs', on_delete='SET_NULL')


class OutputToThermostat(Model):
    """A simple "through" table for many-to-many relationship."""
    output = ForeignKeyField(Output, on_delete='CASCADE')
    thermostat = ForeignKeyField(Thermostat, on_delete='CASCADE')
    mode = TextField(default='heating')

    class Meta:
        primary_key = CompositeKey('output', 'thermostat')


class Preset(BaseModel):
    id = PrimaryKeyField()
    name = TextField()
    temperature = IntegerField()
    thermostat = ManyToManyField(Thermostat, backref='presets', on_delete='CASCADE')


class DaySchedule(BaseModel):
    id = PrimaryKeyField()
    index = IntegerField()
    content = TextField()
    thermostat = ForeignKeyField(Thermostat, backref='day_schedules', on_delete='CASCADE')

    @classmethod
    def from_dict(cls, thermostat, day_index, data):
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
        return cls(thermostat=thermostat, day_index=day_index, content=json.dumps(data))

    def to_dict(self):
        return json.loads(self.content)

    @classmethod
    def from_v0_dict(cls, thermostat, day_index, v0_dict):
        data = {"0": v0_dict['temp_n'],
                v0_dict['start_d1']: v0_dict['temp_d1'],
                v0_dict['stop_d1']:  v0_dict['temp_n'],
                v0_dict['start_d2']: v0_dict['temp_d2'],
                v0_dict['stop_d2']:  v0_dict['temp_n']}
        return cls.from_dict(thermostat, day_index, data)

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
            for timestamp, temperature in self.to_dict().iteritems:
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
