"""
Utility functions for fetching airport data
"""
import logging
from typing import Optional
from flightradar24.api import FlightRadar24API

logger = logging.getLogger(__name__)


def get_airport_elevation(airport_icao: str) -> Optional[int]:
    """
    Fetch airport elevation from FlightRadar24API

    Args:
        airport_icao: Airport ICAO code (e.g., 'KPHX')

    Returns:
        Elevation in feet MSL, or None if not found
    """
    try:
        fr_api = FlightRadar24API()

        # Remove 'K' prefix if present (FlightRadar24 uses 3-letter codes)
        airport_code = airport_icao
        if airport_icao.startswith('K') and len(airport_icao) == 4:
            airport_code = airport_icao[1:]  # Remove K prefix for US airports

        # Fetch airport details
        airport_data = fr_api.get_airport_details(airport_code)

        # Navigate to elevation
        if (airport_data and
            'airport' in airport_data and
            airport_data['airport'] and
            'pluginData' in airport_data['airport']):

            plugin_data = airport_data['airport']['pluginData']

            if ('details' in plugin_data and
                'position' in plugin_data['details'] and
                'elevation' in plugin_data['details']['position']):

                elevation = plugin_data['details']['position']['elevation']
                logger.info(f"Fetched elevation for {airport_icao}: {elevation} ft MSL")
                return int(elevation)

        logger.warning(f"Could not find elevation for {airport_icao}")
        return None

    except Exception as e:
        logger.error(f"Error fetching elevation for {airport_icao}: {e}")
        return None
