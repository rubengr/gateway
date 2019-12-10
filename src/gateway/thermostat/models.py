import json
import logging
from peewee import *

db = SqliteDatabase('gateway.db', pragmas={'foreign_keys': 1})

logger = logging.getLogger('openmotics')

class BaseModel(Model):
    class Meta:
        database = db


class Thermostat(BaseModel):
    id = PrimaryKeyField()
    name = TextField()
    sensor = IntegerField()
    pid_p = FloatField()
    pid_i = FloatField()
    pid_d = FloatField()
    automatic = BooleanField()
    room = IntegerField()
    start = IntegerField()

    def set_preset(self, name, temperature):
        self.presets[name] = temperature

    def get_preset(self, name):
        return Preset.select().where(Preset.name == name, Preset.thermostat == self.id)

    def get_schedule_length(self):
        return len(self._day_schedules)

    def set_day_schedule(self, day, thermostat_day_schedule):
        self._day_schedules[day] = thermostat_day_schedule

    def get_day_schedule(self, day):
        return self._day_schedules.get(day)


class Preset(BaseModel):
    id = PrimaryKeyField()
    name = TextField()
    temperature = IntegerField()
    thermostat = ManyToManyField(Thermostat, backref='presets', on_delete='CASCADE')


class Output(BaseModel):
    id = PrimaryKeyField()
    output_nr = IntegerField(unique=True)
    thermostat = ForeignKeyField(Thermostat, backref='outputs', on_delete='SET_NULL')


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
        data = self.to_dict()
        if len(data) > 5:
            logger.warning('Serializing temperature day schedule to the old format might result in information loss due to features that are not supported.')
        for timestamp, temperature in self.to_dict().iteritems:


        data = {"0": v0_dict['temp_n'],
                v0_dict['start_d1']: v0_dict['temp_d1'],
                v0_dict['stop_d1']:  v0_dict['temp_n'],
                v0_dict['start_d2']: v0_dict['temp_d2'],
                v0_dict['stop_d2']:  v0_dict['temp_n']}
        return cls.from_dict(thermostat, day_index, data)

    def get_scheduled_temperature(self, seconds_in_day):
        seconds_in_day = seconds_in_day % 86400
        data = self.to_dict()
        last_value = data.get(0)
        for key in sorted(data):
            if key > seconds_in_day:
                break
            last_value = data[key]
        return last_value
