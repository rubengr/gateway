"""Peewee migrations -- 001_thermostats_from_master.py.

Some examples (model - class or model name)::

    > Model = migrator.orm['model_name']            # Return model in current state by name

    > migrator.sql(sql)                             # Run custom SQL
    > migrator.python(func, *args, **kwargs)        # Run python code
    > migrator.create_model(Model)                  # Create a model (could be used as decorator)
    > migrator.remove_model(model, cascade=True)    # Remove a model
    > migrator.add_fields(model, **fields)          # Add fields to a model
    > migrator.change_fields(model, **fields)       # Change fields
    > migrator.remove_fields(model, *field_names, cascade=True)
    > migrator.rename_field(model, old_field_name, new_field_name)
    > migrator.rename_table(model, new_table_name)
    > migrator.add_index(model, *col_names, unique=False)
    > migrator.drop_index(model, *col_names)
    > migrator.add_not_null(model, *field_names)
    > migrator.drop_not_null(model, *field_names)
    > migrator.add_default(model, field_name, default)

"""

import peewee as pw
from ConfigParser import ConfigParser

import logging
import constants
from gateway.thermostat.gateway.thermostat_controller_gateway import ThermostatControllerGateway
from master.eeprom_controller import EepromController, EepromFile
from master.eeprom_extension import EepromExtension
from master.eeprom_models import ThermostatConfiguration, CoolingConfiguration
from master.master_communicator import MasterCommunicator
from serial import Serial

try:
    import playhouse.postgres_ext as pw_pext
except ImportError:
    pass

SQL = pw.SQL

logger = logging.getLogger('openmotics')


def get_eeprom_controller():
    config = ConfigParser()
    config.read(constants.get_config_file())
    controller_serial_port = config.get('OpenMotics', 'controller_serial')
    controller_serial = Serial(controller_serial_port, 115200)
    master_communicator = MasterCommunicator(controller_serial)
    db_filename = constants.get_eeprom_extension_database_file()
    eeprom_file = EepromFile(master_communicator)
    eeprom_extension = EepromExtension(db_filename)
    return EepromController(eeprom_file, eeprom_extension)


def migrate(migrator, database, fake=False, **kwargs):
    """Write your migrations here."""
    eeprom_controller = get_eeprom_controller()
    for thermostat_id in xrange(32):
        try:
            heating_config = eeprom_controller.read(ThermostatConfiguration, thermostat_id).serialize()
            ThermostatControllerGateway.create_or_update_thermostat_from_v0_api(thermostat_id,
                                                                                heating_config,
                                                                                'heating')
            cooling_config = eeprom_controller.read(CoolingConfiguration, thermostat_id).serialize()
            ThermostatControllerGateway.create_or_update_thermostat_from_v0_api(thermostat_id,
                                                                                cooling_config,
                                                                                'cooling')
        except Exception:
            logger.exception('Error occurred while migrating thermostat {}'.format(thermostat_id))


def rollback(migrator, database, fake=False, **kwargs):
    """Write your rollback migrations here."""
    pass
