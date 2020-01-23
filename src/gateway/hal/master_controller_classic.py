# Copyright (C) 2019 OpenMotics BV
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
Module for communicating with the Master
"""
import logging
import time
from threading import Thread
from ioc import Injectable, Inject, INJECTED, Singleton
from gateway.hal.master_controller import MasterController, MasterEvent
from gateway.maintenance_communicator import InMaintenanceModeException
from master import master_api, eeprom_models
from master.eeprom_controller import EepromAddress
from master.eeprom_models import SensorConfiguration
from master.outputs import OutputStatus
from master.master_communicator import BackgroundConsumer
from serial_utils import CommunicationTimedOutException

logger = logging.getLogger("openmotics")


@Injectable.named('master_controller')
@Singleton
class MasterClassicController(MasterController):

    @Inject
    def __init__(self, master_communicator=INJECTED, eeprom_controller=INJECTED):
        """
        :type master_communicator: master.master_communicator.MasterCommunicator
        :type eeprom_controller: master.eeprom_controller.EepromController
        """
        super(MasterClassicController, self).__init__(master_communicator)
        self._eeprom_controller = eeprom_controller

        self._output_status = OutputStatus(on_output_change=self._output_changed)
        self._synchronization_thread = Thread(target=self._synchronize, name='ClassicMasterSynchronization')
        self._master_version = None
        self._master_online = False
        self._output_interval = 600
        self._output_last_updated = 0
        self._output_config = {}

        self._master_communicator.register_consumer(
            BackgroundConsumer(master_api.output_list(), 0, self._on_master_output_change, True)
        )

    #################
    # Private stuff #
    #################

    def _synchronize(self):
        while True:
            try:
                self._get_master_version()
                # Refresh if required
                if self._output_last_updated + self._output_interval < time.time():
                    self._refresh_outputs()
                    self._set_master_state(True)
                time.sleep(1)
            except CommunicationTimedOutException:
                logger.error('Got communication timeout during synchronization, waiting 10 seconds.')
                self._set_master_state(False)
                time.sleep(10)
            except InMaintenanceModeException:
                # This is an expected situation
                time.sleep(10)
            except Exception as ex:
                logger.exception('Unexpected error during synchronization: {0}'.format(ex))
                time.sleep(10)

    def _get_master_version(self):
        if self._master_version is None:
            self._master_version = self.get_firmware_version()
            self._set_master_state(True)

    def _set_master_state(self, online):
        if online != self._master_online:
            self._master_online = online

    #######################
    # Internal management #
    #######################

    def start(self):
        super(MasterClassicController, self).start()
        self._synchronization_thread.start()

    ##############
    # Public API #
    ##############

    def invalidate_caches(self):
        self._output_last_updated = 0

    def get_firmware_version(self):
        out_dict = self._master_communicator.do_command(master_api.status())
        return int(out_dict['f1']), int(out_dict['f2']), int(out_dict['f3'])

    # Memory (eeprom/fram)

    def eeprom_read_page(self, page):
        # TODO: Use eeprom controller
        return self._master_communicator.do_command(master_api.eeprom_list(), {'bank': page})['data']

    def fram_read_page(self, page):
        raise NotImplementedError('A classic master does not support FRAM')

    # Input

    def get_input_module_type(self, input_module_id):
        o = self._eeprom_controller.read(eeprom_models.InputConfiguration, input_module_id * 8, ['module_type'])
        return o.module_type

    def load_input(self, input_id, fields=None):
        o = self._eeprom_controller.read(eeprom_models.InputConfiguration, input_id, fields)
        if o.module_type not in ['i', 'I']:  # Only return 'real' inputs
            raise TypeError('The given id {0} is not an input, but {1}'.format(input_id, o.module_type))
        return o.serialize()

    def load_inputs(self, fields=None):
        return [o.serialize() for o in self._eeprom_controller.read_all(eeprom_models.InputConfiguration, fields)
                if o.module_type in ['i', 'I']]  # Only return 'real' inputs

    def save_inputs(self, inputs, fields=None):
        self._eeprom_controller.write_batch([eeprom_models.InputConfiguration.deserialize(input_)
                                             for input_ in inputs])

    # Outputs

    def set_output(self, output_id, state, dimmer=None, timer=None):
        if output_id < 0 or output_id > 240:
            raise ValueError('Output ID {0} not in range 0 <= id <= 240'.format(output_id))
        if dimmer is not None and dimmer < 0 or dimmer > 100:
            raise ValueError('Dimmer value {0} not in [0, 100]'.format(dimmer))
        if timer is not None and timer not in [150, 450, 900, 1500, 2220, 3120]:
            raise ValueError('Timer value {0} not in [150, 450, 900, 1500, 2220, 3120]'.format(timer))

        if dimmer is not None:
            master_version = self.get_firmware_version()
            if master_version >= (3, 143, 79):
                dimmer = int(0.63 * dimmer)
                self._master_communicator.do_command(
                    master_api.write_dimmer(),
                    {'output_nr': output_id, 'dimmer_value': dimmer}
                )
            else:
                dimmer = int(dimmer) / 10 * 10
                if dimmer == 0:
                    dimmer_action = master_api.BA_DIMMER_MIN
                elif dimmer == 100:
                    dimmer_action = master_api.BA_DIMMER_MAX
                else:
                    dimmer_action = getattr(master_api, 'BA_LIGHT_ON_DIMMER_{0}'.format(dimmer))
                self._master_communicator.do_command(
                    master_api.basic_action(),
                    {'action_type': dimmer_action, 'action_number': output_id}
                )

        if not state:
            self._master_communicator.do_command(
                master_api.basic_action(),
                {'action_type': master_api.BA_LIGHT_OFF, 'action_number': output_id}
            )
            return

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_LIGHT_ON, 'action_number': output_id}
        )

        if timer is not None:
            timer_action = getattr(master_api, 'BA_LIGHT_ON_TIMER_{0}_OVERRULE'.format(timer))
            self._master_communicator.do_command(
                master_api.basic_action(),
                {'action_type': timer_action, 'action_number': output_id}
            )

    def toggle_output(self, output_id):
        if output_id < 0 or output_id > 240:
            raise ValueError('Output ID not in range 0 <= id <= 240: %d' % output_id)

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_LIGHT_TOGGLE, 'action_number': output_id}
        )

    def load_output(self, output_id, fields=None):
        return self._eeprom_controller.read(eeprom_models.OutputConfiguration, output_id, fields).serialize()

    def load_outputs(self, fields=None):
        return [o.serialize() for o in self._eeprom_controller.read_all(eeprom_models.OutputConfiguration, fields)]

    def save_outputs(self, outputs, fields=None):
        self._eeprom_controller.write_batch([eeprom_models.OutputConfiguration.deserialize(output)
                                             for output in outputs])
        for output in outputs:
            output_nr, timer = output['id'], output.get('timer')
            if timer is not None:
                self._master_communicator.do_command(
                    master_api.write_timer(),
                    {'id': output_nr, 'timer': timer}
                )
        self._output_last_updated = 0

    def get_output_statuses(self):
        return self._output_status.get_outputs()

    def get_output_status(self, output_id):
        return self._output_status.get_output(output_id)

    def _refresh_outputs(self):
        self._output_config = self.load_outputs()
        number_of_outputs = self._master_communicator.do_command(master_api.number_of_io_modules())['out'] * 8
        outputs = []
        for i in xrange(number_of_outputs):
            outputs.append(self._master_communicator.do_command(master_api.read_output(), {'id': i}))
        self._output_status.full_update(outputs)
        self._output_last_updated = time.time()

    def _output_changed(self, output_id, status):
        """ Executed by the Output Status tracker when an output changed state """
        event_status = {'on': status['on']}
        # 1. only add value to status when handling dimmers
        if self._output_config[output_id]['module_type'] in ['d', 'D']:
            event_status['value'] = status['value']
        # 2. format response data
        event_data = {'id': output_id,
                      'status': event_status,
                      'location': {'room_id': self._output_config[output_id]['room']}}
        for callback in self._event_callbacks:
            callback(MasterEvent(event_type=MasterEvent.Types.OUTPUT_CHANGE, data=event_data))

    def _on_master_output_change(self, data):
        """ Triggers when the master informs us of an Output state change """
        self._output_status.partial_update(data['outputs'])

    # Shutters

    def shutter_up(self, shutter_id):
        self._master_communicator.do_basic_action(master_api.BA_SHUTTER_UP, shutter_id)

    def shutter_down(self, shutter_id):
        self._master_communicator.do_basic_action(master_api.BA_SHUTTER_DOWN, shutter_id)

    def shutter_stop(self, shutter_id):
        self._master_communicator.do_basic_action(master_api.BA_SHUTTER_STOP, shutter_id)

    def shutter_group_up(self, group_id):
        """ Make a shutter group go up. The shutters stop automatically when the up position is
        reached (after the predefined number of seconds).

        :param group_id: The id of the shutter group.
        :type group_id: Byte
        :returns:'status': 'OK'.
        """
        if group_id < 0 or group_id > 30:
            raise ValueError('id not in [0, 30]: %d' % group_id)

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_SHUTTER_GROUP_UP, 'action_number': id}
        )

        return {'status': 'OK'}

    def shutter_group_down(self, group_id):
        """ Make a shutter group go down. The shutters stop automatically when the down position is
        reached (after the predefined number of seconds).

        :param group_id: The id of the shutter group.
        :type group_id: Byte
        :returns:'status': 'OK'.
        """
        if group_id < 0 or group_id > 30:
            raise ValueError('id not in [0, 30]: %d' % group_id)

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_SHUTTER_GROUP_DOWN, 'action_number': group_id}
        )

        return {'status': 'OK'}

    def shutter_group_stop(self, group_id):
        """ Make a shutter group stop.

        :param group_id: The id of the shutter group.
        :type group_id: Byte
        :returns:'status': 'OK'.
        """
        if group_id < 0 or group_id > 30:
            raise ValueError('id not in [0, 30]: %d' % group_id)

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_SHUTTER_GROUP_STOP, 'action_number': group_id}
        )

        return {'status': 'OK'}

    # Sensors

    def get_sensor_temperature(self, sensor_id):
        if sensor_id is None or sensor_id == 255:
            return None
        return self.get_sensors_temperature()[sensor_id]

    def get_sensors_temperature(self):
        output = []
        sensor_list = self._master_communicator.do_command(master_api.sensor_temperature_list())
        for i in range(32):
            output.append(sensor_list['tmp%d' % i].get_temperature())
        return output

    def get_sensor_humidity(self, sensor_id):
        if sensor_id is None or sensor_id == 255:
            return None
        return self.get_sensors_humidity()[sensor_id]

    def get_sensors_humidity(self):
        output = []
        sensor_list = self._master_communicator.do_command(master_api.sensor_humidity_list())
        for i in range(32):
            output.append(sensor_list['hum%d' % i].get_humidity())
        return output

    def get_sensor_brightness(self, sensor_id):
        if sensor_id is None or sensor_id == 255:
            return None
        return self.get_sensors_brightness()[sensor_id]

    def get_sensors_brightness(self):
        output = []
        sensor_list = self._master_communicator.do_command(master_api.sensor_brightness_list())
        for i in range(32):
            output.append(sensor_list['bri%d' % i].get_brightness())
        return output

    def set_virtual_sensor(self, sensor_id, temperature, humidity, brightness):
        if 0 > sensor_id > 31:
            raise ValueError('sensor_id not in [0, 31]: %d' % sensor_id)

        self._master_communicator.do_command(master_api.set_virtual_sensor(),
                                              {'sensor': sensor_id,
                                               'tmp': master_api.Svt.temp(temperature),
                                               'hum': master_api.Svt.humidity(humidity),
                                               'bri': master_api.Svt.brightness(brightness)})

    def get_sensor_configuration(self, sensor_id, fields=None):
        """
        Get a specific sensor_configuration defined by its id.

        :param sensor_id: The id of the sensor_configuration
        :type sensor_id: Id
        :param fields: The field of the sensor_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        return self._eeprom_controller.read(SensorConfiguration, sensor_id, fields).serialize()

    def get_sensors_configuration(self, fields=None):
        """
        Get all sensor_configurations.

        :param fields: The field of the sensor_configuration to get. (None gets all fields)
        :type fields: List of strings
        :returns: list of sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        return [o.serialize() for o in self._eeprom_controller.read_all(SensorConfiguration, fields)]

    def set_sensor_configuration(self, config):
        """
        Set one sensor_configuration.

        :param config: The sensor_configuration to set
        :type config: sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        self._eeprom_controller.write(SensorConfiguration.deserialize(config))

    def set_sensors_configuration(self, config):
        """
        Set multiple sensor_configurations.

        :param config: The list of sensor_configurations to set
        :type config: list of sensor_configuration dict: contains 'id' (Id), 'name' (String[16]), 'offset' (SignedTemp(-7.5 to 7.5 degrees)), 'room' (Byte), 'virtual' (Boolean)
        """
        self._eeprom_controller.write_batch([SensorConfiguration.deserialize(o) for o in config])
        
    # Virtual modules

    def add_virtual_output_module(self):
        """ Adds a virtual output module.
        :returns: dict with 'status'.
        """
        module = self._master_communicator.do_command(master_api.add_virtual_module(), {'vmt': 'o'})
        return {'status': module.get('resp')}

    def add_virtual_dim_module(self):
        """ Adds a virtual dim module.
        :returns: dict with 'status'.
        """
        module = self._master_communicator.do_command(master_api.add_virtual_module(), {'vmt': 'd'})
        return {'status': module.get('resp')}

    def add_virtual_input_module(self):
        """ Adds a virtual input module.
        :returns: dict with 'status'.
        """
        module = self._master_communicator.do_command(master_api.add_virtual_module(), {'vmt': 'i'})
        return {'status': module.get('resp')}

    # Generic

    def get_status(self):
        """ Get the status of the Master.

        :returns: dict with 'time' (HH:MM), 'date' (DD:MM:YYYY), 'mode', 'version' (a.b.c)
                  and 'hw_version' (hardware version)
        """
        out_dict = self._master_communicator.do_command(master_api.status())
        return {'time': '%02d:%02d' % (out_dict['hours'], out_dict['minutes']),
                'date': '%02d/%02d/%d' % (out_dict['day'], out_dict['month'], out_dict['year']),
                'mode': out_dict['mode'],
                'version': '%d.%d.%d' % (out_dict['f1'], out_dict['f2'], out_dict['f3']),
                'hw_version': out_dict['h']}

    def get_version(self):
        """ Returns the master firmware version as tuple """
        master_version = self.get_status()['version']
        return tuple([int(x) for x in master_version.split('.')])

    def get_modules(self):
        """ Get a list of all modules attached and registered with the master.

        :returns: Dict with:
        * 'outputs' (list of module types: O,R,D),
        * 'inputs' (list of input module types: I,T,L,C)
        * 'shutters' (List of modules types: S).
        """
        mods = self._master_communicator.do_command(master_api.number_of_io_modules())

        inputs = []
        outputs = []
        shutters = []
        can_inputs = []

        for i in range(mods['in']):
            ret = self._master_communicator.do_command(
                master_api.read_eeprom(),
                {'bank': 2 + i, 'addr': 252, 'num': 1}
            )
            is_can = ret['data'][0] == 'C'
            ret = self._master_communicator.do_command(
                master_api.read_eeprom(),
                {'bank': 2 + i, 'addr': 0, 'num': 1}
            )
            if is_can:
                can_inputs.append(ret['data'][0])
            else:
                inputs.append(ret['data'][0])

        for i in range(mods['out']):
            ret = self._master_communicator.do_command(
                master_api.read_eeprom(),
                {'bank': 33 + i, 'addr': 0, 'num': 1}
            )
            outputs.append(ret['data'][0])

        for shutter in range(mods['shutter']):
            shutters.append('S')

        if len(can_inputs) > 0 and 'C' not in can_inputs:
            can_inputs.append('C')  # First CAN enabled installations didn't had this in the eeprom yet

        return {'outputs': outputs, 'inputs': inputs, 'shutters': shutters, 'can_inputs': can_inputs}

    def get_modules_information(self):
        """ Gets module information """

        def get_master_version(eeprom_address, _is_can=False):
            _module_address = self.__eeprom_controller.read_address(eeprom_address)
            formatted_address = '{0:03}.{1:03}.{2:03}.{3:03}'.format(ord(_module_address.bytes[0]),
                                                                     ord(_module_address.bytes[1]),
                                                                     ord(_module_address.bytes[2]),
                                                                     ord(_module_address.bytes[3]))
            try:
                if _is_can or _module_address.bytes[0].lower() == _module_address.bytes[0]:
                    return formatted_address, None, None
                _module_version = self.__master_communicator.do_command(master_api.get_module_version(),
                                                                        {'addr': _module_address.bytes},
                                                                        extended_crc=True,
                                                                        timeout=1)
                _firmware_version = '{0}.{1}.{2}'.format(_module_version['f1'], _module_version['f2'], _module_version['f3'])
                return formatted_address, _module_version['hw_version'], _firmware_version
            except CommunicationTimedOutException:
                return formatted_address, None, None

        information = {}

        # Master slave modules
        no_modules = self.__master_communicator.do_command(master_api.number_of_io_modules())
        for i in range(no_modules['in']):
            is_can = self.__eeprom_controller.read_address(EepromAddress(2 + i, 252, 1)).bytes == 'C'
            version_info = get_master_version(EepromAddress(2 + i, 0, 4), is_can)
            module_address, hardware_version, firmware_version = version_info
            module_type = self.__eeprom_controller.read_address(EepromAddress(2 + i, 0, 1)).bytes
            information[module_address] = {'type': module_type,
                                           'hardware': hardware_version,
                                           'firmware': firmware_version,
                                           'address': module_address,
                                           'is_can': is_can}
        for i in range(no_modules['out']):
            version_info = get_master_version(EepromAddress(33 + i, 0, 4))
            module_address, hardware_version, firmware_version = version_info
            module_type = self.__eeprom_controller.read_address(EepromAddress(33 + i, 0, 1)).bytes
            information[module_address] = {'type': module_type,
                                           'hardware': hardware_version,
                                           'firmware': firmware_version,
                                           'address': module_address}
        for i in range(no_modules['shutter']):
            version_info = get_master_version(EepromAddress(33 + i, 173, 4))
            module_address, hardware_version, firmware_version = version_info
            module_type = self.__eeprom_controller.read_address(EepromAddress(33 + i, 173, 1)).bytes
            information[module_address] = {'type': module_type,
                                           'hardware': hardware_version,
                                           'firmware': firmware_version,
                                           'address': module_address}

        return information

    def flash_leds(self, led_type, led_id):
        """ Flash the leds on the module for an output/input/sensor.

        :type led_type: byte
        :param led_type: The module type: output/dimmer (0), input (1), sensor/temperatur (2).
        :type led_id: byte
        :param led_id: The id of the output/input/sensor.
        :returns: dict with 'status' ('OK').
        """
        ret = self._master_communicator.do_command(master_api.indicate(),
                                                   {'type': led_type, 'id': led_id})
        return {'status': ret['resp']}

    def get_backup(self):
        """
        Get a backup of the eeprom of the master.

        :returns: String of bytes (size = 64kb).
        """
        retry = None
        output = ""
        bank = 0
        while bank < 256:
            try:
                output += self._master_communicator.do_command(
                    master_api.eeprom_list(),
                    {'bank': bank}
                )['data']
                bank += 1
            except CommunicationTimedOutException:
                if retry == bank:
                    raise
                retry = bank
                logger.warning('Got timeout reading bank {0}. Retrying...'.format(bank))
                time.sleep(2)  # Doing heavy reads on eeprom can exhaust the master. Give it a bit room to breathe.
        return output

    def factory_reset(self):
        # Wipe master EEPROM
        data = chr(255) * (256 * 256)
        self.restore(data)

    def cold_reset(self):
        """ Perform a cold reset on the master. Turns the power off, waits 5 seconds and
        turns the power back on.

        :returns: 'status': 'OK'.
        """
        _ = self  # Must be an instance method
        gpio_direction = open('/sys/class/gpio/gpio44/direction', 'w')
        gpio_direction.write('out')
        gpio_direction.close()

        def power(master_on):
            """ Set the power on the master. """
            gpio_file = open('/sys/class/gpio/gpio44/value', 'w')
            gpio_file.write('1' if master_on else '0')
            gpio_file.close()

        power(False)
        time.sleep(5)
        power(True)

        return {'status': 'OK'}

    def reset(self):
        """ Reset the master.

        :returns: emtpy dict.
        """
        self._master_communicator.do_command(master_api.reset())
        return dict()

    def restore(self, data):
        """
        Restore a backup of the eeprom of the master.

        :param data: The eeprom backup to restore.
        :type data: string of bytes (size = 64 kb).
        :returns: dict with 'output' key (contains an array with the addresses that were written).
        """
        ret = []
        (num_banks, bank_size, write_size) = (256, 256, 10)

        for bank in range(0, num_banks):
            read = self._master_communicator.do_command(master_api.eeprom_list(),
                                                         {'bank': bank})['data']
            for addr in range(0, bank_size, write_size):
                orig = read[addr:addr + write_size]
                new = data[bank * bank_size + addr: bank * bank_size + addr + len(orig)]
                if new != orig:
                    ret.append('B' + str(bank) + 'A' + str(addr))

                    self._master_communicator.do_command(
                        master_api.write_eeprom(),
                        {'bank': bank, 'address': addr, 'data': new}
                    )

        self._master_communicator.do_command(master_api.activate_eeprom(), {'eep': 0})
        ret.append('Activated eeprom')
        self._eeprom_controller.invalidate_cache()

        return {'output': ret}

    # Error functions

    def error_list(self):
        """ Get the error list per module (input and output modules). The modules are identified by
        O1, O2, I1, I2, ...

        :returns: dict with 'errors' key, it contains list of tuples (module, nr_errors).
        """
        error_list = self._master_communicator.do_command(master_api.error_list())
        return error_list['errors']

    def last_success(self):
        """ Get the number of seconds since the last successful communication with the master.
        """
        return self._master_communicator.get_seconds_since_last_success()

    def clear_error_list(self):
        """ Clear the number of errors.

        :returns: empty dict.
        """
        self._master_communicator.do_command(master_api.clear_error_list())
        return dict()

    def set_status_leds(self, status):
        """ Set the status of the leds on the master.

        :param status: whether the leds should be on or off.
        :type status: boolean.
        :returns: empty dict.
        """
        on = 1 if status is True else 0
        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_STATUS_LEDS, 'action_number': on}
        )
        return dict()

    # Actions

    def do_basic_action(self, action_type, action_number):
        """ Execute a basic action.

        :param action_type: The type of the action as defined by the master api.
        :type action_type: Integer [0, 254]
        :param action_number: The number provided to the basic action, its meaning depends on the \
        action_type.
        :type action_number: Integer [0, 254]
        """
        if action_type < 0 or action_type > 254:
            raise ValueError('action_type not in [0, 254]: %d' % action_type)

        if action_number < 0 or action_number > 254:
            raise ValueError('action_number not in [0, 254]: %d' % action_number)

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': action_type,
             'action_number': action_number}
        )

        return dict()

    def do_group_action(self, group_action_id):
        """ Execute a group action.

        :param group_action_id: The id of the group action
        :type group_action_id: Integer (0 - 159)
        :returns: empty dict.
        """
        if group_action_id < 0 or group_action_id > 159:
            raise ValueError('group_action_id not in [0, 160]: %d' % group_action_id)

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_GROUP_ACTION,
             'action_number': group_action_id}
        )

        return dict()

    # All lights off functions

    def set_all_lights_off(self):
        """ Turn all lights off.

        :returns: empty dict.
        """
        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_ALL_LIGHTS_OFF, 'action_number': 0}
        )
        return dict()

    def set_all_lights_floor_off(self, floor):
        """ Turn all lights on a given floor off.

        :returns: empty dict.
        """

        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_LIGHTS_OFF_FLOOR, 'action_number': floor}
        )
        return dict()

    def set_all_lights_floor_on(self, floor):
        """ Turn all lights on a given floor on.

        :returns: empty dict.
        """
        self._master_communicator.do_command(
            master_api.basic_action(),
            {'action_type': master_api.BA_LIGHTS_ON_FLOOR, 'action_number': floor}
        )
        return dict()



