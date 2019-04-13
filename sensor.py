import logging

import asyncio

from datetime import timedelta
from homeassistant.components.sensor import (DOMAIN, ENTITY_ID_FORMAT)

from custom_components.meross import (DOMAIN, MEROSS_DEVICE, MEROSS_DEVICES_BY_ID, HA_SENSOR, MerossDevice)

""" Is it necessary??? """
SCAN_INTERVAL = timedelta(seconds=10)

MEROSS_SENSORS_MAP = {
    'power'   : { 'eid' : 'power',   'uom' : 'W',  'icon' : 'mdi:flash-outline', 'factor' : 0.001, 'decimals':2 },
    'current' : { 'eid' : 'current', 'uom' : 'A',  'icon' : 'mdi:current-ac',    'factor' : 0.001, 'decimals':2 },
    'voltage' : { 'eid' : 'voltage', 'uom' : 'V',  'icon' : 'mdi:power-plug',    'factor' : 0.1,   'decimals':2 },
}

l = logging.getLogger("meross_sensor")
l.setLevel(logging.DEBUG)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):

    #l.debug('async_setup_platform called')

    if discovery_info is None:
        return

    ha_entities = []
    meross_device_ids = discovery_info.get('meross_device_ids')
    for meross_device_id in meross_device_ids:
        if meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
            meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
            if meross_device.supports_electricity_reading():
                for sensor in MEROSS_SENSORS_MAP.keys():
                    ha_entities.append(MerossSensor(hass, sensor, meross_device_id))
    async_add_entities(ha_entities, update_before_add=False)


class MerossSensor(MerossDevice):
    """Representation of a Meross sensor."""

    def __init__(self, hass, sensor, meross_device_id):
        """Initialize the device."""
        sensor_id = "{}_{}_{}" . format(DOMAIN, meross_device_id, MEROSS_SENSORS_MAP[sensor]['eid'])
        super().__init__(hass, meross_device_id, ENTITY_ID_FORMAT, sensor_id)
        #l.debug('Entity ' + self.entity_id + ' created')
        self.sensor = sensor
        self._value = 0
    
    async def async_update(self):
        #l.debug('async_update() called')
        """ update is done in the update function"""        
        if self.meross_device_id in self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
            f = MEROSS_SENSORS_MAP[self.sensor]['factor']
            self._value = self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][self.meross_device_id][HA_SENSOR][self.sensor]*f

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return MEROSS_SENSORS_MAP[self.sensor]['uom']

    @property
    def icon(self):
        """Return the icon."""
        return MEROSS_SENSORS_MAP[self.sensor]['icon']

    @property
    def state(self):
        formatted_value = '{:.{d}f}'.format(self._value, d=MEROSS_SENSORS_MAP[self.sensor]['decimals'])
        return formatted_value
