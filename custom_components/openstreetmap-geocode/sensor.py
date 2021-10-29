import logging, json, requests
from datetime import datetime, timedelta
from requests import get
from math import radians, cos, sin, asin, sqrt

import voluptuous as vol
import homeassistant.helpers.location as location
import homeassistant.helpers.config_validation as cv

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.helpers.event import track_state_change
from homeassistant.util import Throttle
from homeassistant.util.location import distance
from homeassistant.helpers.entity import Entity
from homeassistant.const import (CONF_API_KEY, CONF_NAME, CONF_SCAN_INTERVAL)

_LOGGER = logging.getLogger(__name__)

DEPENDENCIES = ['zone', 'device_tracker']

CONF_DEVICE_ID = 'device_id'
CONF_HOME_ZONE = 'home_zone'
CONF_OPTIONS = 'options'
CONF_MAP_PROVIDER = 'map_provider'
CONF_MAP_ZOOM = 'map_zoom'
CONF_LANGUAGE = 'language'
CONF_PICTURE = 'picture'

ATTR_OPTIONS = 'options'
ATTR_STREET_NAME = 'street_name'
ATTR_STREET_NUMBER = 'street_number'
ATTR_STREET = 'street'
ATTR_CITY = 'city'
ATTR_POSTAL_TOWN = 'postal_town'
ATTR_POSTAL_CODE = 'postal_code'
ATTR_REGION = 'state_province'
ATTR_COUNTRY = 'country'
ATTR_COUNTY = 'county'
ATTR_FORMATTED_ADDRESS = 'formatted_address'
ATTR_PLACE_TYPE = 'place_type'
ATTR_PLACE_NAME = 'place_name'
ATTR_PLACE_CATEGORY = 'place_category'
ATTR_PLACE_NEIGHBOURHOOD = 'neighbourhood'
ATTR_DEVICE_ID = 'device_entity_id'
ATTR_DEVICE_ZONE = 'device_zone'
ATTR_PICTURE = 'entity_picture'
ATTR_LATITUDE_OLD = 'previous_latitude'
ATTR_LONGITUDE_OLD = 'previous_longitude'
ATTR_LATITUDE = 'current_latitude'
ATTR_LONGITUDE = 'current_longitude'
ATTR_MTIME = 'last_changed'
ATTR_DISTANCE_KM = 'distance_from_home_km'
ATTR_DISTANCE_M = 'distance_from_home_m'
ATTR_HOME_ZONE = 'home_zone'
ATTR_HOME_LATITUDE = 'home_latitude'
ATTR_HOME_LONGITUDE = 'home_longitude'
ATTR_LOCATION_CURRENT = 'current_location'
ATTR_LOCATION_PREVIOUS = 'previous_location'
ATTR_DIRECTION_OF_TRAVEL = 'direction_of_travel'
ATTR_MAP_LINK = 'map_link'

DEFAULT_NAME = 'openstreetmap_geocode'
DEFAULT_OPTION = 'zone, place'
DEFAULT_HOME_ZONE = 'zone.home'
DEFAULT_KEY = "no key"
DEFAULT_MAP_PROVIDER = 'apple'
DEFAULT_MAP_ZOOM = '18'
DEFAULT_LANGUAGE = 'default'
DEFAULT_PICTURE = ''

SCAN_INTERVAL = timedelta(seconds=60)
THROTTLE_INTERVAL = timedelta(seconds=120)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_DEVICE_ID): cv.string,
    vol.Optional(CONF_API_KEY, default=DEFAULT_KEY): cv.string,
    vol.Optional(CONF_OPTIONS, default=DEFAULT_OPTION): cv.string,
    vol.Optional(CONF_HOME_ZONE, default=DEFAULT_HOME_ZONE): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Optional(CONF_MAP_PROVIDER, default=DEFAULT_MAP_PROVIDER): cv.string,
    vol.Optional(CONF_MAP_ZOOM, default=DEFAULT_MAP_ZOOM): cv.string,
    vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): cv.string,
    vol.Optional(CONF_PICTURE, default=DEFAULT_LANGUAGE): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=SCAN_INTERVAL): cv.time_period,
})

TRACKABLE_DOMAINS = ['device_tracker']

