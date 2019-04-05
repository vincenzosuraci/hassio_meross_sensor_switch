import logging, time, hmac, hashlib, random, base64, json, socket

from datetime import timedelta
from homeassistant.util import Throttle
from homeassistant.components.sensor import (DOMAIN, ENTITY_ID_FORMAT)

# from homeassistant.custom_components.meross import (DOMAIN as MEROSS_HTTP_CLIENT, MerossDevice)
from custom_components.meross import (DOMAIN as MEROSS_DOMAIN, MEROSS_HTTP_CLIENT, MerossDevice)

SCAN_INTERVAL = timedelta(seconds=10)

MEROSS_SENSORS_MAP = {
    'power'                 : { 'eid' : 'power',   'uom' : 'W',  'icon' : 'mdi:flash-outline', 'factor' : 0.001, 'decimals':3 },
    'current'               : { 'eid' : 'current', 'uom' : 'A',  'icon' : 'mdi:current-ac',    'factor' : 0.001, 'decimals':3 },
    'voltage'               : { 'eid' : 'voltage', 'uom' : 'V',  'icon' : 'mdi:power-plug',    'factor' : 0.1,   'decimals':1 },
}

l = logging.getLogger("meross_sensor")
l.setLevel(logging.DEBUG)

def setup_platform(hass, config, add_entities, discovery_info=None):
    #l.debug("setup_platform() called")
    entities = []
    devices = hass.data[MEROSS_HTTP_CLIENT].list_supported_devices()
    #l.debug(str(len(devices))+" Meross devices found!")
    for i, device in enumerate(devices):
        #l.debug("Meross device #"+str(i+1)+" sensors...")
        get_electricity = getattr(device, "get_electricity", None)
        if callable(get_electricity):
            for sensor in MEROSS_SENSORS_MAP.keys():
                #l.debug("Aggiunta del sensore "+sensor+' in corso...')
                entity = MerossSensor(device, sensor)
                entities.append(entity)
    #l.debug("calling add_entities()")
    add_entities(entities, update_before_add=False)

class MerossSensor(MerossDevice):
    """Representation of a Meross sensor."""

    def __init__(self, device, sensor):
        """Initialize the device."""
        #l.debug("MerossSensor::__init__ called")
        id ="{}.{}_{}_{}".format(DOMAIN, MEROSS_DOMAIN, device.device_id(), MEROSS_SENSORS_MAP[sensor]['eid'])
        #l.debug("id: "+id)
        super().__init__(id)
        self.device        = device
        self._sensor        = sensor
        self.entity_id = ENTITY_ID_FORMAT.format(id)
        #l.debug("self.entity_id: "+self.entity_id)
        #l.debug("MerossSensor::__init__ terminated")

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        #l.debug("unit_of_measurement(self) called")
        return MEROSS_SENSORS_MAP[self._sensor]['uom']

    @property
    def state(self):
       """Return the state of the sensor."""
       #l.debug("state(self) called")
       d = MEROSS_SENSORS_MAP[self._sensor]['decimals']
       f = MEROSS_SENSORS_MAP[self._sensor]['factor']
       value = self.device.get_electricity()['electricity'][self._sensor]*f
       formatted_value = '{:.{d}f}'.format(value,d = MEROSS_SENSORS_MAP[self._sensor]['decimals'])
       return formatted_value

    @property
    def icon(self):
        """Return the icon."""
        #l.debug("icon(self) called")
        return MEROSS_SENSORS_MAP[self._sensor]['icon']
