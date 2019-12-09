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
Module to handle Errors from the Core

More information: https://wiki.openmotics.com/index.php/Error_List_AIO
"""

import logging

logger = logging.getLogger('openmotics')


class Error(object):
    class Types(object):
        OUTPUT_ERROR = 'OUTPUT_ERROR'
        INPUT_ERROR = 'INPUT_ERROR'
        SENSOR_ERROR = 'SENSOR_ERROR'
        DEFAULT_SWITCH_CASE_TRIGGERED = 'DEFAULT_SWITCH_CASE_TRIGGERED'
        I2C_ERROR = 'I2C_ERROR'
        UART_ERROR = 'UART_ERROR'
        SM_UPDATE_TIME_DATE = 'SM_UPDATE_TIME_DATE'
        SM_IMMEDIATE_QUEUE = 'SM_IMMEDIATE_QUEUE'
        SM_GROUP_QUEUE = 'SM_GROUP_QUEUE'
        SM_TIMER = 'SM_TIMER'
        SM_EEPROM_ACTIVATE_STATE = 'SM_EEPROM_ACTIVATE_STATE'
        SM_PERFORM_EEPROM_ACTIVATE = 'SM_PERFORM_EEPROM_ACTIVATE'
        SM_CLI_PRINT = 'SM_CLI_PRINT'
        SM_CAN_QUEUE = 'SM_CAN_QUEUE'
        SM_CAN = 'SM_CAN'
        SM_EXECUTE_EVERY_MINUTE = 'SM_EXECUTE_EVERY_MINUTE'
        SM_EXECUTE_GROUP_ACTION = 'SM_EXECUTE_GROUP_ACTION'
        SM_GROUP_DELAY_QUEUE = 'SM_GROUP_DELAY_QUEUE'
        SM_CAN_TX_QUEUE = 'SM_CAN_TX_QUEUE'
        MICRO_CAN_WATCHDOG_RESET = 'MICRO_CAN_WATCHDOG_RESET'
        MICRO_CAN_WARM_RESET = 'MICRO_CAN_WARM_RESET'
        MISSING_ENDIF = 'MISSING_ENDIF'
        COMMAND_ERROR = 'COMMAND_ERROR'
        UNKNOWN = 'UNKNOWN'

    StateMachineTypes = [Types.SM_UPDATE_TIME_DATE, Types.SM_IMMEDIATE_QUEUE, Types.SM_GROUP_QUEUE, Types.SM_TIMER,
                         Types.SM_EEPROM_ACTIVATE_STATE, Types.SM_PERFORM_EEPROM_ACTIVATE, Types.SM_CLI_PRINT,
                         Types.SM_CAN_QUEUE, Types.SM_CAN, Types.SM_EXECUTE_EVERY_MINUTE, Types.SM_EXECUTE_GROUP_ACTION,
                         Types.SM_GROUP_DELAY_QUEUE, Types.SM_CAN_TX_QUEUE]

    def __init__(self, data):
        self._parameter_a = data['parameter_a']
        self._parameter_b = data['parameter_b']
        self._parameter_c = data['parameter_c']
        self._type = data['type']

    @property
    def type(self):
        type_map = {0: Error.Types.OUTPUT_ERROR,
                    1: Error.Types.INPUT_ERROR,
                    2: Error.Types.SENSOR_ERROR,
                    3: Error.Types.DEFAULT_SWITCH_CASE_TRIGGERED,
                    4: Error.Types.I2C_ERROR,
                    5: Error.Types.UART_ERROR,
                    6: Error.Types.SM_UPDATE_TIME_DATE,
                    7: Error.Types.SM_IMMEDIATE_QUEUE,
                    8: Error.Types.SM_GROUP_QUEUE,
                    9: Error.Types.SM_TIMER,
                    10: Error.Types.SM_EEPROM_ACTIVATE_STATE,
                    11: Error.Types.SM_PERFORM_EEPROM_ACTIVATE,
                    12: Error.Types.SM_CLI_PRINT,
                    13: Error.Types.SM_CAN_QUEUE,
                    14: Error.Types.MICRO_CAN_WATCHDOG_RESET,
                    15: Error.Types.MICRO_CAN_WARM_RESET,
                    16: Error.Types.SM_CAN,
                    17: Error.Types.SM_EXECUTE_EVERY_MINUTE,
                    18: Error.Types.SM_EXECUTE_GROUP_ACTION,
                    19: Error.Types.MISSING_ENDIF,
                    20: Error.Types.SM_GROUP_DELAY_QUEUE,
                    21: Error.Types.SM_CAN_TX_QUEUE,
                    254: Error.Types.COMMAND_ERROR}
        return type_map.get(self._type, Error.Types.UNKNOWN)

    @property
    def error(self):
        try:
            if self.type == Error.Types.OUTPUT_ERROR:
                if self._parameter_a == 0:
                    return 'Output module {0} is not responding'.format(self._parameter_b)
                if self._parameter_a == 1:
                    return 'Address conflict during initialisation on {0}'.format(Error._decode_address(self._parameter_b, self._parameter_c))
                if self._parameter_a == 2:
                    return 'Tried to switch output {0} ON while paired output {1} was already ON. Both will be switched OFF'.format(self._parameter_b, self._parameter_c)
            if self.type == Error.Types.INPUT_ERROR:
                if self._parameter_a == 0:
                    return 'Input module {0} is not responding'.format(self._parameter_b)
                if self._parameter_a == 1:
                    return 'Address conflict during initialisation on {0}'.format(Error._decode_address(self._parameter_b, self._parameter_c))
            if self.type == Error.Types.SENSOR_ERROR:
                if self._parameter_a == 0:
                    return 'Sensor module {0} is not responding'.format(self._parameter_b)
                if self._parameter_a == 1:
                    return 'Address conflict during initialisation on {0}'.format(Error._decode_address(self._parameter_b, self._parameter_c))
                if self._parameter_a == 2:
                    return 'Configured sensor {0} did not update value in the last 2 minutes'.format(self._parameter_b)
            if self.type == Error.Types.DEFAULT_SWITCH_CASE_TRIGGERED:
                return 'Default switch/case triggered. Parameters {0} / {1} / {2}'.format(self._parameter_a, self._parameter_b, self._parameter_c)
            if self.type == Error.Types.I2C_ERROR:
                return 'Detected {0} I2C error(s) on state machine phase {1} on port {2}'.format(self._parameter_c, self._parameter_a, self._parameter_b)
            if self.type == Error.Types.UART_ERROR:
                return 'UART receiving error detected on state machine phase {0} on port {1}'.format(self._parameter_a, self._parameter_b)
            if self.type in Error.StateMachineTypes:
                return 'State machine {0} blocked. Parameters {1} / {2} / {3}'.format(self.type.replace('SM_', ''), self._parameter_a, self._parameter_b, self._parameter_c)
            if self.type == Error.Types.MICRO_CAN_WATCHDOG_RESET:
                return 'Watchdog reset on uCAN. Parameters {0} / {1} / {2}'.format(self._parameter_a, self._parameter_b, self._parameter_c)
            if self.type == Error.Types.MICRO_CAN_WARM_RESET:
                return 'Warm reset on uCAN. Parameters {0} / {1} / {2}'.format(self._parameter_a, self._parameter_b, self._parameter_c)
            if self.type == Error.Types.COMMAND_ERROR:
                if self._parameter_a == 0:
                    return 'CRC error: An API instruction {0} has generated a CRC error and has not been interpreted'.format(Error._extract_command(self._parameter_b))
                if self._parameter_b == 10:
                    return 'API parameters send on instruction {0} not in range to be an acceptable value'.format(Error._extract_command(self._parameter_b))
            else:
                return 'Unknown error type {0}. Parameters {1} / {2} / {3}'.format(self._type, self._parameter_a, self._parameter_b, self._parameter_c)
        except Exception as ex:
            logger.debug('Unexpected error parsing errors: {0}'.format(ex))
        return 'Unknown error on type {0}. Parameters {1} / {2} / {3}'.format(self.type, self._parameter_a, self._parameter_b, self._parameter_c)

    @staticmethod
    def _extract_command(word):
        first = word >> 8 & 0xFF
        second = word & 0xFF
        return ''.join([str(chr(c)) if 32 < c <= 126 else '.' for c in [first, second]])

    @staticmethod
    def _decode_address(first_word, second_word):
        return '.'.join([first_word >> 8 & 0xFF, first_word & 0xFF, second_word >> 8 & 0xFF, second_word & 0xFF])

    def __str__(self):
        return '{0} ({1})'.format(self.type, self.error)
