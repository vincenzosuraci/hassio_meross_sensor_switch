from datetime import timedelta
import logging
import voluptuous as vol
import threading

from requests.exceptions import ConnectionError

from homeassistant.core import callback
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers.dispatcher import (dispatcher_send, async_dispatcher_connect)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval

"""Import MerossHttpClient from Meross.iot.api library"""
from meross_iot.api import MerossHttpClient
from meross_iot.api import UnauthorizedException
from meross_iot.supported_devices.power_plugs import GenericPlug
from meross_iot.supported_devices.client_status import ClientStatus
from meross_iot.supported_devices.exceptions.CommandTimeoutException import CommandTimeoutException
from meross_iot.supported_devices.exceptions.StatusTimeoutException import StatusTimeoutException
from meross_iot.supported_devices.exceptions.ConnectionDroppedException import ConnectionDroppedException

""" Setting log """
_LOGGER = logging.getLogger('meross_init')
_LOGGER.setLevel(logging.DEBUG)

""" This is needed to ensure meross_iot library is always updated """
""" Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html"""
REQUIREMENTS = ['meross_iot==0.2.2.3']

""" This is needed, it impact on the name to be called in configurations.yaml """
""" Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html"""
DOMAIN = 'meross'

MEROSS_HTTP_CLIENT = 'http_client'
MEROSS_DEVICES_BY_ID = 'meross_devices_by_id'
MEROSS_DEVICE = 'meross_device'
MEROSS_DEVICE_NAME = 'device_name'
MEROSS_NUM_CHANNELS = 'num_channels'
MEROSS_LOAD_DEVICES_THREAD = 'load_devices_thread'
MEROSS_UPDATE_DEVICES_STATUS_THREAD = 'update_devices_status_thread'
MEROSS_LAST_DISCOVERED_DEVICE_IDS = 'last_discovered_device_ids'
MEROSS_MAIN_LOOP_THREAD = 'main_loop_thread'
UPDATE_MEROSS_DEVICES_LIST_FLAG = 'update_devices_list'
UPDATE_MEROSS_DEVICES_STATUS_FLAG = 'update_devices_status'

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


class HomeAssistantMerossGenericPlug(GenericPlug):
    def __init__(self,
                 token,
                 key,
                 user_id,
                 **device_info):
        super().__init__(token, key, user_id, **device_info)

    def get_client_status(self):
        return self._connection_manager.get_status()

    def is_active(self):
        status = self._connection_manager.get_status()
        return status == ClientStatus.CONNECTED or status == ClientStatus.SUBSCRIBED

    def _on_disconnect(self, client, userdata, rc):
        _LOGGER.warning(str(self) + ' >>> _on_disconnect()')
        super()._on_disconnect(client, userdata, rc)

    def __del__(self):
        _LOGGER.debug(str(self) + ' >>> _del_()')
        # super().__del__(self)


class HomeAssistantMerossHttpClient(MerossHttpClient):
    def __init__(self, email, password):
        super().__init__(email, password)

    def supported_devices_info_by_id(self, online_only=True):
        supported_devices_info_by_id = {}
        for device_info in self.list_devices():
            device_id = device_info['uuid']
            online = device_info['onlineStatus']

            if online_only and online != 1:
                # The device is not online, so we skip it.
                continue
            else:
                supported_devices_info_by_id[device_id] = device_info
        return supported_devices_info_by_id

    def get_device(self, device_info, online_only=True):
        online = device_info['onlineStatus']
        if online_only and online != 1:
            return None
        return HomeAssistantMerossGenericPlug(self._token, self._key, self._userid, **device_info)

    def __del__(self):
        _LOGGER.debug('HomeAssistantMerossHttpClient >>> _del_()')
        # super().__del__(self)


def thread_main_loop(hass, config):
    _LOGGER.debug('thread_main_loop()')
    while True:
        if hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_LIST_FLAG]:
            hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_LIST_FLAG] = False
            thread_update_devices_list(hass, config)
        if hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_STATUS_FLAG]:
            hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_STATUS_FLAG] = False
            thread_update_devices_status(hass, config)


