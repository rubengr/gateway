# Copyright (C) 2016 OpenMotics BVBA
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
The main module for the OpenMotics
"""
from platform_utils import System
System.import_eggs()

import logging
import time
import constants
from wiring import Graph, SingletonScope
from bus.om_bus_service import MessageService
from bus.om_bus_client import MessageClient
from cloud.cloud_api_client import CloudAPIClient
from cloud.events import EventSender
from serial import Serial
from signal import signal, SIGTERM
from ConfigParser import ConfigParser
from threading import Lock
from serial_utils import RS485
from gateway.webservice import WebInterface, WebService
from gateway.comm_led_controller import CommunicationLedController
from gateway.gateway_api import GatewayApi
from gateway.users import UserController
from gateway.metrics_controller import MetricsController
from gateway.metrics_collector import MetricsCollector
from gateway.metrics_caching import MetricsCacheController
from gateway.config import ConfigurationController
from gateway.scheduling import SchedulingController
from gateway.pulses import PulseCounterController
from gateway.observer import Observer, Event
from gateway.shutters import ShutterController
from urlparse import urlparse
from master.eeprom_controller import EepromController, EepromFile
from master.eeprom_extension import EepromExtension
from master.maintenance import MaintenanceService
from master.master_communicator import MasterCommunicator
from master.passthrough import PassthroughService
from power.power_communicator import PowerCommunicator
from power.power_controller import PowerController
from plugins.base import PluginController

logger = logging.getLogger("openmotics")


def setup_logger():
    """ Setup the OpenMotics logger. """

    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


class OpenmoticsService(object):

    def __init__(self):
        self.graph = Graph()

    def _register_classes(self):
        self.graph.register_factory('config_controller', ConfigurationController, scope=SingletonScope)
        self.graph.register_factory('user_controller', UserController, scope=SingletonScope)
        self.graph.register_factory('master_communicator', MasterCommunicator, scope=SingletonScope)
        self.graph.register_factory('metrics_controller', MetricsController, scope=SingletonScope)
        self.graph.register_factory('web_interface', WebInterface, scope=SingletonScope)
        self.graph.register_factory('observer', Observer, scope=SingletonScope)
        self.graph.register_factory('metrics_collector', MetricsCollector, scope=SingletonScope)
        self.graph.register_factory('plugin_controller', PluginController, scope=SingletonScope)
        self.graph.register_factory('power_communicator', PowerCommunicator, scope=SingletonScope)
        self.graph.register_factory('shutter_controller', ShutterController, scope=SingletonScope)
        self.graph.register_factory('gateway_api', GatewayApi, scope=SingletonScope)
        self.graph.register_factory('pulse_controller', PulseCounterController, scope=SingletonScope)
        self.graph.register_factory('eeprom_controller', EepromController, scope=SingletonScope)
        self.graph.register_factory('eeprom_file', EepromFile, scope=SingletonScope)
        self.graph.register_factory('eeprom_extension', EepromExtension, scope=SingletonScope)
        self.graph.register_factory('power_controller', PowerController, scope=SingletonScope)
        self.graph.register_factory('web_service', WebService, scope=SingletonScope)
        self.graph.register_factory('scheduling_controller', SchedulingController, scope=SingletonScope)
        self.graph.register_factory('maintenance_service', MaintenanceService, scope=SingletonScope)
        self.graph.register_factory('metrics_cache_controller', MetricsCacheController, scope=SingletonScope)
        self.graph.register_factory('cloud_api_client', CloudAPIClient)
        self.graph.register_factory('communication_led_controller', CommunicationLedController, scope=SingletonScope)
        self.graph.register_factory('event_sender', EventSender, scope=SingletonScope)
        self.graph.validate()

    def start(self):
        """ Main function. """
        logger.info('Starting OM core service...')

        # Get configuration
        config = ConfigParser()
        config.read(constants.get_config_file())

        defaults = {'username': config.get('OpenMotics', 'cloud_user'),
                    'password': config.get('OpenMotics', 'cloud_pass')}
        controller_serial_port = config.get('OpenMotics', 'controller_serial')
        passthrough_serial_port = config.get('OpenMotics', 'passthrough_serial')
        power_serial_port = config.get('OpenMotics', 'power_serial')
        gateway_uuid = config.get('OpenMotics', 'uuid')

        config_lock = Lock()
        schedule_lock = Lock()
        metrics_lock = Lock()

        # Create OM API client
        parsed_url = urlparse(config.get('OpenMotics', 'vpn_check_url'))
        cloud_endpoint = parsed_url.hostname
        cloud_port = parsed_url.port
        cloud_ssl = parsed_url.scheme == 'https'

        # Inject configuration values into environment
        self.graph.register_instance('message_client', MessageClient('openmotics_service'))
        self.graph.register_instance('gateway_uuid', gateway_uuid)
        self.graph.register_instance('cloud_endpoint', cloud_endpoint)
        self.graph.register_instance('cloud_port', cloud_port)
        self.graph.register_instance('cloud_ssl', cloud_ssl)
        self.graph.register_instance('cloud_api_version', 0)
        self.graph.register_instance('user_db', constants.get_config_database_file())
        self.graph.register_instance('user_db_lock', config_lock)
        self.graph.register_instance('config', defaults)
        self.graph.register_instance('token_timeout', 3600)
        self.graph.register_instance('config_db', constants.get_config_database_file())
        self.graph.register_instance('config_db_lock', config_lock)
        self.graph.register_instance('controller_serial', Serial(controller_serial_port, 115200))
        self.graph.register_instance('eeprom_db', constants.get_eeprom_extension_database_file())
        self.graph.register_instance('power_db', constants.get_power_database_file())
        self.graph.register_instance('scheduling_db', constants.get_scheduling_database_file())
        self.graph.register_instance('scheduling_db_lock', schedule_lock)
        self.graph.register_instance('power_serial', RS485(Serial(power_serial_port, 115200, timeout=None)))
        self.graph.register_instance('pulse_db', constants.get_pulse_counter_database_file())
        self.graph.register_instance('ssl_private_key', constants.get_ssl_private_key_file())
        self.graph.register_instance('ssl_certificate', constants.get_ssl_certificate_file())
        self.graph.register_instance('metrics_db', constants.get_metrics_database_file())
        self.graph.register_instance('metrics_db_lock', metrics_lock)
        if passthrough_serial_port:
            self.graph.register_instance('passthrough_serial', Serial(passthrough_serial_port, 115200))

        # Register DI factory classes into environment
        self._register_classes()

        # TODO: eliminate circular dependencies, so below can be autowired using DI
        metrics_controller = self.graph.get('metrics_controller')
        message_client = self.graph.get('message_client')
        web_interface = self.graph.get('web_interface')
        scheduling_controller = self.graph.get('scheduling_controller')
        observer = self.graph.get('observer')
        gateway_api = self.graph.get('gateway_api')
        metrics_collector = self.graph.get('metrics_collector')
        plugin_controller = self.graph.get('plugin_controller')
        web_service = self.graph.get('web_service')
        event_sender = self.graph.get('event_sender')
        message_client.add_event_handler(metrics_controller.event_receiver)
        web_interface.set_plugin_controller(plugin_controller)
        web_interface.set_metrics_collector(metrics_collector)
        web_interface.set_metrics_controller(metrics_controller)
        gateway_api.set_plugin_controller(plugin_controller)
        metrics_controller.add_receiver(metrics_controller.receiver)
        metrics_controller.add_receiver(web_interface.distribute_metric)
        scheduling_controller.set_webinterface(web_interface)
        metrics_collector.set_controllers(metrics_controller, plugin_controller)
        plugin_controller.set_webservice(web_service)
        plugin_controller.set_metrics_controller(metrics_controller)
        plugin_controller.set_metrics_collector(metrics_collector)
        observer.set_gateway_api(gateway_api)

        # TODO: make sure all subscribers only subscribe to the observer, not master directly

        # send master events to metrics collector
        observer.subscribe_master(Observer.MasterEvents.ON_INPUT_CHANGE, metrics_collector.on_input)
        observer.subscribe_master(Observer.MasterEvents.ON_OUTPUTS, metrics_collector.on_output)

        # send state changes to plugin_controller
        observer.subscribe_events(plugin_controller.process_observer_event)
        # TODO: move output and shutter also to plugin_controller.process_observer_event
        observer.subscribe_master(Observer.MasterEvents.ON_OUTPUTS, plugin_controller.process_output_status)
        observer.subscribe_master(Observer.MasterEvents.ON_SHUTTER_UPDATE, plugin_controller.process_shutter_status)

        # send all other events
        observer.subscribe_events(web_interface.send_event_websocket)
        observer.subscribe_events(event_sender.enqueue_event)

        if passthrough_serial_port:
            self.graph.register_factory('passthrough_service', PassthroughService, scope=SingletonScope)
            passthrough_service = self.graph.get('passthrough_service')
            passthrough_service.start()

        services = ['master_communicator', 'observer', 'power_communicator', 'metrics_controller',
                    'scheduling_controller', 'metrics_collector', 'web_service', 'gateway_api', 'plugin_controller',
                    'communication_led_controller', 'event_sender']
        for service in services:
            self.graph.get(service).start()

        signal_request = {'stop': False}

        def stop(signum, frame):
            """ This function is called on SIGTERM. """
            _ = signum, frame
            logger.info('Stopping OM core service...')
            services_to_stop = ['web_service', 'metrics_collector', 'metrics_controller', 'plugin_controller', 'event_sender']
            for service_to_stop in services_to_stop:
                self.graph.get(service_to_stop).stop()
            logger.info('Stopping OM core service... Done')
            signal_request['stop'] = True

        signal(SIGTERM, stop)
        logger.info('Starting OM core service... Done')
        while not signal_request['stop']:
            time.sleep(1)


if __name__ == "__main__":
    setup_logger()
    logger.info("Starting OpenMotics service")

    # TODO: move message service to separate process
    message_service = MessageService()
    message_service.start()

    openmotics_service = OpenmoticsService()
    openmotics_service.start()
