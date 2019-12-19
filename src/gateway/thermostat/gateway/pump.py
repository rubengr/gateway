import time
from threading import Thread


class Pump(object):

    def __init__(self, pump, gateway_api):
        """ Create a pump object
        :param pump: the pump object
        :type pump: gateway.thermostat.gateway.models.Pump
        :param gateway_api: Gateway API Controller
        :type gateway_api: gateway.gateway_api.GatewayApi
        """
        self._pump = pump
        self._gateway_api = gateway_api

    def valves_open(self):
        return any([valve.is_open() for valve in self._pump.valves])

    def _set_state(self, active):
        output_number = self._pump.output.number
        dimmable_output = self._gateway_api.get_output_configuration(output_number, fields='module_type').get('module_type') in ['d', 'D']
        if dimmable_output:
            dimmer = 100 if active else 0
            self._gateway_api.set_output_dimmer(output_number, dimmer=dimmer)
        self._gateway_api.set_output_status(output_number, active)

    def turn_on(self):
        if self.valves_open():
            self._set_state(True)
        else:
            raise RuntimeError('Cannot turn on pump {} since no attached valves are open.'.format(self._pump.id))

    def turn_off(self):
        self._set_state(False)
