import logging

import asyncio

from datetime import timedelta
from homeassistant.components.switch import ENTITY_ID_FORMAT, SwitchDevice
from custom_components.meross import (DOMAIN as MEROSS_DOMAIN, MEROSS_DEVICES_BY_ID, MEROSS_DEVICE, HA_SWITCH, MerossDevice)

""" Is it necessary??? """
SCAN_INTERVAL = timedelta(seconds=10)

l = logging.getLogger("meross_switch")
l.setLevel(logging.DEBUG)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):

    l.debug('async_setup_platform called')

    """Set up Meross Switch device."""
    if discovery_info is None:
        return

    ha_entities = []
    meross_device_ids = discovery_info.get('meross_device_ids')
    for meross_device_id in meross_device_ids:
        if meross_device_id in hass.data[MEROSS_DOMAIN][MEROSS_DEVICES_BY_ID]:
            meross_device = hass.data[MEROSS_DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
            meross_device_info = str(meross_device)
            """ Some devices also have a dedicated channel for USB """
            usb_channel = meross_device.get_usb_channel_index()
            """ Some Meross devices return 0 channels... """
            channels = max(1, len(meross_device.get_channels()))
            for channel in range(0, channels):
                suffix = ''
                if channel > 0:
                    suffix = '_'+str(channel)
                if usb_channel is not None:
                    if usb_channel == channel:
                        suffix = '_usb'
                ha_entities.append(MerossSwitch(hass, meross_device_id, meross_device_info, channel, suffix))
    await async_add_entities(ha_entities, update_before_add=False)


class MerossSwitch(MerossDevice, SwitchDevice):
    """meross Switch Device."""

    def __init__(self, hass, meross_device_id, meross_device_info, channel, suffix):
        """Init Meross switch device."""
        switch_id = "{}_{}{}".format(MEROSS_DOMAIN, meross_device_id, suffix)
        super().__init__(hass, meross_device_id, ENTITY_ID_FORMAT, switch_id)
        l.debug('Entity ' + self.entity_id + ' created')
        self.value = False
        self.channel = channel
        self.meross_device_info = meross_device_info

    async def async_set_value(self, value):
        if self.meross_device_id in self.hass.data[MEROSS_DOMAIN][MEROSS_DEVICES_BY_ID]:
            self.hass.data[MEROSS_DOMAIN][MEROSS_DEVICES_BY_ID][self.meross_device_id][HA_SWITCH][self.channel] = value

    async def async_get_value(self):
        if self.meross_device_id in self.hass.data[MEROSS_DOMAIN][MEROSS_DEVICES_BY_ID]:
            if self.channel in self.hass.data[MEROSS_DOMAIN][MEROSS_DEVICES_BY_ID][self.meross_device_id][HA_SWITCH]:
                self.value = self.hass.data[MEROSS_DOMAIN][MEROSS_DEVICES_BY_ID][self.meross_device_id][HA_SWITCH][self.channel]
        return self.value

    async def async_is_on(self):
        """Return true if switch is on."""
        return await self.async_get_value()

    async def async_turn_on(self):
        """Turn the switch on"""
        device = await self.async_device()
        if device is not None:
            device.turn_on_channel(self.channel)
            """Force to update the status until the next scan"""
            self.value = True
            await self.async_set_value(self.value)

    async def async_turn_off(self):
        """Turn the device off"""
        device = await self.async_device()
        if device is not None:
            device.turn_off_channel(self.channel)
            """Force to update the status until the next scan"""
            self.value = False
            await self.async_set_value(self.value)

    @property
    def is_on(self):
        return asyncio.run_coroutine_threadsafe(self.async_is_on(), self.hass.loop).result()

    def turn_on(self, **kwargs):
        self.hass.loop.create_task(self.async_turn_on())

    def turn_off(self, **kwargs):
        self.hass.loop.create_task(self.async_turn_off())
