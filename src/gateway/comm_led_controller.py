import time
import logging
from wiring import provides, scope, inject, SingletonScope
from threading import Thread
from bus.om_bus_events import OMBusEvents

logger = logging.getLogger("openmotics")


class CommunicationLedController(object):

    @provides('observer')
    @scope(SingletonScope)
    @inject(master_communicator='master_communicator', power_communicator='power_communicator', message_client='message_client')
    def __init__(self, master_communicator, power_communicator, message_client):
        """
        Blink the serial leds if necessary.
        :type message_client: bus.om_bus_client.MessageClient
        :type master_communicator: master.master_communicator.MasterCommunicator
        :type power_communicator: power.power_communicator.PowerCommunicator
        """
        self._master_communicator = master_communicator
        self._power_communicator = power_communicator
        self._message_client = message_client

        self._thread = Thread(target=self.led_driver)
        self._thread.setName("Serial led driver thread")
        self._thread.daemon = True

    def start(self):
        logger.info("Starting commmunications led controller...")
        self._thread.start()
        logger.info("Starting commmunications led controller... Done")

    def led_driver(self):
        master = (0, 0)
        power = (0, 0)

        while True:
            new_master = (self._master_communicator.get_bytes_read(), self._master_communicator.get_bytes_written())
            if self._power_communicator is None:
                new_power = (0, 0)
            else:
                new_power = (self._power_communicator.get_bytes_read(), self._power_communicator.get_bytes_written())

            if master[0] != new_master[0] or master[1] != new_master[1]:
                self._message_client.send_event(OMBusEvents.SERIAL_ACTIVITY, 5)
            if power[0] != new_power[0] or power[1] != new_power[1]:
                self._message_client.send_event(OMBusEvents.SERIAL_ACTIVITY, 4)

            master = new_master
            power = new_power
            time.sleep(0.1)
