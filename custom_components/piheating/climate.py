"""
PLATFORM setup for piheating

Uses sqlalchemy to read /write to MariaDB backend

Raspberry pi does actual heating control
"""

import logging

from homeassistant.components.climate import ClimateDevice

from homeassistant.components.climate.const import (
    HVAC_MODE_AUTO,
    HVAC_MODE_HEAT,
    HVAC_MODE_OFF,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    SUPPORT_TARGET_TEMPERATURE
)

from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS
)

_LOGGER = logging.getLogger(__name__)

REQUIREMENTS = ['sqlalchemy==1.2.14']

""" PLATFORM creates a separate climate entity for each ZONE in piHeating """
def setup_platform(hass, config, add_entities, discovery_info=None):
    """ test database connections """
    temp_unit = hass.config.units.temperature_unit
    
    db_url = "mysql://ch:heatingpi@192.168.1.10/ch"
    import sqlalchemy
    from sqlalchemy.orm import sessionmaker, scoped_session

    try:
        engine = sqlalchemy.create_engine(db_url)
        sessionmaker = scoped_session(sessionmaker(bind=engine))

        """ Run a dummy query just to test the db_url """
        sess = sessionmaker()
        sess.execute("SELECT 1;")
        _LOGGER.debug("piHeating:Setup:Connected to db OK");

    except sqlalchemy.exc.SQLAlchemyError as err:
        _LOGGER.error("piHeating: Couldn't connect using %s DB_URL: %s", db_url, err)
        return

    """ call the ubiquitous getCurSchedule stored procedure to create entities and add them """
    entities = [];
    try:
        zones = sess.execute("call usp_getCurSchedule").fetchall();
        for zone in zones:
          entities.append(piClimate(zone['zName'], float(zone['sTemp']), float(zone['cTemp']),
                                    zone['nStart'], float(zone['zOverTemp']), zone['OverEnd'], zone['zo'],
                                    zone['zFlame'],
                                    sessionmaker, temp_unit));
          _LOGGER.debug("piheating: %s", zone['OverEnd'].strftime('%Y-%m-%d %H:%M:%S'));

    except sqlalchemy.exc.SQLAlchemyError as err:
        _LOGGER.error("piHeating: Couldn't fetch zones", db_url, err)

    add_entities(entities);

