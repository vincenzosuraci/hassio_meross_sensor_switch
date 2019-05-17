import inspect
from datetime import timedelta
import logging
import voluptuous as vol
import time
import datetime

from meross_iot.cloud.exceptions.CommandTimeoutException import CommandTimeoutException
from meross_iot.cloud.exceptions.StatusTimeoutException import StatusTimeoutException
from requests.exceptions import ConnectionError

from homeassistant.core import callback
from homeassistant.const import (CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery
from homeassistant.helpers.dispatcher import (async_dispatcher_connect)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval

from meross_iot.api import UnauthorizedException
from meross_iot.manager import MerossManager
from meross_iot.meross_event import MerossEventType
from meross_iot.cloud.devices.power_plugs import GenericPlug
from meross_iot.logger import set_log_level

# Setting log
_LOGGER = logging.getLogger('meross_init')
_LOGGER.setLevel(logging.DEBUG)

set_log_level(root=logging.INFO, connection=logging.INFO, network=logging.INFO)

# This is needed to ensure meross_iot library is always updated
# Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html
REQUIREMENTS = ['meross_iot==0.3.0.0b1']

# This is needed, it impact on the name to be called in configurations.yaml
# Ref: https://developers.home-assistant.io/docs/en/creating_integration_manifest.html
DOMAIN = 'meross'

MEROSS_MANAGER = 'manager'

HA_SWITCH = 'switch'
HA_SENSOR = 'sensor'

SIGNAL_DELETE_ENTITY = 'meross_delete'
SIGNAL_UPDATE_ENTITY = 'meross_update'

DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)

CONF_MEROSS_DEVICES_SCAN_INTERVAL = 'meross_devices_scan_interval'
DEFAULT_MEROSS_DEVICES_SCAN_INTERVAL = timedelta(minutes=15)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_USERNAME): cv.string,

        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.time_period,
        vol.Optional(CONF_MEROSS_DEVICES_SCAN_INTERVAL, default=DEFAULT_MEROSS_DEVICES_SCAN_INTERVAL): cv.time_period,
    })
}, extra=vol.ALLOW_EXTRA)


# ----------------------------------------------------------------------------------------------------------------------
#
# ASYNC SETUP
#
# ----------------------------------------------------------------------------------------------------------------------


async def async_setup(hass, config):

    _LOGGER.debug('async_setup() >>> STARTED')

    # create the MerossManager object
    hass.data[DOMAIN] = MerossPlatform(hass, config)

    _LOGGER.debug('async_setup() <<< TERMINATED')

    return True


# ----------------------------------------------------------------------------------------------------------------------
#
# MEROSS PLUG
#
# ----------------------------------------------------------------------------------------------------------------------


class MerossPlug:

    def __init__(self, hass, config, meross_device):

        # homeassistant
        self._hass = hass
        self._config = config

        # device
        self.device = meross_device
        self.uuid = meross_device.uuid
        self.name = meross_device.name
        self.was_available = meross_device.online

        # async register sensors & switches
        self.sensor_states = {}
        self.switch_states = {}
        self.sensor_switch_added = False
        if self.was_available:
            self.add_sensor_and_switches()
        else:
            _LOGGER.info(self.name + ' is offline >>> no sensor or switch added')

    def add_sensor_and_switches(self):
        self._hass.async_create_task(
            discovery.async_load_platform(self._hass,
                                          HA_SENSOR,
                                          DOMAIN,
                                          {'meross_device_uuid': self.uuid},
                                          self._config))
        self._hass.async_create_task(
            discovery.async_load_platform(self._hass,
                                          HA_SWITCH,
                                          DOMAIN,
                                          {'meross_device_uuid': self.uuid},
                                          self._config))
        self.sensor_switch_added = True

    @property
    def available(self):
        return self.device.online

    def set_availability(self, available):
        if self.was_available != available:
            self.was_available = available
            if available:
                _LOGGER.info(self.name + ' is online')
                if not self.sensor_switch_added:
                    self.add_sensor_and_switches()
            else:
                _LOGGER.info(self.name + ' is offline')
        for name, sensor in self.sensor_states.items():
            sensor['available'] = available
        for channel, switch in self.switch_states.items():
            switch['available'] = available

    async def async_update_status(self):
        _LOGGER.debug(self.name + ' async_update_status() >>> STARTED')
        available = self.available
        self.set_availability(available)
        if available:
            self.update_switch_status()
            self.update_sensor_status()
        _LOGGER.debug(self.name + ' async_update_status() >>> TERMINATED')
        return True

    def update_switch_status(self):

        _LOGGER.debug(self.name + 'update_switch_status() >>> STARTED')

        # for each channel (switch), update its status (on/off)
        for channel, switch_state in self.switch_states.items():

            try:
                # update the Meross Device switch status
                # WARNING: potentially blocking >>> CommandTimeoutException expected
                channel_status = self.device.get_channel_status(channel)
                switch_state['is_on'] = channel_status
                _LOGGER.debug(self.name + ' >>> channel ' +
                              str(channel) + ' >>> ' +
                              str(channel_status))

            except StatusTimeoutException:
                # Handle a StatusTimeoutException
                handle_status_timeout_exception(inspect.stack()[0][3])

            except CommandTimeoutException:
                # Handle a CommandTimeoutException
                handle_command_timeout_exception(inspect.stack()[0][3])

        _LOGGER.debug(self.name + 'update_switch_status() <<< STARTED')

    def update_sensor_status(self):
        if len(self.sensor_states) > 0:

            try:
                # for each electricity <key,value> pair, save it in hass object
                # WARNING: potentially blocking >>> CommandTimeoutException expected
                _LOGGER.debug(self.name + ' >>> get_electricity()')
                electricity = self.device.get_electricity()
                for key, value in electricity.items():
                    if key in self.sensor_states:
                        self.sensor_states[key]['value'] = value

            except CommandTimeoutException:
                handle_command_timeout_exception(inspect.stack()[0][3])


