import os
import io

from sensors.common.constants import *
from sensors.config.constants import *
from sensors.domain.observed_property import *
from sensors.domain.thing import *
from sensors.domain.transport import *

from ruamel import yaml


class ConfigurationError(Exception):
    """Exception raised for errors in configuration

    """

    def __init__(self, message):
        self.message = message


class Config():

    class __Config:
        def __init__(self):
            self.config = self.get_configuration()

        @classmethod
        def get_configuration(cls):
            """

            :return: Dictionary representing configuration
            """
            yaml_path = os.environ.get(ENV_YAML_PATH)
            if yaml_path is None:
                _raise_config_error("No configuration file defined, please make sure environment variable ${0} is set".\
                                    format(ENV_YAML_PATH))
            config_raw = None
            with io.open(yaml_path, 'r') as f:
                config_raw = yaml.safe_load(f)

            # First-order error checking of raw config
            if config_raw is None:
                _raise_config_error("Unable to parse configuration in YAML {0}.".format(yaml_path))
            if CFG_THING not in config_raw:
                _raise_config_error("Element {0} not configured in YAML {1}.".format(CFG_THING,
                                                                                     yaml_path))
            if CFG_SENSORS not in config_raw:
                _raise_config_error("Element {0} not configured in YAML {1}.". \
                                    format(CFG_SENSORS, yaml_path))
            sensors = config_raw[CFG_SENSORS]
            if type(sensors) != list:
                _raise_config_error("Element {0} with value {1} is invalid in YAML {2}.". \
                                    format(CFG_SENSORS, str(sensors), yaml_path))
            if len(sensors) < 1:
                _raise_config_error("Element {0} not configured in YAML {1}.".format(CFG_SENSORS,
                                                                                     yaml_path))
            if CFG_TRANSPORTS not in config_raw:
                _raise_config_error("Element {0} not configured in YAML {1}.".format(CFG_TRANSPORTS,
                                                                                     yaml_path))
            transports = config_raw[CFG_TRANSPORTS]
            if type(transports) != list:
                _raise_config_error("Element {0} with value {1} is invalid in YAML {2}.". \
                                    format(CFG_TRANSPORTS, str(transports), yaml_path))

            # Convert raw config elements to ones easier to deal with (doing
            # validation along the way).
            ds_id_present = set()
            c = {}

            # Simulator
            simulator_enabled = False
            if CFG_SIMULATOR in config_raw:
                simulator_enabled = get_config_element(CFG_ENABLED, config_raw[CFG_SIMULATOR], CFG_SIMULATOR,
                                                       optional=True)
                if simulator_enabled is None:
                    simulator_enabled = False
            c[CFG_SIMULATOR] = simulator_enabled

            # Logging
            logger_path = DEFAULT_LOGGER_PATH
            if CFG_LOGGING in config_raw:
                logger_path = get_config_element(CFG_LOGGING_LOGGER_PATH, config_raw[CFG_LOGGING], CFG_LOGGING,
                                                 optional=True)
                if logger_path is None:
                    logger_path = DEFAULT_LOGGER_PATH
            c[CFG_LOGGING_LOGGER_PATH] = logger_path

            # Spooler
            db_path = DEFAULT_DB_PATH
            if CFG_SPOOLER in config_raw:
                db_path = get_config_element(CFG_SPOOLER_DB_PATH, config_raw[CFG_SPOOLER], CFG_SPOOLER,
                                             optional=True)
                if db_path is None:
                    db_path = DEFAULT_DB_PATH
            c[CFG_SPOOLER_DB_PATH] = db_path

            # Thing
            thing_id = get_config_element(CFG_ID, config_raw[CFG_THING], CFG_THING)
            foi_id = get_config_element(CFG_LOCATION_ID, config_raw[CFG_THING], CFG_THING)
            c[CFG_THING] = Thing(thing_id, foi_id)

            # Sensors
            sensor_objects = []
            for s in sensors:
                sensor_type = get_config_element(CFG_TYPE, s, CFG_SENSOR)
                observed_properties = get_config_element(CFG_OBSERVED_PROPERTIES, s, CFG_SENSOR)
                if len(observed_properties) < 1:
                    _raise_config_error("No observed properties defined in sensor {0} in YAML {1}". \
                                        format(str(s), yaml_path))
                op_objects = []
                for op in observed_properties:
                    op_name = get_config_element(CFG_NAME, op, CFG_OBSERVED_PROPERTY)
                    op_ds_id = get_config_element(CFG_DATASTREAM_ID, op, CFG_OBSERVED_PROPERTY)
                    # Make sure this datastream_id hasn't already been encountered
                    if op_ds_id in ds_id_present:
                        _raise_config_error("Datastream with ID {0} is specified more than once in YAML {1}". \
                                            format(op_ds_id, yaml_path))
                    else:
                        ds_id_present.add(op_ds_id)
                    op_objects.append(ObservedProperty(op_name, op_ds_id))
                if len(op_objects) < 1:
                    _raise_config_error("No valid observed properties defined in sensor {0} in YAML {1}". \
                                        format(str(s), yaml_path))
                if simulator_enabled:
                    from sensors.domain import get_sensor_instance_simulator as get_sensor_instance
                else:
                    from sensors.domain import get_sensor_instance
                sensor_objects.append(get_sensor_instance(sensor_type, *op_objects))

            if len(sensor_objects) < 1:
                _raise_config_error("No valid sensors defined in YAML {0}".format(yaml_path))

            c[CFG_SENSORS] = sensor_objects

            # Transports
            transport_present = set()
            transport_objects = []
            for t in transports:
                transport_type = get_config_element(CFG_TYPE, t, CFG_TRANSPORT)
                properties = get_config_element(CFG_PROPERTIES, t, CFG_TRANSPORT)
                if len(properties) < 1:
                    _raise_config_error("No properties defined in transport with type {0} in YAML {1}". \
                                        format(transport_type, yaml_path))
                transport_object = Transport.get_instance(transport_type, **properties)
                t_identifier = transport_object.identifier()
                if t_identifier in transport_present:
                    _raise_config_error("Transport with identifier {0} is specified more than once in YAML {1}". \
                                        format(t_identifier, yaml_path))
                else:
                    transport_present.add(t_identifier)
                transport_objects.append(transport_object)

            if len(transport_objects) < 1:
                _raise_config_error("No valid transports defined in YAML {0}".format(yaml_path))

            c[CFG_TRANSPORTS] = transport_objects

            return c

        def __str__(self):
            return repr(self) + str(self.config)

    instance = None

    def __init__(self, unittest=False):
        if not Config.instance or unittest:
            Config.instance = Config.__Config()
        else:
            pass

    def __getattr__(self, item):
        return getattr(self.instance, item)


def _raise_config_error(mesg: str):
    logging.error(mesg)
    raise ConfigurationError(mesg)


def get_config_element(element_name, container, container_name, optional=False):
    element = None
    if (element_name not in container) and optional is False:
        _raise_config_error("{container_name} {container} does not contain element {element_name}".\
                            format(container_name=container_name, container=str(container),
                            element_name=element_name))
    else:
        element = container[element_name]
    return element
