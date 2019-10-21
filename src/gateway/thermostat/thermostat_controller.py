from wiring import provides, scope, inject, SingletonScope


class ThermostatController(object):

    @provides('thermostat_controller')
    @scope(SingletonScope)
    @inject(gateway_api='gateway_api')
    def __init__(self, gateway_api):
        self._gateway_api = gateway_api
        self._thermostats = {}
        self._thermostat_groups = {}

    def get_thermostat_by_id(self, thermostat_id):
        """ :raises ValueError if thermostat_id not in range [0, 32]. """
        if thermostat_id not in range(0, 32):
            raise ValueError('Thermostat not in [0,32]: %d' % thermostat_id)
        thermostat = self._thermostats.get(thermostat_id)
        """ :raises ValueError if thermostat_id not existing yet [0, 32]. """
        if thermostat is None:
            raise ValueError('Thermostat {} does not exist'.format(thermostat_id))
        return thermostat

    def get_thermostat_group_by_id(self, thermostat_group_id):
        """ :raises ValueError if thermostat_group_id not in range [0, 32]. """
        if thermostat_group_id not in range(0, 32):
            raise ValueError('Thermostat group not in [0,32]: %d' % thermostat_group_id)
        thermostat_group = self._thermostat_groups.get(thermostat_group_id)
        """ :raises ValueError if thermostat_id not existing yet [0, 32]. """
        if thermostat_group is None:
            raise ValueError('Thermostat group {} does not exist'.format(thermostat_group_id))
        return thermostat_group

    def get_thermostat_list(self):
        """ Get the thermostat list.
        """
        return self._thermostats.values()

    def get_thermostat_group_list(self):
        """ Get the thermostat list.
        """
        return self._thermostat_groups.values()

    def setpoint(self, thermostat_id, temperature):
        """ Set the current setpoint of a thermostat.

        :param thermostat_id: The id of the thermostat to set
        :type thermostat_id: Integer [0, 32]
        :param temperature: The temperature to set in degrees Celcius
        :type temperature: float
        :returns: dict with 'thermostat', 'config' and 'temp'
        """
        thermostat = self.get_thermostat_by_id(thermostat_id)
        thermostat.setpoint(temperature)

    def set_thermostat_mode(self, thermostat_id, thermostat_on, automatic=None, setpoint=None):
        """ Set the mode of the thermostats.

        :param thermostat_on: Whether the thermostats are on
        :type thermostat_on: boolean
        :param cooling_mode: Cooling mode (True) of Heating mode (False)
        :type cooling_mode: boolean | None
        :param cooling_on: Turns cooling ON when set to true.
        :type cooling_on: boolean | None
        :param automatic: Indicates whether the thermostat system should be set to automatic
        :type automatic: boolean | None
        :param setpoint: Requested setpoint (integer 0-5)
        :type setpoint: int | None
        :returns: dict with 'status'
        """
        thermostat = self.get_thermostat_by_id(thermostat_id)
        if cooling_mode is not None:
            thermostat.cooling_mode = cooling_mode
        if automatic is not None:
            thermostat.automatic = automatic
        if setpoint is not None:
            thermostat.setpoint = setpoint
        if thermostat_on:
            thermostat.run()

    def set_thermostat_group_mode(self, thermostat_group, thermostat_group_on, cooling_mode=False):
        """ Set the mode of the thermostats.
        :param thermostat_on: Whether the thermostats are on
        :type thermostat_on: boolean
        :param thermostat_on: Whether the thermostats are on
        :type thermostat_on: boolean
        :param cooling_mode: Cooling mode (True) of Heating mode (False)
        :type cooling_mode: boolean | None
        :param automatic: Indicates whether the thermostat system should be set to automatic
        :type automatic: boolean | None
        :param setpoint: Requested setpoint (integer 0-5)
        :type setpoint: int | None
        :returns: dict with 'status'
        """

        thermostat = self.get_thermostat_group_by_id(thermostat_group)

        self._running = thermostat_on
        self.cooling_mode = cooling_mode
        self.automatic = automatic
        self.setpoint(setpoint)






        _ = thermostat_on  # Still accept `thermostat_on` for backwards compatibility

        # Figure out whether the system should be on or off
        set_on = False
        if cooling_mode is True and cooling_on is True:
            set_on = True
        if cooling_mode is False:
            # Heating means threshold based
            global_config = self.get_global_thermostat_configuration()
            outside_sensor = global_config['outside_sensor']
            current_temperatures = self.get_sensor_temperature_status()
            if len(current_temperatures) > outside_sensor:
                current_temperature = current_temperatures[outside_sensor]
                set_on = global_config['threshold_temp'] > current_temperature
            else:
                set_on = True

        # Calculate and set the global mode
        mode = 0
        mode |= (1 if set_on is True else 0) << 7
        mode |= 1 << 6  # multi-tenant mode
        mode |= (1 if cooling_mode else 0) << 4
        if automatic is not None:
            mode |= (1 if automatic else 0) << 3

        check_basic_action(self.__master_communicator.do_basic_action(
            master_api.BA_THERMOSTAT_MODE, mode
        ))

        # Caclulate and set the cooling/heating mode
        cooling_heating_mode = 0
        if cooling_mode is True:
            cooling_heating_mode = 1 if cooling_on is False else 2

        check_basic_action(self.__master_communicator.do_basic_action(
            master_api.BA_THERMOSTAT_COOLING_HEATING, cooling_heating_mode
        ))

        # Then, set manual/auto
        if automatic is not None:
            action_number = 1 if automatic is True else 0
            check_basic_action(self.__master_communicator.do_basic_action(
                master_api.BA_THERMOSTAT_AUTOMATIC, action_number
            ))

        # If manual, set the setpoint if appropriate
        if automatic is False and setpoint is not None and 3 <= setpoint <= 5:
            check_basic_action(self.__master_communicator.do_basic_action(
                getattr(master_api, 'BA_ALL_SETPOINT_{0}'.format(setpoint)), 0
            ))

        self.__observer.invalidate_cache(Observer.Types.THERMOSTATS)
        self.__observer.increase_interval(Observer.Types.THERMOSTATS, interval=2, window=10)
        return {'status': 'OK'}

    def set_per_thermostat_mode(self, thermostat_id, automatic, setpoint):
        """ Set the setpoint/mode for a certain thermostat.

        :param thermostat_id: The id of the thermostat.
        :type thermostat_id: Integer [0, 31]
        :param automatic: Automatic mode (True) or Manual mode (False)
        :type automatic: boolean
        :param setpoint: The current setpoint
        :type setpoint: Integer [0, 5]
        :returns: dict with 'status'
        """
        if thermostat_id < 0 or thermostat_id > 31:
            raise ValueError('Thermostat_id not in [0, 31]: %d' % thermostat_id)

        if setpoint < 0 or setpoint > 5:
            raise ValueError('Setpoint not in [0, 5]: %d' % setpoint)

        if automatic:
            check_basic_action(self.__master_communicator.do_basic_action(
                master_api.BA_THERMOSTAT_TENANT_AUTO, thermostat_id
            ))
        else:
            check_basic_action(self.__master_communicator.do_basic_action(
                master_api.BA_THERMOSTAT_TENANT_MANUAL, thermostat_id
            ))

            check_basic_action(self.__master_communicator.do_basic_action(
                getattr(master_api, 'BA_ONE_SETPOINT_{0}'.format(setpoint)), thermostat_id
            ))

        self.__observer.invalidate_cache(Observer.Types.THERMOSTATS)
        self.__observer.increase_interval(Observer.Types.THERMOSTATS, interval=2, window=10)
        return {'status': 'OK'}


    def get_thermostats_status(self):

        def get_automatic_setpoint(_mode):
            _automatic = bool(_mode & 1 << 3)
            return _automatic, 0 if _automatic else (_mode & 0b00000111)

        thermostat_info = self._gateway_api.get_thermostat_list()
        thermostat_mode = self._gateway_api.get_thermostat_mode_list()
        aircos = self._gateway_api.get_airco_status()
        outputs = self.get_outputs()

        mode = thermostat_info['mode']
        thermostats_on = bool(mode & 1 << 7)
        cooling = bool(mode & 1 << 4)
        automatic, setpoint = get_automatic_setpoint(thermostat_mode['mode0'])

        fields = ['sensor', 'output0', 'output1', 'name', 'room']
        if cooling:
            thermostats_config = self._gateway_api.get_cooling_configurations(fields=fields)
        else:
            thermostats_config = self._gateway_api.get_thermostat_configurations(fields=fields)

        thermostats = []
        for thermostat_id in xrange(32):
            config = thermostats_config[thermostat_id]
            if (config['sensor'] <= 31 or config['sensor'] == 240) and config['output0'] <= 240:
                t_mode = thermostat_mode['mode{0}'.format(thermostat_id)]
                t_automatic, t_setpoint = get_automatic_setpoint(t_mode)
                thermostat = {'id': thermostat_id,
                              'act': thermostat_info['tmp{0}'.format(thermostat_id)].get_temperature(),
                              'csetp': thermostat_info['setp{0}'.format(thermostat_id)].get_temperature(),
                              'outside': thermostat_info['outside'].get_temperature(),
                              'mode': t_mode,
                              'automatic': t_automatic,
                              'setpoint': t_setpoint,
                              'name': config['name'],
                              'sensor_nr': config['sensor'],
                              'airco': aircos['ASB{0}'.format(thermostat_id)]}
                for output in [0, 1]:
                    output_nr = config['output{0}'.format(output)]
                    if output_nr < len(outputs) and outputs[output_nr]['status']:
                        thermostat['output{0}'.format(output)] = outputs[output_nr]['dimmer']
                    else:
                        thermostat['output{0}'.format(output)] = 0
                thermostats.append(thermostat)

        thermostats_info = {'thermostats_on': thermostats_on,
                            'automatic': automatic,
                            'setpoint': setpoint,
                            'cooling': cooling,
                            'status': thermostats}

        return thermostats_config, thermostats_info
