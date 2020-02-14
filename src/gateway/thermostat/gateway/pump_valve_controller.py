import logging
from threading import Lock
from ioc import INJECTED, Inject
from models import Valve
from gateway.thermostat.gateway.valve_driver import ValveDriver

logger = logging.getLogger('openmotics')


@Inject
class PumpValveController(object):

    def __init__(self, gateway_api=INJECTED):
        """ Create a ValveController object
        :param gateway_api: Gateway API Controller
        :type gateway_api: gateway.gateway_api.GatewayApi
        """
        self._gateway_api = gateway_api
        self._valve_drivers = {}
        self._config_change_lock = Lock()

    def refresh_from_db(self):
        with self._config_change_lock:
            existing_driver_numbers = set(self._valve_drivers.keys())
            new_driver_numbers = set()
            for valve in Valve.select():
                if valve.number in existing_driver_numbers:
                    self._valve_drivers[valve.number].update_valve(valve)
                else:
                    self._valve_drivers[valve.number] = ValveDriver(valve)
                new_driver_numbers.add(valve.number)

            drivers_to_be_deleted = existing_driver_numbers.difference(new_driver_numbers)
            for driver_number in drivers_to_be_deleted:
                valve_driver = self._valve_drivers.get(driver_number)
                if valve_driver is not None:
                    valve_driver.close()
                    del self._valve_drivers[driver_number]

    @staticmethod
    def _open_valves_cascade(total_percentage, valve_drivers):
        n_valves = len(valve_drivers)
        percentage_per_valve = 100.0 / n_valves
        n_valves_fully_open = int(total_percentage / percentage_per_valve)
        last_valve_open_percentage = 100.0 * (total_percentage - n_valves_fully_open * percentage_per_valve) / percentage_per_valve
        for n in xrange(n_valves_fully_open):
            valve_driver = valve_drivers[n]
            valve_driver.set(100)
        for n in xrange(n_valves_fully_open, n_valves):
            valve_driver = valve_drivers[n]
            percentage = last_valve_open_percentage if n == n_valves_fully_open else 0
            valve_driver.set(percentage)

    @staticmethod
    def _open_valves_equal(percentage, valve_drivers):
        for valve_driver in valve_drivers:
            valve_driver.set(percentage)

    def set_valves(self, percentage, valve_numbers, mode='cascade'):
        if len(valve_numbers) > 0:
            self.prepare_valves_for_transition(percentage, valve_numbers, mode=mode)

    def prepare_valves_for_transition(self, percentage, valve_numbers, mode='cascade'):
        if len(valve_numbers) > 0:
            valve_drivers = [self.get_valve_driver(valve_number) for valve_number in valve_numbers]
            if mode == 'cascade':
                self._open_valves_cascade(percentage, valve_drivers)
            else:
                self._open_valves_equal(percentage, valve_drivers)

    def steer(self):
        self.prepare_pumps_for_transition()
        self.steer_valves()
        self.steer_pumps()

    def prepare_pumps_for_transition(self):
        active_pump_drivers = set()
        potential_inactive_pump_drivers = set()
        for valve_number, valve_driver in self._valve_drivers.iteritems():
            if valve_driver.is_open():
                for pump_driver in valve_driver.pump_drivers:
                    active_pump_drivers.add(pump_driver)
            elif valve_driver.will_close():
                for pump_driver in valve_driver.pump_drivers:
                    potential_inactive_pump_drivers.add(pump_driver)

        inactive_pump_drivers = potential_inactive_pump_drivers.difference(active_pump_drivers)
        for pump_driver in inactive_pump_drivers:
            pump_driver.turn_off()

    def steer_valves(self):
        for valve_number, valve_driver in self._valve_drivers.iteritems():
            valve_driver.steer_output()

    def steer_pumps(self):
        active_pump_drivers = set()
        potential_inactive_pump_drivers = set()
        for valve_number, valve_driver in self._valve_drivers.iteritems():
            if valve_driver.is_open():
                for pump_driver in valve_driver.pump_drivers:
                    active_pump_drivers.add(pump_driver)
            else:
                for pump_driver in valve_driver.pump_drivers:
                    potential_inactive_pump_drivers.add(pump_driver)
        inactive_pump_drivers = potential_inactive_pump_drivers.difference(active_pump_drivers)

        for pump_driver in inactive_pump_drivers:
            pump_driver.turn_off()
        for pump_driver in active_pump_drivers:
            pump_driver.turn_on()

    def get_valve_driver(self, valve_number):
        valve_driver = self._valve_drivers.get(valve_number)
        if valve_driver is None:
            valve = Valve.get(number=valve_number)
            valve_driver = ValveDriver(valve)
            self._valve_drivers[valve.number] = valve_driver
        return valve_driver
