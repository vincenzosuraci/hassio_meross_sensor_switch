from datetime import timedelta
import logging
import voluptuous as vol

from homeassistant.core import callback
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers.dispatcher import (dispatcher_send, async_dispatcher_connect)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval


"""Import MerossHttpClient from Meross.iot.api library"""
from meross_iot.api import MerossHttpClient
from meross_iot.supported_devices.exceptions.CommandTimeoutException import CommandTimeoutException
from meross_iot.api import UnauthorizedException

# Setting the logLevel to 40 will HIDE any message logged with severity less than 40 (40=WARNING, 30=INFO)
l = logging.getLogger("meross_init")
l.setLevel(logging.DEBUG)

""" This is needed to ensure meross_iot library is always updated """
""" Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html"""
REQUIREMENTS = ['meross_iot==0.2.0.2']

""" This is needed, it impact on the name to be called in configurations.yaml """
""" Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html"""
DOMAIN = 'meross'

MEROSS_HTTP_CLIENT = 'http_client'
MEROSS_DEVICES_BY_ID = 'meross_devices_by_id'
MEROSS_DEVICE = 'meross_device'
MEROSS_NUM_CHANNELS = 'num_channels'
MEROSS_LAST_DISCOVERED_DEVICE_IDS = 'last_discovered_device_ids'

HA_SWITCH = 'switch'
HA_SENSOR = 'sensor'
HA_ENTITY_IDS = 'ha_entity_ids'

SIGNAL_DELETE_ENTITY = 'meross_delete'
SIGNAL_UPDATE_ENTITY = 'meross_update'

SERVICE_FORCE_UPDATE = 'force_update'
SERVICE_PULL_DEVICES = 'pull_devices'

DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)

