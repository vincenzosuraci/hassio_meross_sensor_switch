from datetime import timedelta
import logging
import voluptuous as vol
import threading
import time

from meross_iot.cloud.exceptions import CommandTimeoutException, StatusTimeoutException
from requests.exceptions import ConnectionError

from homeassistant.core import callback
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL, EVENT_HOMEASSISTANT_STOP)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers.dispatcher import (dispatcher_send, async_dispatcher_connect)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval

"""Import MerossHttpClient from Meross.iot.api library"""
#from meross_iot.api import MerossHttpClient
from meross_iot.api import UnauthorizedException
from meross_iot.manager import MerossManager
from meross_iot.meross_event import MerossEventType
#from meross_iot.cloud.devices.light_bulbs import GenericBulb
from meross_iot.cloud.devices.power_plugs import GenericPlug
#from meross_iot.supported_devices.exceptions.ConnectionDroppedException import ConnectionDroppedException

""" Setting log """
_LOGGER = logging.getLogger('meross_init')
_LOGGER.setLevel(logging.DEBUG)

""" This is needed to ensure meross_iot library is always updated """
""" Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html"""
REQUIREMENTS = ['meross_iot==0.3.0.0b0']

""" This is needed, it impact on the name to be called in configurations.yaml """
""" Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html"""
DOMAIN = 'meross'

MEROSS_MANAGER = 'manager'
MEROSS_DEVICES_BY_ID = 'devices_by_id'
MEROSS_DEVICE = 'device'
MEROSS_DEVICE_NAME = 'device_name'
MEROSS_NUM_CHANNELS = 'num_channels'
MEROSS_LAST_DISCOVERED_DEVICE_IDS = 'last_discovered_device_ids'
MEROSS_MAIN_LOOP_FLAG = 'main_loop_flag'
MEROSS_MAIN_LOOP_THREAD = 'main_loop_thread'
MEROSS_UPDATE_DEVICES_LIST_FLAG = 'update_devices_list_flag'
MEROSS_UPDATE_DEVICES_STATUS_FLAG = 'update_devices_status_flag'
MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS = 'update_devices_status_dead_locks'
MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS_MAX = 10
MEROSS_DEVICE_AVAILABLE = 'device_available'

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


def thread_main_loop(hass, config):
    _LOGGER.debug('thread_main_loop() >>> STARTED')
    scan_interval_s = config[DOMAIN][CONF_SCAN_INTERVAL].total_seconds()
    while hass.data[DOMAIN][MEROSS_MAIN_LOOP_FLAG]:
        if hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_LIST_FLAG]:
            hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_LIST_FLAG] = False
            thread_update_devices_list(hass, config)
        if hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_FLAG]:
            start = time.time()
            hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_FLAG] = False
            thread_update_devices_status(hass, config)
            duration_s = time.time() - start
            if duration_s >= scan_interval_s:
                _LOGGER.warning('thread_update_devices_status() duration was ' + str(
                    duration_s) + ' seconds that is >= scan_interval = ' + str(
                    scan_interval_s) + ' seconds >>> consider to increase the scan_interval')
    _LOGGER.debug('thread_main_loop() >>> FINISHED')
    close_meross_manager(hass)


def update_device_status_by_id(hass, meross_device_id):
    # get the Meross Device object
    meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
    # get the Meross Device name
    meross_device_name = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_NAME]
    # debug
    _LOGGER.debug(meross_device_name + ' >>> async_update_device_status_by_id()')
    # update the electricity info, if the Meross Device supports it
    try:
        # get the num of channels (switches) associated to this device
        num_channels = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_NUM_CHANNELS]
        if (len(hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_SWITCH]) == 0):
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
                    handle_status_timeout_exception('get_channel_status()')
                    pass
                except CommandTimeoutException:
                    # Handle a CommandTimeoutException
                    handle_command_timeout_exception('get_channel_status()')
                    pass
        # check of the Meross Device supports electricity reading
        # WARNING: potentially blocking >>> CommandTimeoutException expected
        _LOGGER.debug(meross_device_name + ' >>> supports_electricity_reading()')
        if meross_device.supports_electricity_reading():
            try:
                # for each electricity <key,value> pair, save it in hass object
                # WARNING: potentially blocking >>> CommandTimeoutException expected
                _LOGGER.debug(meross_device_name + ' >>> get_electricity()')
                electricity = meross_device.get_electricity()
                for key, value in electricity.items():
                    hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_SENSOR][key] = value
            except CommandTimeoutException:
                handle_command_timeout_exception('get_electricity()')
                pass
    except CommandTimeoutException:
        # Handle a CommandTimeoutException
        handle_command_timeout_exception('supports_electricity_reading()')
        pass
    pass


def thread_update_devices_status(hass, config):
    # debug
    _LOGGER.debug('thread_update_devices_status()')

    for meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
        # get the Meross Device object
        meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
        # check if the Meross Device object is active (i.e. still subscribed to the Meross Mqtt server)
        if meross_device.online:
            # update device status
            update_device_status_by_id(hass, meross_device_id)
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


