import logging

from datetime import timedelta
from homeassistant.components.sensor import (DOMAIN, ENTITY_ID_FORMAT)

from custom_components.meross import (DOMAIN, MEROSS_DEVICE, MEROSS_DEVICES_BY_ID, HA_SENSOR, MEROSS_DEVICE_AVAILABLE,
                                      MerossEntity)

""" Is it necessary??? """
SCAN_INTERVAL = timedelta(seconds=10)

MEROSS_SENSORS_MAP = {
    'power':    {'eid': 'power',   'uom': 'W',  'icon': 'mdi:flash-outline', 'factor': 0.001, 'decimals': 2},
    'current':  {'eid': 'current', 'uom': 'A',  'icon': 'mdi:current-ac',    'factor': 0.001, 'decimals': 2},
    'voltage':  {'eid': 'voltage', 'uom': 'V',  'icon': 'mdi:power-plug',    'factor': 0.1,   'decimals': 2},
}

""" Setting log """
_LOGGER = logging.getLogger('meross_sensor')
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
                for meross_sensor_name in MEROSS_SENSORS_MAP.keys():
                    ha_entities.append(MerossSensorEntity(hass, meross_device_id, meross_device_info, meross_sensor_name))
    async_add_entities(ha_entities, update_before_add=False)


class MerossSensorEntity(MerossEntity):
    """Representation of a Meross sensor."""

    def __init__(self, hass, meross_device_id, meross_device_info, meross_sensor_name):
        self._value = 0
        self._sensor_name = meross_sensor_name
        meross_device_name = meross_device_info.split('(')[0].rstrip()
        meross_sensor_id = "{}_{}_{}".format(DOMAIN, meross_device_id, MEROSS_SENSORS_MAP[meross_sensor_name]['eid'])
        meross_entity_id = ENTITY_ID_FORMAT.format(meross_sensor_id)
        _LOGGER.debug(meross_device_name + ' >>> ' + meross_sensor_name + ' >>> __init__()')
        super().__init__(hass, meross_device_id, meross_device_name, meross_entity_id, meross_sensor_name)

    async def async_update(self):
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> async_update()')
        """ update is done in the update function"""
        self._available = False
        if self._meross_device_id in self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
            meross_device_dict = self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][self._meross_device_id]
            self._available = meross_device_dict[MEROSS_DEVICE_AVAILABLE]
            f = MEROSS_SENSORS_MAP[self._sensor_name]['factor']
            self._value = meross_device_dict[HA_SENSOR][self._sensor_name]*f

    @property
    def unit_of_measurement(self):
        uom = MEROSS_SENSORS_MAP[self._sensor_name]['uom']
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> unit_of_measurement() >>> ' + uom)
        """Return the unit of measurement."""
        return uom

    @property
    def icon(self):
        icon = MEROSS_SENSORS_MAP[self._sensor_name]['icon']
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> icon() >>> ' + str(icon))
        """Return the icon."""
        return icon

    @property
    def state(self):
        formatted_value = '{:.{d}f}'.format(self._value, d=MEROSS_SENSORS_MAP[self._sensor_name]['decimals'])
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> state() >>> ' + formatted_value)
        return formatted_value
