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
            entities.append(MerossSwitch(hass, meross_device_id))
    add_entities(entities)

class MerossSwitch(MerossDevice, SwitchDevice):
    """meross Switch Device."""

    def __init__(self, hass, meross_device_id):
        """Init Meross switch device."""
        switch_id = "{}_{}".format(MEROSS_DOMAIN, meross_device_id)
        super().__init__(hass, meross_device_id, ENTITY_ID_FORMAT, switch_id)

    @property
    def is_on(self):
        """Return true if switch is on."""
        if self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id] is not None:
            return self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]['switch']
        return False

    def turn_on(self, **kwargs):
        """Turn the switch on."""
        device = self.device()
        if device is not None:
            device.turn_on()
            if self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id] is not None:
                self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]['switch'] = True

    def turn_off(self, **kwargs):
        """Turn the device off."""
        device = self.device()
        if device is not None:
            device.turn_off()
            if self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id] is not None:
                self.hass.data[MEROSS_DOMAIN]['last_scan_by_device_id'][self.meross_device_id]['switch'] = False