def update_device_availability(hass):
    """ Delete no more existing Meross devices and related entities """
    for meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
        if meross_device_id not in hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS]:
            meross_device_name = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_NAME]
            _LOGGER.debug('Meross device ' + meross_device_name + ' is no more available')
            hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_AVAILABLE] = False
        else:
            hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_AVAILABLE] = True


def handle_unauthorized_exception(caller):
    _LOGGER.warning('UnauthorizedException when executing ' + caller + ' >>> check: a) internet connection, b) Meross '
                                                                       'account credentials')
    pass


def handle_command_timeout_exception(caller):
    _LOGGER.warning('CommandTimeoutException when executing ' + caller)
    pass


def handle_connection_error_exception(caller):
    _LOGGER.warning('ConnectionError when executing ' + caller + ' >>> check internet connection')
    pass


def handle_status_timeout_exception(caller):
    _LOGGER.warning('StatusTimeout when executing ' + caller + ' >>> check internet connection')
    pass


def thread_update_devices_list(hass, config):

    _LOGGER.debug('thread_update_devices_list()')

    """ Load the updated list of Meross devices """
    meross_device_ids_by_type = {}
    hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS] = []

    try:
        # WARNING: blocking function >>> Exceptions may occur
        _LOGGER.debug('get_devices_by_kind(GenericPlug) >>> BLOCKING')
        meross_plugs = hass.data[DOMAIN][MEROSS_MANAGER].get_devices_by_kind(GenericPlug)
        _LOGGER.debug(str(len(meross_plugs)) + ' plugs found')
        for meross_plug in meross_plugs:

            """ Meross device id === uuid """
            meross_device_id = meross_plug.uuid

            """ Add the Meross device id """
            hass.data[DOMAIN][MEROSS_LAST_DISCOVERED_DEVICE_IDS].append(meross_device_id)

            """ Check if the Meross device id has been already registered """
            if meross_device_id not in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:

                """ Meross device not yet registered """

                _LOGGER.debug('Meross device id ' + meross_device_id + ' not yet registered')
                _LOGGER.debug('get_device() >>> BLOCKING')
                meross_device = hass.data[DOMAIN][MEROSS_MANAGER].get_device_by_uuid(meross_device_id)

                """ New device found """
                meross_device_name = meross_device.name
                _LOGGER.debug('New Meross device created: ' + meross_device_name)

                """ Check if the device is available """
                meross_device_available = meross_device.online
                _LOGGER.debug('Meross device availability: ' + str(meross_device_available))

                try:
                    num_channels = max(1, len(meross_device.get_channels()))
                    hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id] = {
                        MEROSS_DEVICE: meross_device,
                        MEROSS_NUM_CHANNELS: num_channels,
                        MEROSS_DEVICE_NAME: meross_device_name,
                        MEROSS_DEVICE_AVAILABLE: meross_device_available,
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
                    handle_command_timeout_exception('get_channels()')
                    pass

                update_device_status_by_id(hass, meross_device_id)

            #else:

                #""" Meross device has been already registered """
                #meross_device = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE]
                #meross_device_name = hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_NAME]

                #update_device_status_by_id(hass, meross_device_id)

                #if not meross_device.online:
                #    _LOGGER.debug('Meross device ' + meross_device_name + ' status is ' + str(
                #        meross_device.get_client_status()))
                #    _LOGGER.debug('Meross device ' + meross_device_name + ' will be created')
                #    meross_device = hass.data[DOMAIN][MEROSS_HTTP_CLIENT].get_device(meross_device_info)
                #    hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE] = meross_device

        """ Register all the new entities """
        for ha_type, meross_device_ids in meross_device_ids_by_type.items():
            hass.async_create_task(discovery.async_load_platform(hass, ha_type, DOMAIN,
                                                                 {'meross_device_ids': meross_device_ids}, config))
    except CommandTimeoutException:
        handle_command_timeout_exception('get_devices_by_kind()')
        pass
    except UnauthorizedException:
        handle_unauthorized_exception('get_devices_by_kind()')
        pass
    except ConnectionError:
        handle_connection_error_exception('get_devices_by_kind()')
        pass

    #remove_entities(hass)

    #update_device_availability(hass)

    pass


async def stop_main_loop_thread(hass):
    _LOGGER.debug('stop_main_loop_thread() >>> Exiting from main loop...')
    hass.data[DOMAIN][MEROSS_MAIN_LOOP_FLAG] = False
    pass


def close_meross_manager(hass):
    _LOGGER.debug('close_meross_manager() >>> Closing Meross manager...')
    hass.data[DOMAIN][MEROSS_MANAGER].stop()
    pass


async def async_setup(hass, config):

    _LOGGER.debug('async_setup() >>> STARTED')

    """Get Meross Component configuration"""
    username = config[DOMAIN][CONF_USERNAME]
    password = config[DOMAIN][CONF_PASSWORD]
    scan_interval = config[DOMAIN][CONF_SCAN_INTERVAL]
    meross_devices_scan_interval = config[DOMAIN][CONF_MEROSS_DEVICES_SCAN_INTERVAL]

    """ define it here to have access to hass object """
    def meross_event_handler(eventobj):
        _LOGGER.debug(str(eventobj.event_type) + " event detected")
        if eventobj.event_type == MerossEventType.CLIENT_CONNECTION:
            # Fired when the MQTT client connects/disconnects to the MQTT broker
            # do nothing...
            pass
        elif eventobj.event_type == MerossEventType.DEVICE_ONLINE_STATUS:
            _LOGGER.debug("Device online status changed: %s went %s" % (eventobj.device.name, eventobj.status))
            meross_device_id = eventobj.device.uuid
            if meross_device_id in hass.data[DOMAIN][MEROSS_DEVICES_BY_ID]:
                # the device has been already discovered >>> update its availability
                hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][MEROSS_DEVICE_AVAILABLE] = eventobj.status
            else:
                # the device has not yet been discovered >>> update the device list
                hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_LIST_FLAG] = True
            pass
        elif eventobj.event_type == MerossEventType.DEVICE_SWITCH_STATUS:
            _LOGGER.debug("Switch state changed: Device %s (channel %d) went %s"
                          % (eventobj.device.name, eventobj.channel_id, eventobj.switch_state))
            meross_device_id = eventobj.device.uuid
            channel = eventobj.channel_id
            channel_status = eventobj.switch_state
            hass.data[DOMAIN][MEROSS_DEVICES_BY_ID][meross_device_id][HA_SWITCH][channel] = channel_status
        else:
            _LOGGER.warning(str(eventobj.event_type) + " is an unknown event!")
        pass

    def meross_reset():
        _LOGGER.debug('reset() >>> Stopping Meross manager...')
        hass.data[DOMAIN][MEROSS_MANAGER].stop()
        _LOGGER.debug('reset() >>> Creating new Meross manager...')
        hass.data[DOMAIN][MEROSS_MANAGER] = MerossManager(username, password)
        _LOGGER.debug('reset() >>> Starting Meross manager...')
        hass.data[DOMAIN][MEROSS_MANAGER].start()
        _LOGGER.debug('reset() >>> Listening for meross_event_handler()...')
        hass.data[DOMAIN][MEROSS_MANAGER].register_event_handler(meross_event_handler)
        pass

    try:
        # Creating Meross manager. It connects to the Meross Mqtt broker...
        meross_manager = MerossManager(username, password)

        hass.data[DOMAIN] = {
            MEROSS_MANAGER: meross_manager,
            MEROSS_DEVICES_BY_ID: {},
            MEROSS_UPDATE_DEVICES_LIST_FLAG: False,
            MEROSS_UPDATE_DEVICES_STATUS_FLAG: False,
            MEROSS_MAIN_LOOP_FLAG: True,
            MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS: 0,
        }

        # Starts the manager
        hass.data[DOMAIN][MEROSS_MANAGER].start()

        # Register event handlers for the manager...
        hass.data[DOMAIN][MEROSS_MANAGER].register_event_handler(meross_event_handler)

        """ Called at the very beginning and periodically, each scan_interval seconds """
        async def async_periodic_update_devices_status(event_time):
            if hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_FLAG]:
                _LOGGER.warning('MEROSS_UPDATE_DEVICES_STATUS_FLAG is true, probably the Meross main loop is stucked')
                hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS] += 1
                if hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS] > MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS_MAX:
                    _LOGGER.warning('Resetting after ' + str(MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS_MAX) + ' dead locks')
                    meross_reset()
            else:
                hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_FLAG] = True
                hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_STATUS_DEAD_LOCKS] = 0

        """ Called at the very beginning and periodically, each scan_interval seconds """
        async def async_periodic_update_devices_list(event_time):
            if hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_LIST_FLAG]:
                _LOGGER.warning('MEROSS_UPDATE_DEVICES_LIST_FLAG is true, probably the Meross main loop is stucked')
            else:
                hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_LIST_FLAG] = True

        """ This is used to update the Meross Devices status periodically """
        _LOGGER.debug('registering async_periodic_update_devices_status() each ' + str(scan_interval))
        async_track_time_interval(hass, async_periodic_update_devices_status, scan_interval)

        """ This is used to update the Meross Devices list periodically """
        _LOGGER.debug('registering async_periodic_update_devices_list() each ' + str(meross_devices_scan_interval))
        async_track_time_interval(hass, async_periodic_update_devices_list, meross_devices_scan_interval)

        """ Schedule to load the Meross device list, for the first time"""
        hass.data[DOMAIN][MEROSS_UPDATE_DEVICES_LIST_FLAG] = True
        hass.data[DOMAIN][MEROSS_MAIN_LOOP_THREAD] = threading.Thread(target=thread_main_loop, args=[hass, config])
        hass.data[DOMAIN][MEROSS_MAIN_LOOP_THREAD].start()

        """ Intercept HA stop """
        # ERROR:
        event_str = EVENT_HOMEASSISTANT_STOP
        _LOGGER.debug('registering stop_main_loop_thread(hass) when detecting ' + event_str + ' event')
        hass.bus.async_listen_once(event_str, stop_main_loop_thread(hass))

    except UnauthorizedException:
        handle_unauthorized_exception('MerossManager()')
        pass

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
