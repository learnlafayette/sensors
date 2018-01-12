from sensors.config.constants import *

# Simulated sensors
from sensors.simulator.sensor import mq131 as sim_mq131
from sensors.simulator.sensor import dht11 as sim_dht11


def get_sensor_instance_simulator(typ, *args):
    if typ == CFG_SENSOR_TYPE_MQ131:
        return sim_mq131.Mq131(typ, *args)
    elif typ == CFG_SENSOR_TYPE_DHT11:
        return sim_dht11.Dht11(typ, *args)
    else:
        raise ValueError("Unknown sensor type {0}".format(typ))


def get_sensor_instance(typ, *args):
    raise NotImplementedError