def update_device_status_by_id(hass, meross_device_id):
    # get the Meross Device object
    meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
    # get the Meross Device name
    meross_device_name = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_NAME]
    # debug
    _LOGGER.debug(meross_device_name + ' >>> async_update_device_status_by_id()')
    # get the num of channels (switches) associated to this device
    num_channels = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_NUM_CHANNELS]
    # for each channel (switch), update its status (on/off)
    for channel in range(0, num_channels):
        try:
            # update the Meross Device switch status
            # WARNING: potentially blocking >>> CommandTimeoutException expected
            _LOGGER.debug(meross_device_name + ' >>> get_channel_status()')
            channel_status = meross_device.get_channel_status(channel)
            hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_SWITCH][channel] = channel_status
            _LOGGER.debug(meross_device_name + ' >>> channel ' + str(channel) + ' >>> ' + str(channel_status))
        except StatusTimeoutException:
            # Handle a StatusTimeoutException
            # Error while waiting for status ClientStatus.SUBSCRIBED. Last status is: ClientStatus.CONNECTED
            _LOGGER.warning('StatusTimeoutException when executing update_device_status_by_id()')
            pass
        except CommandTimeoutException:
            # Handle a CommandTimeoutException
            _LOGGER.warning('CommandTimeoutException when executing update_device_status_by_id()')
            pass
    # update the electricity info, if the Meross Device supports it
    try:
        # check of the Meross Device supports electricity reading
        # WARNING: potentially blocking >>> CommandTimeoutException expected
        _LOGGER.debug(meross_device_name + ' >>> supports_electricity_reading()')
        if meross_device.supports_electricity_reading():
            try:
                # for each electricity <key,value> pair, save it in hass object
                # WARNING: potentially blocking >>> CommandTimeoutException expected
                _LOGGER.debug(meross_device_name + ' >>> get_electricity()')
                electricity = meross_device.get_electricity()
                if 'electricity' in electricity:
                    for key, value in electricity['electricity'].items():
                        hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_SENSOR][key] = value
                else:
                    _LOGGER.warning(meross_device_name + ' >>> electricity not found in dict')
            except CommandTimeoutException:
                _LOGGER.warning('CommandTimeoutException when executing get_electricity()')
                pass
    except CommandTimeoutException:
        # Handle a CommandTimeoutException
        _LOGGER.warning('CommandTimeoutException when executing supports_electricity_reading()')
        pass
    pass


def thread_update_devices_status(hass, config):
    # debug
    _LOGGER.debug('thread_update_devices_status()')

    # count the inactive devices
    num_inactive_devices = 0
    for meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
        # get the Meross Device object
        meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
        # get the Meross Device name
        meross_device_name = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_NAME]
        # debug
        _LOGGER.debug('Device ' + meross_device_name + ': ' + str(meross_device.get_client_status()))
        # check if the Meross Device object is active (i.e. still subscribed to the Meross Mqtt server)
        if meross_device.is_active():
            # update device status
            update_device_status_by_id(hass, meross_device_id)
        else:
            num_inactive_devices += 1

    if num_inactive_devices > 0:
        # Some previously discovered devices are no more active: it means that the Meross Device object has been
        # disconnected. Let's check again their availability and try to rebuild
        hass.async_create_task(async_update_device_list(hass, config))
    pass


def remove_entities(hass):
    """ Delete no more existing Meross devices and related entities """
    for meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
        if meross_device_id not in hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS]:
            meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
            meross_device_name = str(meross_device)
            _LOGGER.debug('Meross device ' + meross_device_name + ' is no more online and will be deleted')
            for entity_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_ENTITY_IDS]:
                dispatcher_send(hass, SIGNAL_DELETE_ENTITY, entity_id)