# ----------------------------------------------------------------------------------------------------------------------
#
# MEROSS PLATFORM
#
# ----------------------------------------------------------------------------------------------------------------------

class MerossPlatform:

    def __init__(self, hass, config):

        self._hass = hass
        self._config = config

        self._username = config[DOMAIN][CONF_USERNAME]
        self._password = config[DOMAIN][CONF_PASSWORD]
        self.update_status_interval = config[DOMAIN][CONF_SCAN_INTERVAL]
        self.discover_plugs_interval = config[DOMAIN][CONF_MEROSS_DEVICES_SCAN_INTERVAL]

        # start meross manager
        self._meross_manager = None
        self.start_meross_manager()

        # first discover plugs
        self.meross_plugs_by_uuid = {}
        hass.async_create_task(self.async_discover_plugs())

        # first update
        hass.async_create_task(self.async_update_plugs())

        # starting timers
        hass.async_create_task(self.async_start_timer())

    async def async_start_timer(self):

        # This is used to update the Meross Devices status periodically
        _LOGGER.info('Meross devices status will be updated each ' + str(self.update_status_interval))
        async_track_time_interval(self._hass,
                                  self.async_update_plugs,
                                  self.update_status_interval)

        # This is used to discover new Meross Devices periodically
        _LOGGER.info('Meross devices list will be updated each ' + str(self.discover_plugs_interval))
        async_track_time_interval(self._hass,
                                  self.async_discover_plugs,
                                  self.discover_plugs_interval)

        return True

    async def async_update_plugs(self, now=None):

        # monitor the duration in millis
        # registering starting timestamp in ms
        start_ms = int(round(time.time() * 1000))

        _LOGGER.debug('async_update_plugs() >>> STARTED at ' + str(now))

        for meross_device_uuid, meross_plug in self.meross_plugs_by_uuid.items():
            _LOGGER.debug(meross_plug.name + ' plug status update >>> STARTED')
            await meross_plug.async_update_status()
            _LOGGER.debug(meross_plug.name + ' plug status update <<< TERMINATED')
        _LOGGER.debug('async_update_plugs() <<< TERMINATED')

        # registering ending timestamp in ms
        end_ms = int(round(time.time() * 1000))
        duration_ms = end_ms - start_ms
        duration_s = int(round(duration_ms / 1000))
        duration_td = datetime.timedelta(seconds=duration_s)
        if duration_td > self.update_status_interval:
            _LOGGER.warning('Updating the Meross plug status took ' + str(duration_td))

        return True

    async def async_discover_plugs(self, now=None):

        _LOGGER.debug('async_discover_plugs >>> STARTED at ' + str(now))

        # get all the registered meross_plugs
        meross_plugs = self._meross_manager.get_devices_by_kind(GenericPlug)

        # check each registered meross plug
        for meross_plug in meross_plugs:

            # get meross plug uuid
            meross_plug_uuid = meross_plug.uuid

            # Check if the meross plug uuid has been already discovered
            if meross_plug_uuid not in self.meross_plugs_by_uuid:
                self.meross_plugs_by_uuid[meross_plug_uuid] = MerossPlug(self._hass,
                                                                         self._config,
                                                                         meross_plug)
        _LOGGER.debug('async_discover_plugs <<< FINISHED')

        return True

    def meross_event_handler(self, eventobj):
        _LOGGER.info(str(eventobj.event_type) + " event detected")
        if eventobj.event_type == MerossEventType.CLIENT_CONNECTION:
            # Fired when the MQTT client connects/disconnects to the MQTT broker
            # do nothing...
            pass
        elif eventobj.event_type == MerossEventType.DEVICE_ONLINE_STATUS:
            _LOGGER.info("Device online status changed: %s went %s" % (eventobj.device.name, eventobj.status))
            meross_device_uuid = eventobj.device.uuid
            meross_device_availability = eventobj.status
            if meross_device_uuid in self.meross_plugs_by_uuid:
                # the device has been already discovered >>> update its availability
                meross_plug = self.meross_plugs_by_uuid[meross_device_uuid]
                meross_plug.set_availability(meross_device_availability)
            else:
                # the device has not yet been discovered >>> add it
                self._hass.async_create_task(self.async_discover_plugs())
            pass
        elif eventobj.event_type == MerossEventType.DEVICE_SWITCH_STATUS:
            _LOGGER.info("Switch state changed: Device %s (channel %d) went %s" %
                         (eventobj.device.name, eventobj.channel_id, eventobj.switch_state))
            meross_device_uuid = eventobj.device.uuid
            channel = eventobj.channel_id
            channel_status = eventobj.switch_state
            meross_plug = self.meross_plugs_by_uuid[meross_device_uuid]
            meross_plug.switch_states[channel]['is_on'] = channel_status
        else:
            _LOGGER.warning(str(eventobj.event_type) + " is an unknown event!")
        pass

    def start_meross_manager(self):

        try:
            # Create the manager
            self._meross_manager = MerossManager(self._username, self._password)

            # Starts the manager
            self._meross_manager.start()

            # Register event handlers for the manager...
            self._meross_manager.register_event_handler(self.meross_event_handler)

        except CommandTimeoutException:
            handle_command_timeout_exception('start_meross_manager()')

        except UnauthorizedException:
            handle_unauthorized_exception('start_meross_manager()')

        except ConnectionError:
            handle_connection_error_exception('start_meross_manager()')

        pass