def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the sensor platform."""
    name = config.get(CONF_NAME)
    api_key = config.get(CONF_API_KEY)
    device_id = config.get(CONF_DEVICE_ID)
    options = config.get(CONF_OPTIONS)
    home_zone = config.get(CONF_HOME_ZONE)
    map_provider = config.get(CONF_MAP_PROVIDER)
    map_zoom = config.get(CONF_MAP_ZOOM)
    language = config.get(CONF_LANGUAGE)
    picture = config.get(CONF_PICTURE)

    add_devices([OpenStreetMap_Geocode(hass, device_id, name, api_key, options, home_zone, map_provider, map_zoom, language, picture)])

class OpenStreetMap_Geocode(Entity):
    """Representation of a OpenStreetMap_Geocode Sensor."""

    def __init__(self, hass, device_id, name, api_key, options, home_zone, map_provider, map_zoom, language, picture):
        """Initialize the sensor."""
        self._hass = hass
        self._name = name
        self._api_key = api_key
        self._options = options.lower()
        self._device_id = device_id.lower()
        self._home_zone = home_zone.lower()
        self._map_provider = map_provider.lower()
        self._map_zoom = map_zoom.lower()
        self._language = language.lower()
        self._language.replace(" ", "")
        self._entity_picture = picture
        self._state = "Initializing..." #(since 99:99)"

        home_latitude = str(hass.states.get(home_zone).attributes.get('latitude'))
        home_longitude = str(hass.states.get(home_zone).attributes.get('longitude'))
        #self._entity_picture = hass.states.get(device_id).attributes.get('entity_picture') if hass.states.get(device_id) else None
        self._street_name = None
        self._street_number = None
        self._street = None
        self._city = None
        self._postal_town = None
        self._postal_code = None
        self._city = None
        self._region = None
        self._country = None
        self._county = None
        self._formatted_address = None
        self._place_type = None
        self._place_name = None
        self._place_category = None
        self._place_neighbourhood = None
        self._home_latitude = home_latitude
        self._home_longitude = home_longitude 
        self._latitude_old = home_latitude
        self._longitude_old = home_longitude
        self._latitude = home_latitude
        self._longitude = home_longitude
        self._device_zone = 'Home'
        self._mtime = str(datetime.now())
        self._distance_km = 0
        self._distance_m = 0
        self._location_current = home_latitude + ',' + home_longitude
        self._location_previous = home_latitude + ',' + home_longitude
        self._updateskipped = 0
        self._direction = 'stationary'
        self._map_link = None
        #'https://www.google.com/maps/@' + home_latitude + "," + home_longitude + ',19z'

        # Check if device_id was specified correctly
        _LOGGER.info( "(" + self._name + ") Device Entity ID is " + device_id.split('.', 1)[1] )

        if device_id.split('.', 1)[0] in TRACKABLE_DOMAINS:
            self._device_id = device_id
            track_state_change(hass, self._device_id, self.tsc_update, from_state=None, to_state=None)
            _LOGGER.info( "(" + self._name + ") Now subscribed to state change events from " + self._device_id )

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def entity_picture(self):
        """Return the picture of the device."""
        return self._entity_picture

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return{
            ATTR_STREET_NAME: self._street_name,
            ATTR_STREET_NUMBER: self._street_number,
            ATTR_STREET: self._street,
            ATTR_CITY: self._city,
            ATTR_POSTAL_TOWN: self._postal_town,
            ATTR_POSTAL_CODE: self._postal_code,
            ATTR_REGION: self._region,
            ATTR_COUNTRY: self._country,
            ATTR_COUNTY: self._county,
            ATTR_FORMATTED_ADDRESS: self._formatted_address,
            ATTR_PLACE_TYPE: self._place_type,
            ATTR_PLACE_NAME: self._place_name,
            ATTR_PLACE_CATEGORY: self._place_category,
            ATTR_PLACE_NEIGHBOURHOOD: self._place_neighbourhood,
            ATTR_LATITUDE_OLD: self._latitude_old,
            ATTR_LONGITUDE_OLD: self._longitude_old,
            ATTR_LATITUDE: self._latitude,
            ATTR_LONGITUDE: self._longitude,
            ATTR_DEVICE_ID: self._device_id,
            ATTR_DEVICE_ZONE: self._device_zone,
            ATTR_HOME_ZONE: self._home_zone,
            ATTR_PICTURE: self._entity_picture,
            ATTR_DISTANCE_KM: self._distance_km,
            ATTR_DISTANCE_M: self._distance_m,
            ATTR_MTIME: self._mtime,
            ATTR_LOCATION_CURRENT: self._location_current,
            ATTR_LOCATION_PREVIOUS: self._location_previous,
            ATTR_HOME_LATITUDE: self._home_latitude,
            ATTR_HOME_LONGITUDE: self._home_longitude,
            ATTR_DIRECTION_OF_TRAVEL: self._direction,
            ATTR_MAP_LINK: self._map_link,
            ATTR_OPTIONS: self._options
        }


    def tsc_update(self, tscarg2, tsarg3, tsarg4):
        """ Call the do_update function based on the TSC (track state change) event    """
        self.do_update("Track State Change")

    @Throttle(THROTTLE_INTERVAL)
    def update(self):
        """ Call the do_update function based on scan interval and throttle    """
        self.do_update("Scan Interval")

    def haversine(self, lon1, lat1, lon2, lat2):
        """
        Calculate the great circle distance between two points
        on the earth (specified in decimal degrees)
        """
        # convert decimal degrees to radians 
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

        # haversine formula 
        dlon = lon2 - lon1 
        dlat = lat2 - lat1 
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a)) 
        r = 6371 # Radius of earth in kilometers. Use 3956 for miles
        return c * r

    def do_update(self, reason):
        """Get the latest data and updates the states."""

        previous_state = self.state #[:-14]
        distance_traveled = 0
        device_zone = None

        _LOGGER.info( "(" + self._name + ") Calling update due to " + reason )
        _LOGGER.info( "(" + self._name + ") Check if update req'd : " + self._device_id )
        _LOGGER.debug( "(" + self._name + ") Previous State        : " + previous_state )

        if hasattr(self, '_device_id'):
            now = datetime.now()
            old_latitude = str(self._latitude)
            old_longitude = str(self._longitude)
            new_latitude = str(self._hass.states.get(self._device_id).attributes.get('latitude'))
            new_longitude = str(self._hass.states.get(self._device_id).attributes.get('longitude'))
            home_latitude = str(self._home_latitude)
            home_longitude = str(self._home_longitude)
            last_distance_m = self._distance_m
            last_updated = self._mtime
            current_location = new_latitude + "," + new_longitude
            previous_location = old_latitude + "," + old_longitude
            home_location = home_latitude + "," + home_longitude
            
            maplink_apple     = 'https://maps.apple.com/maps/?q=' + current_location + '&z=' + self._map_zoom
            maplink_google    = 'https://www.google.com/maps/search/?api=1&basemap=roadmap&layer=traffic&query=' + current_location
            if (new_latitude != 'None' and new_longitude != 'None' and
                    home_latitude != 'None' and home_longitude != 'None'):
              distance_m = distance(float(new_latitude), float(new_longitude), float(home_latitude), float(home_longitude))
              distance_km = round(distance_m / 1000, 2)
              distance_from_home = str(distance_km)+' km'

              deviation = self.haversine(float(old_latitude), float(old_longitude), float(new_latitude), float(new_longitude))
              if deviation <= 0.2: # in kilometers
                direction = "stationary"
              elif last_distance_m > distance_m:
                direction = "towards home"
              elif last_distance_m < distance_m:
                direction = "away from home"
              else:
                direction = "stationary"

              _LOGGER.debug( "(" + self._name + ") Previous Location: " + previous_location)
              _LOGGER.debug( "(" + self._name + ") Current Location : " + current_location)
              _LOGGER.debug( "(" + self._name + ") Home Location    : " + home_location)
              _LOGGER.info( "(" + self._name + ") Distance from home : (" + (self._home_zone).split(".")[1] + "): " + distance_from_home )
              _LOGGER.info( "(" + self._name + ") Travel Direction   :(" + direction + ")" )
           
              """Update if location has changed."""

              device_zone = self.hass.states.get(self._device_id).state
              distance_traveled = distance(float(new_latitude), float(new_longitude), float(old_latitude), float(old_longitude))

              _LOGGER.info( "(" + self._name + ") Device Zone (before update): " + device_zone )
              _LOGGER.info( "(" + self._name + ") Meters traveled since last update: " + str(round(distance_traveled)) )

        proceed_with_update = True

        if current_location == previous_location:
            _LOGGER.debug( "(" + self._name + ") Skipping update because co-ordinates are identical" )
            proceed_with_update = False

        elif int(distance_traveled) > 0 and self._updateskipped > 3:
            proceed_with_update = True
            _LOGGER.debug( "(" + self._name + ") Allowing update after 3 skips even with distance traveled < 10m" )

        elif int(distance_traveled) < 10:
            self._updateskipped = self._updateskipped + 1
            _LOGGER.debug( "(" + self._name + ") Skipping update because location changed " + str(distance_traveled) + " < 10m  (" + str(self._updateskipped) + ")" )
            proceed_with_update = False

        if previous_state == 'Initializing...':
            _LOGGER.debug( "(" + self._name + ") Peforming Initial Update for user at home..." )
            proceed_with_update = True

        if proceed_with_update and device_zone:
            _LOGGER.debug( "(" + self._name + ") Proceeding with update for " + self._device_id )
            self._device_zone = device_zone
            _LOGGER.info( "(" + self._name + ") Device Zone (current) " + self._device_zone + " Skipped Updates: " + str(self._updateskipped))

            self._reset_attributes()
            
            self._latitude = new_latitude
            self._longitude = new_longitude
            self._latitude_old = old_latitude
            self._longitude_old = old_longitude
            self._location_current = current_location
            self._location_previous = previous_location
            self._device_zone = device_zone
            self._distance_km = distance_from_home
            self._distance_m = distance_m
            self._direction = direction

            if self._map_provider == 'google':
                _LOGGER.debug( "(" + self._name + ") Google Map Link requested for: [" + self._map_provider + "]")
                self._map_link = maplink_google
            else:
                _LOGGER.debug( "(" + self._name + ") Apple Map Link requested for: [" + self._map_provider + "]")
                self._map_link = maplink_apple
                
            _LOGGER.debug( "(" + self._name + ") Map Link generated: " + self._map_link )

            url = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=" + self._latitude + "&lon=" + self._longitude + ("&accept-language=" + self._language if self._language != DEFAULT_LANGUAGE else "") + "&addressdetails=1&namedetails=1&zoom=18&limit=1" + ("&email=" + self._api_key if self._api_key != DEFAULT_KEY else "")

            decoded = {}
            _LOGGER.info( "(" + self._name + ") OpenStreetMap request sent with lat=" + self._latitude + " and lon=" + self._longitude)
            _LOGGER.debug( "(" + self._name + ") url - " + url)
            response = get(url)
            json_input = response.text
            _LOGGER.debug( "(" + self._name + ") response - " + json_input)
            decoded = json.loads(json_input)

            place_options = self._options.lower()
            place_type = '-'
            place_name = '-'
            place_category = '-'
            place_neighbourhood = '-'
            street_name = ''
            street_number = ''
            street = 'Unnamed Road'
            city = '-'
            postal_town = '-'
            region = '-'
            county = '-'
            country = '-'
            postal_code = ''
            formatted_address = ''
            target_option = ''
            
            if "place" in self._options:
                place_type = decoded["type"]
                if place_type == "yes":
                    place_type = decoded["addresstype"]
                if place_type in decoded["address"]:
                    place_name = decoded["address"][place_type]
                if "category" in decoded:
                    place_category = decoded["category"]
                    if place_category in decoded["address"]:
                        place_name = decoded["address"][place_category]
                if "name" in decoded["namedetails"]:
                    place_name = decoded["namedetails"]["name"]
                for language in self._language.split(','):
                    if "name:" + language in decoded["namedetails"]:
                        place_name = decoded["namedetails"]["name:" + language]
                        break
                if "neighbourhood" in decoded["address"]:
                    place_neighbourhood = decoded["address"]["neighbourhood"]
                if self._device_zone == 'not_home' and place_name != 'house':
                    new_state = place_name
                    
            if "road" in decoded["address"]:
                street_name = decoded["address"]["road"]
            if "house_number" in decoded["address"]:
                street_number = decoded["address"]["house_number"]
            if "road" in decoded["address"] and "house_number" in decoded["address"]:
                street = decoded["address"]["road"] + " " + decoded["address"]["house_number"]
            else:
                street = decoded["address"]["road"]
            if "city" in decoded["address"]:
                city = decoded["address"]["city"]
            if "town" in decoded["address"]:
                city = decoded["address"]["town"]
            if "village" in decoded["address"]:
                city = decoded["address"]["village"]
            if "city_district" in decoded["address"]:
                postal_town = decoded["address"]["city_district"]
            if "suburb" in decoded["address"]:
                postal_town = decoded["address"]["suburb"]
            if "state" in decoded["address"]:
                region = decoded["address"]["state"]
            if "county" in decoded["address"]:
                county = decoded["address"]["county"]
            if "country" in decoded["address"]:
                country = decoded["address"]["country"]
            if "postcode" in decoded["address"]:
                postal_code = decoded["address"]["postcode"]
            if "display_name" in decoded:
                formatted_address = decoded["display_name"]
            if "sv" in self._language:
                formatted_address = street + ", " + postal_code + " " + postal_town

            self._place_type = place_type
            self._place_category = place_category
            self._place_neighbourhood = place_neighbourhood
            self._place_name = place_name
            self._street_name = street_name
            self._street_number = street_number
            self._street = street
            self._city = city
            self._postal_town = postal_town
            self._region = region
            self._county = county
            self._country = country
            self._postal_code = postal_code
            self._formatted_address = formatted_address
            self._mtime = str(datetime.now())
            
            if 'error_message' in decoded:
                new_state = decoded['error_message']
                _LOGGER.info( "(" + self._name + ") An error occurred contacting the web service")
            elif self._device_zone == "not_home" or self._device_zone == "Stationary" or "do_not_show_home" in self._options:
                if city == '-':
                    city = postal_town
                    if city == '-':
                        city = county

                # Options:  "zone, place, street_number, street, city, county, state, postal_code, country, formatted_address"

                _LOGGER.debug( "(" + self._name + ") Building State from Display Options: " + self._options)

                display_options = []
                options_array = self._options.split(',')
                for option in options_array:
                    display_options.append(option.strip())
                    
                user_display = []

                if "zone" in display_options and ("do_not_show_not_home" not in display_options and self._device_zone != "not_home"):
                    zone = self._device_zone
                    user_display.append(zone)
                if "place_name" in display_options:
                    if place_name != "-":
                        user_display.append(place_name)
                if "place" in display_options:
                    if place_name != "-":
                        user_display.append(place_name)
                    if place_category.lower() != "place":
                        user_display.append(place_category)
                    if place_type.lower() != "yes":
                        user_display.append(place_type)
                    user_display.append(place_neighbourhood)
                    user_display.append(street_number)
                    user_display.append(street)
                else:
                    if "street_name" in display_options:
                        user_display.append(street_name)
                    if "street_number" in display_options:
                        user_display.append(street_number)
                    if "street" in display_options:
                        user_display.append(street)
                if "city" in display_options:
                    user_display.append(city)
                if "county" in display_options:
                    user_display.append(county)
                if "state" in display_options:
                    user_display.append(region)
                elif "region" in display_options:
                    user_display.append(region)
                if "postal_code" in display_options:
                    user_display.append(postal_code)
                if "country" in display_options:
                    user_display.append(country)
                if "formatted_address" in display_options:
                    user_display.append(formatted_address)
                if "do_not_reorder" in display_options:
                    user_display = []
                    display_options.remove("do_not_reorder")
                    for option in display_options:
                        if option == "state":
                            target_option = "region"
                        if option == "place_neighborhood":
                            target_option = "place_neighbourhood"
                        if option in locals():
                            user_display.append(target_option)

                if not user_display:
                    user_display = self._device_zone
                    user_display.append(street)
                    user_display.append(city)

                new_state = ', '.join( item for item in user_display )
                _LOGGER.debug( "(" + self._name + ") New State built from Display Options will be: " + new_state )
            else:
                new_state = device_zone
                _LOGGER.debug( "(" + self._name + ") New State from Device set to: " + new_state)

            current_time = "%02d:%02d" % (now.hour, now.minute)
            
            if previous_state != new_state:
                _LOGGER.info( "(" + self._name + ") New state built using options: " + self._options)
                _LOGGER.debug( "(" + self._name + ") Building EventData for (" + new_state +")")
                self._state = new_state #+ " (since " + current_time + ")"
                event_data = {}
                event_data['entity'] = self._name
                event_data['place_name'] = place_name
                event_data['from_state'] = previous_state
                event_data['to_state'] = new_state
                event_data['distance_from_home'] = distance_from_home
                event_data['direction'] = direction
                event_data['device_zone'] = device_zone
                event_data['latitude'] = self._latitude
                event_data['longitude'] = self._longitude
                event_data['previous_latitude'] = self._latitude_old
                event_data['previous_longitude'] = self._longitude_old
                event_data['map'] = self._map_link
                event_data['mtime'] = current_time
                #_LOGGER.debug( "(" + self._name + ") Event Data: " + event_data )
                #self._hass.bus.fire(DEFAULT_NAME+'_state_update', { 'entity': self._name, 'place_name': place_name, 'from_state': previous_state, 'to_state': new_state, 'distance_from_home': distance_from_home, 'direction': direction, 'device_zone': device_zone, 'mtime': current_time, 'latitude': self._latitude, 'longitude': self._longitude, 'map': self._map_link })
                self._hass.bus.fire(DEFAULT_NAME+'_state_update', event_data )
                _LOGGER.debug( "(" + self._name + ") Update complete...")

    def _reset_attributes(self):
        """Resets attributes."""
        self._street = None
        self._street_number = None
        self._city = None
        self._postal_town = None
        self._postal_code = None
        self._region = None
        self._country = None
        self._county = None
        self._formatted_address = None
        self._place_type = None
        self._place_name = None
        self._mtime = datetime.now()
        self._updateskipped = 0