def thread_update_devices_list(hass, config):

    _LOGGER.debug('thread_update_devices_list()')

    """ Load the updated list of Meross devices """
    meross_device_ids_by_type = {}
    hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS] = []

    try:
        # WARNING: blocking function >>> Exceptions may occur
        _LOGGER.debug('supported_devices_info_by_id() >>> BLOCKING')
        supported_devices_info_by_id = hass.data[DOMAIN][MEROSS_HTTP_CLIENT].supported_devices_info_by_id()
        _LOGGER.debug(str(len(supported_devices_info_by_id)) + ' supported devices found')
        for meross_device_id, meross_device_info in supported_devices_info_by_id.items():

            """ Add the Meross device id """
            hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS].append(meross_device_id)

            """ Check if the Meross device id has been already registered """
            if meross_device_id not in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:

                _LOGGER.debug('Meross device id ' + meross_device_id + ' not yet registered')
                _LOGGER.debug('get_device() >>> BLOCKING')
                meross_device = hass.data[DOMAIN][MEROSS_HTTP_CLIENT].get_device(meross_device_info)

                """ New device found """
                meross_device_name = str(meross_device).split('(')[0].rstrip()
                _LOGGER.debug('New Meross device created: ' + meross_device_name)

                try:
                    num_channels = max(1, len(meross_device.get_channels()))
                    hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id] = {
                        MEROSS_DEVICE: meross_device,
                        MEROSS_NUM_CHANNELS: num_channels,
                        MEROSS_DEVICE_NAME: meross_device_name,
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
                    _LOGGER.warning('CommandTimeoutException when executing get_channels()')
                    pass

                update_device_status_by_id(hass, meross_device_id)

            else:
                meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
                meross_device_name = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_NAME]

                update_device_status_by_id(hass, meross_device_id)

                if not meross_device.is_active():
                    _LOGGER.debug('Meross device ' + meross_device_name + ' status is ' + str(
                        meross_device.get_client_status()))
                    _LOGGER.debug('Meross device ' + meross_device_name + ' will be created')
                    meross_device = hass.data[DOMAIN][MEROSS_HTTP_CLIENT].get_device(meross_device_info)
                    hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE] = meross_device

        for ha_type, meross_device_ids in meross_device_ids_by_type.items():
            hass.async_create_task(discovery.async_load_platform(hass, ha_type, DOMAIN,
                                                                 {'meross_device_ids': meross_device_ids}, config))
    except CommandTimeoutException:
        _LOGGER.warning('CommandTimeoutException when executing supported_devices_info_by_id()')
        pass
    except UnauthorizedException:
        _LOGGER.warning('UnauthorizedException when executing supported_devices_info_by_id() >>> check: a) internet '
                        'connection, b) Meross account credentials')
        pass
    except ConnectionError:
        _LOGGER.warning('ConnectionError when executing supported_devices_info_by_id() >>> check internet connection')
        pass

    remove_entities(hass)

    pass


async def async_update_device_list(hass, config):
    _LOGGER.debug('async_update_device_list()')
    hass.data[DOMAIN][MEROSS_LOAD_DEVICES_THREAD] = threading.Thread(target=thread_update_devices_list, args=[hass, config])
    hass.data[DOMAIN][MEROSS_LOAD_DEVICES_THREAD].start()


async def async_update_devices_status(hass, config):
    _LOGGER.debug('async_update_devices_status()')
    hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_THREAD] = threading.Thread(target=thread_update_devices_status, args=[hass, config])
    hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_THREAD].start()


