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

""" Setting log """
_LOGGER = logging.getLogger('meross_'+__name__.replace('_', ''))
_LOGGER.setLevel(logging.DEBUG)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):

    _LOGGER.debug('async_setup_platform called')

    if discovery_info is None:
        return

    ha_entities = []
    meross_device_ids = discovery_info.get('meross_device_ids')
    for meross_device_id in meross_device_ids:
        if meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
            meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
            meross_device_info = str(meross_device)
            if meross_device.supports_electricity_reading():
                for sensor in MEROSS_SENSORS_MAP.keys():
                    ha_entities.append(MerossSensor(hass, sensor, meross_device_id, meross_device_info))
    async_add_entities(ha_entities, update_before_add=False)


class MerossSensor(MerossDevice):
    """Representation of a Meross sensor."""

    def __init__(self, hass, sensor, meross_device_id, meross_device_info):
        """Initialize the device."""
        sensor_id = "{}_{}_{}" . format(DOMAIN, meross_device_id, MEROSS_SENSORS_MAP[sensor]['eid'], sensor)
        super().__init__(hass, meross_device_id, ENTITY_ID_FORMAT, sensor_id)
        self._sensor = sensor
        self._name = meross_device_info.split('(')[0].rstrip()
        _LOGGER.debug(self._name + ' >>> ' + self.idenfier + ' >>> __init__()')
        self._value = 0
    
    async def async_update(self):
        _LOGGER.debug(self._name + ' >>> ' + self.idenfier + ' >>> async_update()')
        """ update is done in the update function"""        
        if self.meross_device_id in self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
            f = MEROSS_SENSORS_MAP[self._sensor]['factor']
            self._value = self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][self.meross_device_id][HA_SENSOR][self._sensor]*f

    @property
    def unit_of_measurement(self):
        _LOGGER.debug(self._name + ' >>> ' + self.idenfier + ' >>> unit_of_measurement()')
        """Return the unit of measurement."""
        return MEROSS_SENSORS_MAP[self._sensor]['uom']

    @property
    def icon(self):
        _LOGGER.debug(self._name + ' >>> ' + self.idenfier + ' >>> icon()')
        """Return the icon."""
        return MEROSS_SENSORS_MAP[self._sensor]['icon']

    @property
    def state(self):
        _LOGGER.debug(self._name + ' >>> ' + self.idenfier + ' >>> state()')
        formatted_value = '{:.{d}f}'.format(self._value, d=MEROSS_SENSORS_MAP[self._sensor]['decimals'])
        return formatted_value