# ----------------------------------------------------------------------------------------------------------------------
#
# MEROSS ENTITY
#
# ----------------------------------------------------------------------------------------------------------------------

class MerossEntity(Entity):
    # Meross entity ( sensor / switch )

    def __init__(self, hass, meross_device_uuid, meross_device_name, meross_entity_id, meross_entity_name, available):

        self.hass = hass
        self.entity_id = meross_entity_id

        """Register the physical Meross device id"""
        self._meross_device_uuid = meross_device_uuid
        self._meross_entity_name = meross_entity_name
        self._meross_device_name = meross_device_name
        self._available = available

        _LOGGER.debug(self._meross_device_name + ' >>> ' + self._meross_entity_name + ' >>> __init__()')

    async def async_added_to_hass(self):
        # Called when an entity has their entity_id and hass object assigned, before it is written to the state
        # machine for the first time. Example uses: restore the state or subscribe to updates.
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> async_added_to_hass()')
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> entity_id: ' +
                      self.entity_id)
        async_dispatcher_connect(self.hass,
                                 SIGNAL_DELETE_ENTITY,
                                 self._delete_callback)
        async_dispatcher_connect(self.hass,
                                 SIGNAL_UPDATE_ENTITY,
                                 self._update_callback)
        return True

    async def async_will_remove_from_hass(self):
        # Called when an entity is about to be removed from Home Assistant. Example use: disconnect from the server or
        # unsubscribe from updates
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> async_will_remove_from_hass()')
        return True

    async def async_update(self):
        # update is done in the update function
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> async_update()')
        return True

    @property
    def device_id(self):
        # Return Meross device id.
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> device_id() >>> ' +
                      self._meross_device_uuid)
        return self._meross_device_uuid

    @property
    def unique_id(self):
        # Return a unique ID."
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> unique_id() >>> ' +
                      self.entity_id)
        return self.entity_id

    @property
    def name(self):
        # Return Meross device name.
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> name() >>> ' +
                      self._meross_device_name)
        return self._meross_device_name

    @property
    def available(self):
        # Return if the device is available.
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> available() >>> ' +
                      str(self._available))
        return self._available

    @callback
    def _delete_callback(self, entity_id):
        # Remove this entity.
        if entity_id == self.entity_id:
            _LOGGER.debug(self._meross_device_name + ' >>> ' +
                          self._meross_entity_name + ' >>> _delete_callback()')
            self.hass.async_create_task(self.async_remove())

    @callback
    def _update_callback(self):
        # Call update method.
        _LOGGER.debug(self._meross_device_name + ' >>> ' +
                      self._meross_entity_name + ' >>> _update_callback()')
        self.async_schedule_update_ha_state(True)


# ----------------------------------------------------------------------------------------------------------------------
#
# EXCEPTION HANDLING FUNCTIONS
#
# ----------------------------------------------------------------------------------------------------------------------


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
