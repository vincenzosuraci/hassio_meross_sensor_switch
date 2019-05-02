import logging
from datetime import timedelta
from homeassistant.components.sensor import (DOMAIN, ENTITY_ID_FORMAT)
from custom_components.meross import (DOMAIN, MerossEntity)

# Setting log
_LOGGER = logging.getLogger('meross_sensor')
_LOGGER.setLevel(logging.DEBUG)

# define the HA scan for sensor
SCAN_INTERVAL = timedelta(seconds=10)

MEROSS_SENSORS_MAP = {
    'power':    {'eid': 'power',   'uom': 'W',  'icon': 'mdi:flash-outline', 'factor': 0.001,   'decimals': 2},
    'current':  {'eid': 'current', 'uom': 'A',  'icon': 'mdi:current-ac',    'factor': 0.001,   'decimals': 2},
    'voltage':  {'eid': 'voltage', 'uom': 'V',  'icon': 'mdi:power-plug',    'factor': 0.1,     'decimals': 2},
}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):

    _LOGGER.debug('async_setup_platform >>> started')

    if discovery_info is None:
        _LOGGER.warning('async_setup_platform >>> discovery_info is None')
        pass
    else:
        ha_entities = []

        meross_device_uuid = discovery_info.get('meross_device_uuid')
        if meross_device_uuid not in hass.data[DOMAIN].meross_plugs_by_uuid:
            keys = str(hass.data[DOMAIN].meross_plugs_by_uuid.keys())
            _LOGGER.error('uuid ' + meross_device_uuid + ' is not in ' + keys)
        else:
            # get the meross plug
            meross_plug = hass.data[DOMAIN].meross_plugs_by_uuid[meross_device_uuid]
            # get the meross device
            meross_device = meross_plug.device
            # get the meross device name
            meross_device_name = meross_device.name
            # check if the device supports electricity reading
            if meross_device.supports_electricity_reading():
                for meross_sensor_name in MEROSS_SENSORS_MAP.keys():
                    sensor = MerossSensorEntity(hass,
                                                meross_device_uuid,
                                                meross_device_name,
                                                meross_sensor_name)
                    ha_entities.append(sensor)

        if len(ha_entities) > 0:
            async_add_entities(ha_entities, update_before_add=False)

    _LOGGER.debug('async_setup_platform <<< terminated')

    return True


class MerossSensorEntity(MerossEntity):

    def __init__(self, hass, meross_device_uuid, meross_device_name, meross_sensor_name):
        # attributes
        self._value = 0
        self._meross_sensor_name = meross_sensor_name

        # add entity to the meross_plug
        self._meross_plug = hass.data[DOMAIN].meross_plugs_by_uuid[meross_device_uuid]
        meross_device = self._meross_plug.device
        meross_device_online = meross_device.online
        self._meross_plug.sensor_states[meross_sensor_name] = {
            'available': meross_device_online,
            'value': self._value,
            }

        # naming
        meross_sensor_id = "{}_{}_{}".format(DOMAIN, meross_device_uuid, MEROSS_SENSORS_MAP[meross_sensor_name]['eid'])
        meross_entity_id = ENTITY_ID_FORMAT.format(meross_sensor_id)
        _LOGGER.debug(meross_device_name + ' >>> ' +
                      meross_sensor_name + ' >>> __init__()')

        # init MerossEntity
        super().__init__(hass,
                         meross_device_uuid,
                         meross_device_name,
                         meross_entity_id,
                         meross_sensor_name,
                         meross_device_online)

    async def async_update(self):
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> async_update()')
        # update is done in the update function
        self._value = self._meross_plug.sensor_states[self._meross_sensor_name]['value']
        self._available = self._meross_plug.sensor_states[self._meross_sensor_name]['available']
        return True

    @property
    def unit_of_measurement(self):
        uom = MEROSS_SENSORS_MAP[self._meross_sensor_name]['uom']
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> unit_of_measurement() >>> ' +
                      uom)
        # Return the unit of measurement.
        return uom

    @property
    def icon(self):
        icon = MEROSS_SENSORS_MAP[self._meross_sensor_name]['icon']
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> icon() >>> ' +
                      str(icon))
        # Return the icon.
        return icon

    @property
    def state(self):
        f = MEROSS_SENSORS_MAP[self._meross_sensor_name]['factor']
        formatted_value = '{:.{d}f}'.format(self._value*f, d=MEROSS_SENSORS_MAP[self._meross_sensor_name]['decimals'])
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> state() >>> ' +
                      formatted_value)
        return formatted_value
