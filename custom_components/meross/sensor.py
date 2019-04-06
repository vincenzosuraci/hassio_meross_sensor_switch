import logging, time, hmac, hashlib, random, base64, json, socket

from datetime import timedelta
from homeassistant.util import Throttle
from homeassistant.components.sensor import (DOMAIN, ENTITY_ID_FORMAT)

from custom_components.meross import (DOMAIN as MEROSS_DOMAIN, MEROSS_DEVICES, MerossDevice)

SCAN_INTERVAL = timedelta(seconds=10)

MEROSS_SENSORS_MAP = {
    'power'                 : { 'eid' : 'power',   'uom' : 'W',  'icon' : 'mdi:flash-outline', 'factor' : 0.001, 'decimals':2 },
    'current'               : { 'eid' : 'current', 'uom' : 'A',  'icon' : 'mdi:current-ac',    'factor' : 0.001, 'decimals':2 },
    'voltage'               : { 'eid' : 'voltage', 'uom' : 'V',  'icon' : 'mdi:power-plug',    'factor' : 0.1,   'decimals':2 },
}

l = logging.getLogger("meross_sensor")
l.setLevel(logging.DEBUG)

def setup_platform(hass, config, add_entities, discovery_info=None):
    if discovery_info is None:
        return
    meross_devices = hass.data[MEROSS_DEVICES]
    meross_device_ids = discovery_info.get('dev_ids')
    entities = []
    for meross_device_id in meross_device_ids:
        if meross_devices[meross_device_id] is not None:
            meross_device = meross_devices[meross_device_id]
            if 'Appliance.Control.Electricity' in meross_device.get_abilities():
                for sensor in MEROSS_SENSORS_MAP.keys():
                    entity = MerossSensor(hass, sensor, meross_device.device_id())
                    entities.append(entity)
    add_entities(entities)

class MerossSensor(MerossDevice):
    """Representation of a Meross sensor."""

    def __init__(self, hass, sensor, meross_device_id):
        """Initialize the device."""
        sensor_id ="{}_{}_{}".format(MEROSS_DOMAIN, meross_device_id, MEROSS_SENSORS_MAP[sensor]['eid'])
        super().__init__(hass, meross_device_id, ENTITY_ID_FORMAT, sensor_id)
        self.sensor        = sensor

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return MEROSS_SENSORS_MAP[self.sensor]['uom']

    @property
    def state(self):
       """Return the state of the sensor."""
       value = 0
       status = self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]
       if 'sensor' is status
           d = MEROSS_SENSORS_MAP[self.sensor]['decimals']
           f = MEROSS_SENSORS_MAP[self.sensor]['factor']
           value = status['sensor'][self.sensor]*f
       formatted_value = '{:.{d}f}'.format(value,d = MEROSS_SENSORS_MAP[self.sensor]['decimals'])
       return formatted_value

    @property
    def icon(self):
        """Return the icon."""
        return MEROSS_SENSORS_MAP[self.sensor]['icon']
