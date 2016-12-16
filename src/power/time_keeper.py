'''
Created on Mar 2, 2013

@author: fryckbos
'''
import logging
LOGGER = logging.getLogger("openmotics")

import time
from datetime import datetime
from threading import Thread

import power.power_api as power_api

class TimeKeeper(object):
    """ The TimeKeeper keeps track of time and sets the day or night mode on the power modules. """

    def __init__(self, power_communicator, power_controller, period):
        self.__power_communicator = power_communicator
        self.__power_controller = power_controller
        self.__period = period

        self.__mode = {}

        self.__thread = None
        self.__stop = False

    def start(self):
        """ Start the background thread of the TimeKeeper. """
        if self.__thread == None:
            LOGGER.info("Starting TimeKeeper")
            self.__stop = False
            self.__thread = Thread(target=self.__run, name="TimeKeeper thread")
            self.__thread.daemon = True
            self.__thread.start()
        else:
            raise Exception("TimeKeeper thread already running.")

    def stop(self):
        """ Stop the background thread in the TimeKeeper. """
        if self.__thread != None:
            self.__stop = True
        else:
            raise Exception("TimeKeeper thread not running.")

    def __run(self):
        """ Code for the background thread. """
        while not self.__stop:
            try:
                self.__run_once()
            except:
                LOGGER.exception("Exception in TimeKeeper")

            time.sleep(self.__period)

        LOGGER.info("Stopped TimeKeeper")
        self.__thread = None

    def __run_once(self):
        """ One run of the background thread. """
        date = datetime.now()
        for module in self.__power_controller.get_power_modules().values():
            version = module['version']
            daynight = []
            for i in range(power_api.NUM_PORTS[version]):
                if self.is_day_time(module['times%d' % i], date):
                    daynight.append(power_api.DAY)
                else:
                    daynight.append(power_api.NIGHT)

            self.__set_mode(version, module['address'], daynight)

    def is_day_time(self, times, date):
        """ Check if a date is in day time. """
        if times == None:
            times = [0 for _ in range(14)]
        else:
            times = [int(t.replace(":", "")) for t in times.split(",")]

        day_of_week = date.weekday() # 0 = Monday, 6 = Sunday
        current_time = date.hour * 100 + date.minute

        start = times[day_of_week * 2]
        stop = times[day_of_week * 2 + 1]

        return current_time >= start and current_time < stop

    def __set_mode(self, version, address, bytes):
        """ Set the power modules mode. """
        if address not in self.__mode or self.__mode[address] != bytes:
            LOGGER.info("Setting day/night mode to " + str(bytes))
            self.__power_communicator.do_command(address, power_api.set_day_night(version), *bytes)
            self.__mode[address] = bytes
