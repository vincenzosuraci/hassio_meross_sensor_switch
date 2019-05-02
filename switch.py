import logging
from datetime import timedelta
from homeassistant.components.switch import ENTITY_ID_FORMAT, SwitchDevice
from custom_components.meross import (DOMAIN, MerossEntity)

# Setting log
_LOGGER = logging.getLogger('meross_switch')
_LOGGER.setLevel(logging.DEBUG)

# define the HA scan for switch
SCAN_INTERVAL = timedelta(seconds=10)


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
            # some devices also have a dedicated channel for USB
            usb_channel = meross_device.get_usb_channel_index()
            # Some Meross devices return 0 channels...
            channels = max(1, len(meross_device.get_channels()))
            for meross_switch_channel in range(0, channels):
                suffix = ''
                if meross_switch_channel > 0:
                    suffix = '_'+str(meross_switch_channel)
                if usb_channel is not None:
                    if usb_channel == meross_switch_channel:
                        suffix = '_usb'
                # creiamo una entità Home Assistant di tipo MerossSwitchEntity
                switch = MerossSwitchEntity(hass,
                                            meross_device_uuid,
                                            meross_device_name,
                                            meross_switch_channel,
                                            suffix)
                # aggiungiamola alle entità da aggiungere
                ha_entities.append(switch)

        if len(ha_entities) > 0:
            async_add_entities(ha_entities, update_before_add=False)

    _LOGGER.debug('async_setup_platform() <<< terminated')

    return True


class MerossSwitchEntity(MerossEntity, SwitchDevice):

    def __init__(self, hass, meross_device_uuid, meross_device_name, meross_switch_channel, suffix):

        # attributes
        self._is_on = False
        self._meross_switch_channel = meross_switch_channel
        self._meross_plug = hass.data[DOMAIN].meross_plugs_by_uuid[meross_device_uuid]

        # add entity to the meross_plug
        meross_device = self._meross_plug.device
        meross_device_online = meross_device.online
        self._meross_plug.switch_states[meross_switch_channel] = {
            'available':  meross_device_online,
            'is_on': self._is_on,
            }

        # naming
        meross_switch_name = str(meross_switch_channel)
        meross_switch_id = "{}_{}{}".format(DOMAIN, meross_device_uuid, suffix)
        meross_entity_id = ENTITY_ID_FORMAT.format(meross_switch_id)
        _LOGGER.debug(meross_device_name + ' >>> ' + meross_switch_name + ' >>> __init__()')        

        # init MerossEntity
        super().__init__(hass,
                         meross_device_uuid,
                         meross_device_name,
                         meross_entity_id,
                         meross_switch_name,
                         meross_device_online)

    async def async_execute_switch_and_set_status(self):
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name +
                      ' >>> async_execute_switch_and_set_status()')
        meross_plug = self.hass.data[DOMAIN].meross_plugs_by_uuid[self._meross_device_uuid]
        meross_device = meross_plug.device
        if meross_device is None:
            _LOGGER.error(self._meross_device_name + ' is None')
            return False
        elif not meross_device.online:
            _LOGGER.warning(self._meross_device_name + ' is not online')
            meross_plug.switch_states[self._meross_switch_channel]['available'] = False
            return False
        else:
            if self._is_on:
                meross_device.turn_on_channel(self._meross_switch_channel)
            else:
                meross_device.turn_off_channel(self._meross_switch_channel)
            meross_plug.switch_states[self._meross_switch_channel]['is_on'] = self._is_on
        return True

    async def async_turn_on(self):
        self._is_on = True
        _LOGGER.info(self._meross_device_name + ' >>> ' +
                     self._meross_entity_name + ' >>> async_turn_on()')
        return self.hass.async_add_job(self.async_execute_switch_and_set_status)

    async def async_turn_off(self):
        self._is_on = False
        _LOGGER.info(self._meross_device_name + ' >>> ' +
                     self._meross_entity_name + ' >>> async_turn_off()')
        return self.hass.async_add_job(self.async_execute_switch_and_set_status)

    async def async_update(self):
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> async_update()')
        updated_is_on = self._meross_plug.switch_states[self._meross_switch_channel]['is_on']
        if updated_is_on != self._is_on:
            _LOGGER.info(self._meross_device_name + ' >>> ' +
                         self._meross_entity_name + ' >>> switching from ' +
                         str(self._is_on) + ' to ' +
                         str(updated_is_on))
        self._is_on = updated_is_on
        self._available = self._meross_plug.switch_states[self._meross_switch_channel]['available']
        return True

    @property
    def name(self):
        """Name of the device."""
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> name() >>> ' +
                      self._meross_device_name)
        return self._meross_device_name

    @property
    def is_on(self):
        _LOGGER.debug(self._meross_device_name+' >>> ' +
                      self._meross_device_name + ' >>> is_on() >>> ' +
                      str(self._is_on))
        return self._is_on

