from datetime import datetime, timedelta
import logging
import voluptuous as vol

from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD, CONF_PLATFORM, CONF_SCAN_INTERVAL)
from homeassistant.helpers import discovery
from homeassistant.helpers.dispatcher import (dispatcher_send, async_dispatcher_connect)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import track_time_interval

# Setting the logLevel to 40 will HIDE any message logged with severity less than 40 (40=WARNING, 30=INFO)
l = logging.getLogger("meross_init")
l.setLevel(logging.DEBUG)

REQUIREMENTS = ['meross_iot==0.2.0.0']

DOMAIN = 'meross'
MEROSS_HTTP_CLIENT = 'meross_http_client'
MEROSS_DEVICES = 'meross_devices'

SIGNAL_DELETE_ENTITY = 'meross_delete'
SIGNAL_UPDATE_ENTITY = 'meross_update'

SERVICE_FORCE_UPDATE = 'force_update'
SERVICE_PULL_DEVICES = 'pull_devices'

SCAN_INTERVAL = timedelta(seconds=30)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,

        vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL): cv.time_period,
    })
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):

    """Set up Meross Component."""
    from meross_iot.api import MerossHttpClient

    username = config[DOMAIN][CONF_USERNAME]
    password = config[DOMAIN][CONF_PASSWORD]
    scan_interval = config[DOMAIN][CONF_SCAN_INTERVAL]

    meross = MerossHttpClient(email=username, password=password)
    hass.data[MEROSS_HTTP_CLIENT] = meross
    hass.data[DOMAIN] = {
        'entity_id_by_device_id': {},
        'last_scan_by_device_id': {},
        'scan_interval': scan_interval,
        'scanning': False
    }

    def load_devices():
        hass.data[MEROSS_DEVICES] = {}
        for device in meross.list_supported_devices():
            hass.data[MEROSS_DEVICES][device.device_id()] = device

        """Load new devices by device_type_list"""
        device_type_list = {}
        for device in hass.data[MEROSS_DEVICES].values():
            if device.device_id() not in hass.data[DOMAIN]['entity_id_by_device_id']:
                """ switch discovery """
                ha_type = 'switch'
                if ha_type not in device_type_list:
                    device_type_list[ha_type] = []
                device_type_list[ha_type].append(device.device_id())
                """ sensor discovery """
                ha_type = 'sensor'
                if ha_type not in device_type_list:
                    device_type_list[ha_type] = []
                device_type_list[ha_type].append(device.device_id())
                hass.data[DOMAIN]['entity_id_by_device_id'][device.device_id()] = []
                hass.data[DOMAIN]['last_scan_by_device_id'][device.device_id()] = None
        for ha_type, dev_ids in device_type_list.items():
            discovery.load_platform(hass, ha_type, DOMAIN, {'dev_ids': dev_ids}, config)

    """Load Meross devices"""
    load_devices()

    def poll_devices_update(event_time):
        """Check if accesstoken is expired and pull device list from server."""
        """ Discover available devices """
        load_devices()
        """ Delete no more existing devices """
        for dev_id in list(hass.data[DOMAIN]['entity_id_by_device_id']):
            if dev_id not in hass.data[MEROSS_DEVICES].keys():
                dispatcher_send(hass, SIGNAL_DELETE_ENTITY, dev_id)
                hass.data[DOMAIN]['entity_id_by_device_id'].pop(dev_id)
                hass.data[DOMAIN]['last_scan_by_device_id'].pop(dev_id)

    track_time_interval(hass, poll_devices_update, timedelta(minutes=15))

    hass.services.register(DOMAIN, SERVICE_PULL_DEVICES, poll_devices_update)

    def force_update(call):
        """Force all devices to pull data."""
        dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)

    hass.services.register(DOMAIN, SERVICE_FORCE_UPDATE, force_update)

    return True

class MerossDevice(Entity):
    """ Meross device """

    def __init__(self, hass, meross_device_id, ENTITY_ID_FORMAT, meross_entity_id):
        """Register the physical Meross device id"""
        self.meross_device_id = meross_device_id
        """Register the Meross entity id (switch, or sensor+type_of_sensor)"""
        self.entity_id = ENTITY_ID_FORMAT.format(meross_entity_id)
        self.hass = hass

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        self.hass.data[DOMAIN]['entity_id_by_device_id'][self.meross_device_id].append(self.entity_id)
        async_dispatcher_connect(
            self.hass, SIGNAL_DELETE_ENTITY, self._delete_callback)
        async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE_ENTITY, self._update_callback)

    @property
    def device_id(self):
        """Return Meross device id."""
        return self.meross_device_id

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self.entity_id

    @property
    def name(self):
        """Return Meross device name."""
        return self.meross_device_id

    @property
    def available(self):
        """Return if the device is available."""
        return True

    def update(self):
        """ Trying to update only when necessary """
        """ This function can be called concurrenty by different threads """
        """ Only one device at time can be queried, otherwise it hangs """
        scanning = self.hass.data[DOMAIN].get('scanning')
        if scanning is False:
            self.hass.data[DOMAIN]['scanning'] = True
            now = datetime.now()
            scan_interval = self.hass.data[DOMAIN].get('scan_interval')
            for meross_device_id in self.hass.data[DOMAIN]['last_scan_by_device_id'].keys():
                update_device = False
                if self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id] is None:
                    #l.debug('Entity ' + self.entity_id + ', self.hass.data[DOMAIN][\'last_scan_by_device_id\'][meross_device_id] is None >>> update needed!')
                    update_device = True
                else:
                    last_scan = self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id]['last_scan']
                    next_scan = last_scan + scan_interval
                    #l.debug('Entity ' + self.entity_id + ', last scan: ' + str(last_scan) + ', next scan: ' + str(next_scan) + ', now: ' + str(now))
                    if now >= next_scan:
                        #l.debug('Entity ' + self.entity_id + ', now >= next_scan >>> update needed!')
                        update_device = True
                if update_device is True:
                    meross_device = self.hass.data[MEROSS_DEVICES][meross_device_id]
                    #l.debug('Entity ' + self.entity_id + ' >>> updating device id '+meross_device_id)
                    channels = max(1, len(meross_device.get_channels()))
                    if self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id] is None:
                        self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id] = {}                    
                    self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id]['last_scan'] = now
                    if 'switch' not in self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id]:
                        self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id]['switch'] = {}
                    for channel in range(0, channels):
                        status = meross_device.get_channel_status(channel)
                        self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id]['switch'][channel] = status
                        #l.debug('Switch '+self.entity_id+' status updated ('+str(status)+')')
                    if meross_device.supports_electricity_reading():
                        self.hass.data[DOMAIN]['last_scan_by_device_id'][meross_device_id]['sensor'] = meross_device.get_electricity()['electricity']
            self.hass.data[DOMAIN]['scanning'] = False
        None

    def device(self):
        return self.hass.data[MEROSS_DEVICES][self.meross_device_id]

    @callback
    def _delete_callback(self, meross_device_id):
        """Remove this entity."""
        if meross_device_id == self.meross_device_id:
            self.hass.async_create_task(self.async_remove())

    @callback
    def _update_callback(self):
        """Call update method."""
        self.async_schedule_update_ha_state(True)