async def async_setup(hass, config):

    _LOGGER.debug('async_setup() >>> STARTED')

    """Get Meross Component configuration"""
    username = config[DOMAIN][CONF_USERNAME]
    password = config[DOMAIN][CONF_PASSWORD]
    scan_interval = config[DOMAIN][CONF_SCAN_INTERVAL]
    meross_devices_scan_interval = config[DOMAIN][CONF_MEROSS_DEVICES_SCAN_INTERVAL]

    """ When creating HomeAssistantMerossHttpClient no connection is needed """
    hass.data[DOMAIN] = {
        MEROSS_HTTP_CLIENT: HomeAssistantMerossHttpClient(email=username, password=password),
        MEROSS_DEVICES_BY_ID: {},
        UPDATE_MEROSS_DEVICES_LIST_FLAG: False,
        UPDATE_MEROSS_DEVICES_STATUS_FLAG: False,
    }

    """ Called at the very beginning and periodically, each meross_devices_scan_interval seconds """
    async def async_periodic_update_device_list(event_time):
        if hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_LIST_FLAG]:
            _LOGGER.warning('UPDATE_MEROSS_DEVICES_LIST_FLAG is true, probably the Meross main loop is stucked')
        else:
            hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_LIST_FLAG] = True
        pass

    """ Called at the very beginning and periodically, each scan_interval seconds """
    async def async_periodic_update_devices_status(event_time):
        if hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_STATUS_FLAG]:
            _LOGGER.warning('UPDATE_MEROSS_DEVICES_STATUS_FLAG is true, probably the Meross main loop is stucked')
        else:
            hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_STATUS_FLAG] = True

    """ This is used to update the Meross Device list periodically """
    _LOGGER.debug('registering async_periodic_update_device_list() each ' + str(meross_devices_scan_interval))
    async_track_time_interval(hass, async_periodic_update_device_list, meross_devices_scan_interval)

    """ This is used to update the Meross Devices status periodically """
    _LOGGER.debug('registering async_periodic_update_devices_status() each ' + str(scan_interval))
    async_track_time_interval(hass, async_periodic_update_devices_status, scan_interval)

    """ Schedule to load the Meross device list, for the first rime"""
    hass.data[DOMAIN][UPDATE_MEROSS_DEVICES_LIST_FLAG] = True
    hass.data[DOMAIN][MEROSS_MAIN_LOOP_THREAD] = threading.Thread(target=thread_main_loop, args=[hass, config])
    hass.data[DOMAIN][MEROSS_MAIN_LOOP_THREAD].start()

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

    _LOGGER.debug('async_setup() >>> TERMINATED')

    return True


class MerossEntity(Entity):
    """ Meross device """

    def __init__(self, hass, meross_device_id, meross_device_name, meross_entity_id, meross_entity_name):
        """Register the physical Meross device id"""
        self._meross_device_id = meross_device_id
        """Register the Meross entity id (switch, or sensor+type_of_sensor)"""
        self.entity_id = meross_entity_id
        self._meross_entity_name = meross_entity_name
        self.hass = hass
        self._meross_device_name = meross_device_name
        self._available = False
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> __init__()')

    async def async_added_to_hass(self):
        """ Called when an entity has their entity_id and hass object assigned, before it is written to the state
        machine for the first time. Example uses: restore the state or subscribe to updates."""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> async_added_to_hass()')
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> entity_id: ' + self.entity_id)
        self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][self._meross_device_id][HA_ENTITY_IDS].append(self.entity_id)
        async_dispatcher_connect(
            self.hass, SIGNAL_DELETE_ENTITY, self._delete_callback)
        async_dispatcher_connect(
            self.hass, SIGNAL_UPDATE_ENTITY, self._update_callback)

    async def async_will_remove_from_hass(self):
        """ Called when an entity is about to be removed from Home Assistant. Example use: disconnect from the server or
        unsubscribe from updates"""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> async_will_remove_from_hass()')
        pass

    @property
    def device_id(self):
        """Return Meross device id."""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> device_id() >>> ' + self._meross_device_id)
        return self._meross_device_id

    @property
    def unique_id(self):
        """Return a unique ID."""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> unique_id() >>> ' + self.entity_id)
        return self.entity_id

    @property
    def name(self):
        """Return Meross device name."""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> name() >>> ' + self._meross_device_name)
        return self._meross_device_name

    @property
    def available(self):
        """Return if the device is available."""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> available() >>> ' + str(self._available))
        return self._available

    async def async_update(self):
        """ update is done in the update function"""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> async_update()')
        pass

    def get_device(self):
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> get_device()')
        return self.hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][self._meross_device_id][MEROSS_DEVICE]


    @callback
    def _delete_callback(self, entity_id):
        """Remove this entity."""
        if entity_id == self.entity_id:
            _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> _delete_callback()')
            self.hass.async_create_task(self.async_remove())

    @callback
    def _update_callback(self):
        """Call update method."""
        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> _update_callback()')
        self.async_schedule_update_ha_state(True)
