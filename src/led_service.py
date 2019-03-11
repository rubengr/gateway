# Copyright (C) 2019 OpenMotics BVBA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
Service that drives the leds and checks the switch on the front panel of the gateway.
This service allows other services to set the leds over dbus and check whether the
gateway is in authorized mode.
"""
import sys
import fcntl
import time
import gobject
from threading import Thread
from ConfigParser import ConfigParser

from bus.dbus_service import DBusService
from bus.dbus_events import DBusEvents
from platform_utils import Hardware
import constants

AUTH_MODE_LEDS = [Hardware.Led.ALIVE, Hardware.Led.CLOUD, Hardware.Led.VPN, Hardware.Led.COMM_1, Hardware.Led.COMM_2]


class LOGGER(object):
    @staticmethod
    def log(line):
        sys.stdout.write('{0}\n'.format(line))
        sys.stdout.flush()


class LedController(object):
    """
    The LEDController contains all logic to control the leds, and read out the physical buttons
    """

    def __init__(self, i2c_device, i2c_address, input_button):
        self._i2c_device = i2c_device
        self._i2c_address = i2c_address
        self._input_button = input_button
        self._input_button_pressed_since = None
        self._input_button_released = True
        self._ticks = 0

        self._network_enabled = False
        self._network_activity = False
        self._network_bytes = 0

        self._serial_activity = {4: False, 5: False}
        self._enabled_leds = {}
        self._previous_leds = {}
        self._last_i2c_led_code = 0

        self._indicate_started = 0
        self._indicate_pointer = 0
        self._indicate_sequence = [True, False, False, False]

        self._authorized_mode = False
        self._authorized_timeout = 0

        self._check_states_thread = None

        self._last_run_i2c = 0
        self._last_run_gpio = 0
        self._last_state_check = 0
        self._last_button_check = 0

        self._gpio_led_config = Hardware.get_gpio_led_config()
        self._i2c_led_config = Hardware.get_i2c_led_config()
        for led in self._gpio_led_config.keys() + self._i2c_led_config.keys():
            self._enabled_leds[led] = False
            self._write_leds()

    def start(self):
        """ Start the leds and buttons thread. """
        self._check_states_thread = Thread(target=self._check_states)
        self._check_states_thread.daemon = True
        self._check_states_thread.start()

    def set_led(self, led_name, enable):
        """ Set the state of a LED, enabled means LED on in this context. """
        self._enabled_leds[led_name] = bool(enable)

    def toggle_led(self, led_name):
        """ Toggle the state of a LED. """
        self._enabled_leds[led_name] = not self._enabled_leds.get(led_name, False)

    def serial_activity(self, port):
        """ Report serial activity on the given serial port. Port is 4 or 5. """
        self._serial_activity[port] = True

    @staticmethod
    def _is_button_pressed(gpio_pin):
        """ Read the input button: returns True if the button is pressed, False if not. """
        with open('/sys/class/gpio/gpio{0}/value'.format(gpio_pin), 'r') as fh_inp:
            line = fh_inp.read()
        return int(line) == 0

    def _write_leds(self):
        """ Set the LEDs using the current status. """
        try:
            # Get i2c code
            code = 0
            for led in self._i2c_led_config:
                if self._enabled_leds.get(led, False) is True:
                    code |= self._i2c_led_config[led]
            if self._authorized_mode:
                # Light all leds in authorized mode
                for led in AUTH_MODE_LEDS:
                    code |= self._i2c_led_config.get(led, 0)
            code = (~ code) & 255

            # Push code if needed
            if code != self._last_i2c_led_code:
                self._last_i2c_led_code = code
                with open(self._i2c_device, 'r+', 1) as i2c:
                    fcntl.ioctl(i2c, Hardware.IOCTL_I2C_SLAVE, self._i2c_address)
                    i2c.write(chr(code))
                    self._last_run_i2c = time.time()
            else:
                self._last_run_i2c = time.time()
        except Exception as exception:
            LOGGER.log('Error while writing to i2c: {0}'.format(exception))

        for led in self._gpio_led_config:
            on = self._enabled_leds.get(led, False)
            if self._previous_leds.get(led) != on:
                self._previous_leds[led] = on
                try:
                    gpio = self._gpio_led_config[led]
                    with open('/sys/class/gpio/gpio{0}/value'.format(gpio), 'w') as fh_s:
                        fh_s.write('1' if on else '0')
                        self._last_run_gpio = time.time()
                except IOError:
                    pass  # The GPIO doesn't exist or is read only
            else:
                self._last_run_gpio = time.time()

    def _check_states(self):
        """ Checks various states of the system (network) """
        while True:
            try:
                with open('/sys/class/net/eth0/carrier', 'r') as fh_up:
                    line = fh_up.read()
                self._network_enabled = int(line) == 1

                with open('/proc/net/dev', 'r') as fh_stat:
                    for line in fh_stat.readlines():
                        if 'eth0' in line:
                            received, transmitted = 0, 0
                            parts = line.split()
                            if len(parts) == 17:
                                received = parts[1]
                                transmitted = parts[9]
                            elif len(parts) == 16:
                                (_, received) = tuple(parts[0].split(':'))
                                transmitted = parts[8]
                            new_bytes = received + transmitted
                            if self._network_bytes != new_bytes:
                                self._network_bytes = new_bytes
                                self._network_activity = True
                            else:
                                self._network_activity = False
            except Exception as exception:
                LOGGER.log('Error while checking states: {0}'.format(exception))
            self._last_state_check = time.time()
            time.sleep(0.5)

    def drive_leds(self):
        """ This drives different leds (status, alive and serial) """
        try:
            now = time.time()
            if now - 30 < self._indicate_started < now:
                self.set_led(Hardware.Led.STATUS, self._indicate_sequence[self._indicate_pointer])
                self._indicate_pointer = self._indicate_pointer + 1 if self._indicate_pointer < len(self._indicate_sequence) - 1 else 0
            else:
                self.set_led(Hardware.Led.STATUS, not self._network_enabled)
            if self._network_activity:
                self.toggle_led(Hardware.Led.ALIVE)
            else:
                self.set_led(Hardware.Led.ALIVE, False)
            # Calculate serial led states
            comm_map = {4: Hardware.Led.COMM_1,
                        5: Hardware.Led.COMM_2}
            for uart in [4, 5]:
                if self._serial_activity[uart]:
                    self.toggle_led(comm_map[uart])
                else:
                    self.set_led(comm_map[uart], False)
                self._serial_activity[uart] = False
            # Update all leds
            self._write_leds()
        except Exception as exception:
            LOGGER.log('Error while driving leds: {0}'.format(exception))
        gobject.timeout_add(250, self.drive_leds)

    def check_button(self):
        """ Handles input button presses """
        try:
            button_pressed = LedController._is_button_pressed(self._input_button)
            if button_pressed is False:
                self._input_button_released = True
            if self._authorized_mode:
                if time.time() > self._authorized_timeout or (button_pressed and self._input_button_released):
                    self._authorized_mode = False
            else:
                if button_pressed:
                    self._ticks += 0.25
                    self._input_button_released = False
                    if self._input_button_pressed_since is None:
                        self._input_button_pressed_since = time.time()
                    if self._ticks > 5.75:  # After 5.75 seconds + time to execute the code it should be pressed between 5.8 and 6.5 seconds.
                        self._authorized_mode = True
                        self._authorized_timeout = time.time() + 60
                        self._input_button_pressed_since = None
                        self._ticks = 0
                else:
                    self._input_button_pressed_since = None
        except Exception as exception:
            LOGGER.log('Error while checking button: {0}'.format(exception))
        self._last_button_check = time.time()
        gobject.timeout_add(250, self.check_button)

    def event_receiver(self, event, payload):
        if event == DBusEvents.CLOUD_REACHABLE:
            self.set_led(Hardware.Led.CLOUD, payload)
        elif event == DBusEvents.VPN_OPEN:
            self.set_led(Hardware.Led.VPN, payload)
        elif event == DBusEvents.SERIAL_ACTIVITY:
            self.serial_activity(payload)
        elif event == DBusEvents.INDICATE_GATEWAY:
            self._indicate_started = time.time()

    def get_state(self):
        return {'run_gpio': self._last_run_gpio,
                'run_i2c': self._last_run_i2c,
                'run_buttons': self._last_button_check,
                'run_state_check': self._last_state_check,
                'authorized_mode': self._authorized_mode}


def main():
    """
    The main function runs a loop that waits for dbus calls, drives the leds and reads the
    switch.
    """
    try:
        config = ConfigParser()
        config.read(constants.get_config_file())
        i2c_address = int(config.get('OpenMotics', 'leds_i2c_address'), 16)

        led_controller = LedController(Hardware.get_i2c_device(), i2c_address, Hardware.get_gpio_input())
        led_controller.start()
        led_controller.set_led(Hardware.Led.POWER, True)

        DBusService('led_service',
                    event_receiver=lambda *args, **kwargs: led_controller.event_receiver(*args, **kwargs),
                    get_state=led_controller.get_state)

        LOGGER.log("Running led service.")
        mainloop = gobject.MainLoop()
        gobject.timeout_add(250, led_controller.drive_leds)
        gobject.timeout_add(250, led_controller.check_button)
        mainloop.run()
    except Exception as exception:
        LOGGER.log('Error starting led service: {0}'.format(exception))


if __name__ == '__main__':
    main()
