from wiring import provides, scope, inject, SingletonScope
from gateway.thermostat.thermostat_controller import ThermostatController


class GatewayThermostatController(ThermostatController):

    def get_thermostat_configurations(self, fields=None):
        pass

    def set_thermostat_configuration(self, config):
        pass

    def set_thermostat_configurations(self, config):
        pass

    def set_thermostat_mode(self, thermostat_on, cooling_mode=False, cooling_on=False, automatic=None, setpoint=None):
        pass

    def set_current_setpoint(self, thermostat, temperature):
        pass

    def get_thermostats(self):
        pass

    def get_thermostat_configuration(self, thermostat_id, fields=None):
        pass

