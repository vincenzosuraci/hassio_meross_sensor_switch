import logging

from datetime import timedelta
from homeassistant.components.switch import ENTITY_ID_FORMAT, SwitchDevice
from custom_components.meross import (DOMAIN as MEROSS_DOMAIN, MEROSS_DEVICES, MerossDevice)

SCAN_INTERVAL = timedelta(seconds=10)

l = logging.getLogger("meross_switch")
l.setLevel(logging.DEBUG)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up Meross Switch device."""
    if discovery_info is None:
        return
    meross_devices = hass.data[MEROSS_DEVICES]
    meross_device_ids = discovery_info.get('dev_ids')
    entities = []
    for meross_device_id in meross_device_ids:
        if meross_devices[meross_device_id] is not None:
            meross_device = meross_devices[meross_device_id]
            """ Some Meross devices return 0 channels... """
            channels = max(1, len(meross_device.get_channels()))
            for channel in range(0, channels):
                suffix = ''
                if channel > 0:
                    suffix = '_'+str(channel)
                entities.append(MerossSwitch(hass, meross_device_id, channel, suffix))
            """ Some devices also have a dedicated channel for USB """
            channel = meross_device.get_usb_channel_index()
            if channel is not None:
                suffix = '_usb'
                entities.append(MerossSwitch(hass, meross_device_id, channel, suffix))
    add_entities(entities)

class MerossSwitch(MerossDevice, SwitchDevice):
    """meross Switch Device."""

    def __init__(self, hass, meross_device_id, channel, suffix):
        """Init Meross switch device."""
        switch_id = "{}_{}{}".format(MEROSS_DOMAIN, meross_device_id, suffix)
        super().__init__(hass, meross_device_id, ENTITY_ID_FORMAT, switch_id)
        self.value = False
        self.channel = channel

    @property
    def is_on(self):
        """Return true if switch is on."""
        status = self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]
        if status is not None:
            if 'switch' in status:
                if self.channel in status['switch']:
                    self.value = status['switch'][self.channel]
        return self.value

    def turn_on(self, **kwargs):
        """Turn the switch on"""
        device = self.device()
        if device is not None:
            device.turn_on_channel(self.channel)
            """Force to update the status until the next scan"""
            self.value = True
            status = self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]
            if status is not None:
                if 'switch' in status:
                    if self.channel in status['switch']:
                        self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]['switch'][self.channel] = self.value

    def turn_off(self, **kwargs):
        """Turn the device off"""
        device = self.device()
        if device is not None:
            device.turn_off_channel(self.channel)
            """Force to update the status until the next scan"""
            self.value = False
            status = self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]
            if status is not None:
                if 'switch' in status:
                    if self.channel in status['switch']:
                        self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]['switch'][self.channel] = self.value