CONF_MEROSS_DEVICES_SCAN_INTERVAL = 'meross_devices_scan_interval'
DEFAULT_MEROSS_DEVICES_SCAN_INTERVAL = timedelta(minutes=5)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,

        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.time_period,
        vol.Optional(CONF_MEROSS_DEVICES_SCAN_INTERVAL, default=DEFAULT_MEROSS_DEVICES_SCAN_INTERVAL): cv.time_period,
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):

    #l.debug('async_setup')

    """Get Meross Component configuration"""
    username = config[DOMAIN][CONF_USERNAME]
    password = config[DOMAIN][CONF_PASSWORD]
    scan_interval = config[DOMAIN][CONF_SCAN_INTERVAL]
    meross_devices_scan_interval = config[DOMAIN][CONF_MEROSS_DEVICES_SCAN_INTERVAL]

    """ When creating MerossHttpClient no connection is needed """
    hass.data[DOMAIN] = {
        MEROSS_HTTP_CLIENT : MerossHttpClient(email=username, password=password),
        MEROSS_DEVICES_BY_ID: {},
    }

    """ Called at the very beginning and periodically, each 5 seconds """
    async def async_update_devices_status():
        #l.debug('async_update_devices_status()')
        for meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
            meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
            channels = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_NUM_CHANNELS]
            for channel in range(0, channels):
                try:
                    hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_SWITCH][
                        channel] = meross_device.get_channel_status(channel)
                except CommandTimeoutException:
                    l.warning('CommandTimeoutException when executing get_channel_status()')
                    pass
            try:
                if meross_device.supports_electricity_reading():
                    for key, value in meross_device.get_electricity()['electricity'].items():
                        hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_SENSOR][key] = value
            except CommandTimeoutException:
                l.warning('CommandTimeoutException when executing get_electricity()')
                pass

    """ Called at the very beginning and periodically, each 5 seconds """
    async def async_periodic_update_devices_status(event_time):
        await async_update_devices_status()

    """ This is used to update the Meross Devices status periodically """
    async_track_time_interval(hass, async_periodic_update_devices_status, scan_interval)


    """ Called at the very beginning and periodically, every 15 minutes """
    async def async_load_devices():

        l.debug('async_load_devices()')

        """ Load the updated list of Meross devices """
        meross_device_ids_by_type = {}
        hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS] = []
        if len(hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]) > 0:
            l.debug('calling list_supported_devices() >>> suspect of disconnection...')

        try:
            """ ATTENTION: Calling list_supported_devices() disconnects all the active meross devices """
            for meross_device in hass.data[DOMAIN][MEROSS_HTTP_CLIENT].list_supported_devices():
                """ Get the Meross device id """
                meross_device_id = meross_device.device_id()
                hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS].append(meross_device_id)
                """ Check if the Meross device id has been already registered """
                if meross_device_id not in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
                    meross_device_name = str(meross_device).split('(')[0].rstrip()
                    l.debug('New Meross device found: ' + meross_device_name)
                    try:
                        num_channels = max(1, len(meross_device.get_channels()))
                        hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id] = {
                            MEROSS_DEVICE: meross_device,
                            MEROSS_NUM_CHANNELS: num_channels,
                            HA_ENTITY_IDS: [],
                            HA_SWITCH: {},
                            HA_SENSOR: {},
                        }

                        """ switch discovery """
                        if HA_SWITCH not in meross_device_ids_by_type:
                            meross_device_ids_by_type[HA_SWITCH] = []
                        meross_device_ids_by_type[HA_SWITCH].append(meross_device_id)

                        """ sensor discovery """
                        if HA_SENSOR not in meross_device_ids_by_type:
                            meross_device_ids_by_type[HA_SENSOR] = []
                        meross_device_ids_by_type[HA_SENSOR].append(meross_device_id)

                    except CommandTimeoutException:
                        l.warning('CommandTimeoutException when executing get_channels()')
                        pass
                else:
                    """ Update with the new created meross_device... """
                    hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE] = meross_device

            await async_update_devices_status()

            for ha_type, meross_device_ids in meross_device_ids_by_type.items():
                await discovery.async_load_platform(hass, ha_type, DOMAIN, {'meross_device_ids': meross_device_ids},
                                                    config)
        except CommandTimeoutException:
            l.warning('CommandTimeoutException when executing list_supported_devices()')
            pass
        except UnauthorizedException:
            l.warning('UnauthorizedException when executing list_supported_devices() >>> check: a) internet connection, b) Meross account credentials')
            pass

    """Load Meross devices"""
    await async_load_devices()

    """ Called every 15 minutes """
    async def async_poll_devices_update(event_time):
        """Check if accesstoken is expired and pull device list from server."""

        """ Discover available devices """
        await async_load_devices()

        """ Delete no more existing Meross devices """
        for meross_device_id in hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS]:
            if meross_device_id not in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
                for entity_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][HA_ENTITY_IDS]:
                    dispatcher_send(hass, SIGNAL_DELETE_ENTITY, entity_id)
                hass.data[DOMAIN][MEROSS_DEVICES_BY_ID].pop(meross_device_id)

    """ This is used to update the Meross Device list periodically """
    async_track_time_interval(hass, async_poll_devices_update, meross_devices_scan_interval)

    """ Register it as a service """
    """ Ref: https://developers.home-assistant.io/docs/en/dev_101_services.html"""
    """ Decided to disable it"""
    #hass.services.register(DOMAIN, SERVICE_PULL_DEVICES, poll_devices_update)

    #def force_update(call):
    #    """Force all entities to pull data."""
    #    dispatcher_send(hass, SIGNAL_UPDATE_ENTITY)

    """ Register it as a service """
    """ Ref: https://developers.home-assistant.io/docs/en/dev_101_services.html"""
    """ Decided to disable it"""
    #hass.services.register(DOMAIN, SERVICE_FORCE_UPDATE, force_update)

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
        self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][self.meross_device_id][HA_ENTITY_IDS].append(self.entity_id)
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

    async def async_update(self):
        """ update is done in the update function"""
        pass

    def get_device(self):
        return self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][self.meross_device_id][MEROSS_DEVICE]

    @callback
    def _delete_callback(self, meross_device_id):
        """Remove this entity."""
        l.debug('_delete_callback() called')
        if meross_device_id == self.meross_device_id:
            self.hass.async_create_task(self.async_remove())

    @callback
    def _update_callback(self):
        l.debug('_update_callback() called')
        """Call update method."""
        self.async_schedule_update_ha_state(True)