""" each piheating ZONE is a climate device """
class piClimate(ClimateDevice):
    """ initialise """
    def __init__(self, zName, sTemp, cTemp, nStart, zOverTemp, OverEnd, zo, zFlame, sessmaker, tempUnit):
        self._name = zName
        self.sessionmaker = sessmaker
        self._sched_temperature = cTemp
        self._over_temperature = zOverTemp
        self._hvac_modes_list = [HVAC_MODE_AUTO, HVAC_MODE_HEAT, HVAC_MODE_OFF]
        self._temp_precision = PRECISION_TENTHS
        self._temp_unit = tempUnit
        self._min_temp = 7.0
        self._max_temp = 35.0
        if zName == 'Hot Water':
            self._max_temp = 83.0
        self._overEnd = OverEnd.strftime('%Y-%m-%d %H:%M:%S')
        self._zo = zo
        self._current_temperature = sTemp
        if self._zo:
            if self._over_temperature == self._min_temp:
                self._hvac_mode = HVAC_MODE_OFF
            else:
                self._hvac_mode = HVAC_MODE_HEAT
        else:
            self._hvac_mode = HVAC_MODE_AUTO
        self._on = zFlame
        self._nStart = nStart.__str__()
        self._support_flags = SUPPORT_TARGET_TEMPERATURE
    
    @property
    def name(self):
        """Return the name of the ZONE"""
        return self._name
    
    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_modes_list
    
    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags
    
    @property
    def precision(self):
        """Return the precision of the system."""
        return self._temp_precision
    
    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._temp_unit
    
    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temp
    
    @property
    def max_temp(self):
        """Return the minimum temperature."""
        return self._max_temp
    
    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._current_temperature
    
    @property
    def hvac_modes(self):
        """Return current operating mode."""
        return self._hvac_modes_list
    
    @property
    def hvac_mode(self):
        """Return current operating mode."""
        #_LOGGER.error("piHeating: %s _hvac_mode: %s", self._name, self._hvac_mode)
        return self._hvac_mode
    
    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.
        Need to be one of CURRENT_HVAC_*.
        """
        if self._on:
            return CURRENT_HVAC_HEAT
        else:
            return CURRENT_HVAC_IDLE
    
    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        t = self._over_temperature if (self._zo == 1) else self._sched_temperature
        return t
    
    def set_temperature(self, **kwargs):
        """Set new target temperature. """
        import sqlalchemy
        try:
          t = 10
          sess = self.sessionmaker()
          if kwargs.get(ATTR_TEMPERATURE) is not None:
              t = kwargs.get(ATTR_TEMPERATURE)
          """ update zones with new temp and end date/time """
          overEnd = self._overEnd.split(None, 1)[0] + ' ' + self._nStart
          sSQL = "UPDATE zones SET zOverTemp = " + str(t) \
                 + ", zOverEnd = '" + overEnd + "' WHERE zName = '" + self._name + "'"
#          _LOGGER.error("piHeating: Update sql: %s ", sSQL)
          sess.execute(sSQL)
          sess.commit()

        except sqlalchemy.exc.SQLAlchemyError as err:
          _LOGGER.error("piHeating: Error updating temp %s", err)

        finally:
          sess.close()
        
        #self._hvac_mode = HVAC_MODE_HEAT
        self.schedule_update_ha_state()
    
    def update(self):
        """ fetch current state """
        import sqlalchemy
        try:
            sess = self.sessionmaker()
            zones = sess.execute("call usp_getCurSchedule").fetchall()
            for zone in zones:
              if (zone['zName'] == self._name):
                  
                self._current_temperature = float(zone['sTemp'])
                self._sched_temperature = float(zone['cTemp'])
                self._over_temperature = float(zone['zOverTemp'])
                self._overEnd = zone['OverEnd'].strftime('%Y-%m-%d %H:%M:%S')
                self._zo = float(zone['zo'])
                #_LOGGER.error("piHeating: %s zo %s ot %s oe %s", self._name, self._zo, self._over_temperature, self._overEnd)
                if self._zo:
                    if self._over_temperature == self._min_temp:
                        self._hvac_mode = HVAC_MODE_OFF
                    else:
                        self._hvac_mode = HVAC_MODE_HEAT
                else:
                    self._hvac_mode = HVAC_MODE_AUTO
                self._nStart = zone['nStart'].__str__()
                self._on = float(zone['zFlame'])

        except sqlalchemy.exc.SQLAlchemyError as err:
            _LOGGER.error("piHeating: Error fetching temp %s", err)
            return

        finally:
            sess.close()
    
    def set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVAC_MODE_AUTO:
            """Cancel override - reset to AUTO mode"""
            #self._hvac_mode = HVAC_MODE_AUTO
            sSQL = "UPDATE zones SET zOverEnd = now() WHERE zName = '" + self._name + "'"
        elif hvac_mode == HVAC_MODE_HEAT:
            """Turn on override - set to HEAT mode"""
            #self._hvac_mode = HVAC_MODE_HEAT
            overEnd = self._overEnd.split(None, 1)[0] + ' ' + self._nStart
            sSQL = "UPDATE zones SET zOverEnd = '" + overEnd + "' WHERE zName = '" + self._name + "'"
            if self._over_temperature == 7.0:
                sSQL = "UPDATE zones SET zOverTemp = 21, zOverEnd = '" + overEnd + "' WHERE zName = '" + self._name + "'"
        elif hvac_mode == HVAC_MODE_OFF:
            #self._hvac_mode = HVAC_MODE_OFF
            t = 7
            overEnd = self._overEnd.split(None, 1)[0] + ' ' + self._nStart
            sSQL = "UPDATE zones SET zOverTemp = " + str(t) \
                 + ", zOverEnd = '" + overEnd + "' WHERE zName = '" + self._name + "'"
        else:
            _LOGGER.error("piheating: set_hvac_mode: unrecognized hvac mode: %s", hvac_mode)
            return
        
        """Update database with new temp / override end"""
        import sqlalchemy
        #_LOGGER.error("piHeating: SQL: %s", sSQL)
        try:
          sess = self.sessionmaker()
          sess.execute(sSQL)
          sess.commit()
          
        except sqlalchemy.exc.SQLAlchemyError as err:
          _LOGGER.error("piHeating: Error updating temp %s", err)

        finally:
          sess.close()
          
        # Ensure we update the current operation after changing the mode
        self.schedule_update_ha_state()