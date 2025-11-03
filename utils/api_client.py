"""
API client for fetching flight plans
"""
import requests
import random
import time
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class FlightPlanAPIClient:
    """Client for fetching flight plans from the API"""

    BASE_URL = "https://flight-plans.csko.hu/v1/flight_plan"

    def __init__(self, cache_timeout: int = 3600):
        """
        Initialize the API client

        Args:
            cache_timeout: How long to cache results in seconds
        """
        self.cache = {}
        self.cache_timeout = cache_timeout

    def _calculate_cruise_speed(self, aircraft_type: str) -> int:
        """
        Calculate typical cruise speed based on aircraft type

        Args:
            aircraft_type: Aircraft type with optional equipment suffix (e.g., "B738/L")

        Returns:
            Cruise speed in knots
        """
        from utils.constants import (
            AIRCRAFT_CRUISE_SPEEDS,
            DEFAULT_CRUISE_SPEEDS_BY_SUFFIX,
            DEFAULT_CRUISE_SPEED
        )

        # Extract base aircraft type and equipment suffix
        if '/' in aircraft_type:
            base_type, equipment_suffix = aircraft_type.split('/', 1)
        else:
            base_type = aircraft_type
            equipment_suffix = None

        # Try to find cruise speed in the mapping
        if base_type in AIRCRAFT_CRUISE_SPEEDS:
            return AIRCRAFT_CRUISE_SPEEDS[base_type]

        # Fall back to equipment suffix default
        if equipment_suffix and equipment_suffix in DEFAULT_CRUISE_SPEEDS_BY_SUFFIX:
            return DEFAULT_CRUISE_SPEEDS_BY_SUFFIX[equipment_suffix]

        # Last resort: generic default
        logger.info(f"Using default cruise speed for unknown aircraft type: {aircraft_type}")
        return DEFAULT_CRUISE_SPEED

    def get_flight_plan(self, departure: str, arrival: str, retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        Get a flight plan from departure to arrival

        Args:
            departure: Departure airport ICAO code
            arrival: Arrival airport ICAO code
            retries: Number of retries if request fails

        Returns:
            Dict with 'route', 'altitude', and 'aircraft_type' or None if not found
        """
        cache_key = f"{departure}:{arrival}"

        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_timeout:
                return cached_data

        # Try to fetch from API
        for attempt in range(retries):
            try:
                # Use a recent timestamp (last 90 days)
                since = int(time.time()) - (90 * 24 * 3600)

                params = {
                    'departure': departure,
                    'arrival': arrival,
                    'since': since
                }

                response = requests.get(self.BASE_URL, params=params, timeout=10)

                if response.status_code == 200:
                    data = response.json()

                    # Handle both list and dict responses
                    plans_list = []

                    if isinstance(data, list):
                        plans_list = data
                    elif isinstance(data, dict):
                        # API returns dict with keys: 'routes', 'adapted_routes', 'most_recent'
                        # Use 'most_recent' for individual flight plans
                        if 'most_recent' in data and data['most_recent']:
                            plans_list = data['most_recent']
                        elif 'routes' in data and data['routes']:
                            # Use aggregated routes if no individual plans
                            plans_list = data['routes']
                        elif 'plans' in data:
                            plans_list = data['plans']
                        elif 'results' in data:
                            plans_list = data['results']
                        elif 'data' in data:
                            plans_list = data['data']
                        else:
                            # Single plan returned as dict
                            plans_list = [data]

                    # Check if we got any plans
                    if plans_list and len(plans_list) > 0:
                        # Pick a random plan from the results
                        plan = random.choice(plans_list)

                        # Extract route - field name varies by response type
                        route = plan.get('route_text', plan.get('route', ''))

                        # Extract altitude - convert to MSL in feet
                        altitude = plan.get('assigned_altitude', plan.get('altitude', plan.get('max_altitude')))
                        if altitude:
                            if isinstance(altitude, int):
                                # Already in feet, keep as is
                                altitude = str(altitude)
                            elif isinstance(altitude, str):
                                # Check if it's in FL format (e.g., "FL350")
                                if altitude.startswith('FL'):
                                    fl_number = int(altitude[2:])
                                    altitude = str(fl_number * 100)
                                else:
                                    # Assume it's already in feet
                                    altitude = altitude
                        else:
                            altitude = '35000'  # Default 35,000 feet

                        # Extract aircraft type and equipment qualifier
                        aircraft_type = plan.get('aircraft_type', 'B738')
                        equipment_qualifier = plan.get('equipment_qualifier', 'L')

                        # Add equipment suffix to aircraft type
                        if equipment_qualifier and '/' not in aircraft_type:
                            aircraft_type = f"{aircraft_type}/{equipment_qualifier}"

                        # Extract callsign
                        callsign = plan.get('aircraft_id', None)

                        # Extract cruise speed from API or calculate based on aircraft type
                        cruise_speed = plan.get('cruise_speed', plan.get('cruiseSpeed', plan.get('cruise_tas')))
                        if cruise_speed:
                            # Convert to int if it's a string
                            try:
                                cruise_speed = int(cruise_speed)
                            except (ValueError, TypeError):
                                cruise_speed = None

                        # If no cruise speed from API, calculate based on aircraft type
                        if not cruise_speed:
                            cruise_speed = self._calculate_cruise_speed(aircraft_type)

                        result = {
                            'route': route,
                            'altitude': altitude,
                            'aircraft_type': aircraft_type,
                            'callsign': callsign,
                            'cruise_speed': cruise_speed
                        }

                        # Cache the result
                        self.cache[cache_key] = (result, time.time())

                        logger.info(f"Fetched flight plan {departure} -> {arrival}: {result}")
                        return result
                    else:
                        logger.warning(f"No flight plans found for {departure} -> {arrival}")
                        return None

                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"API returned status code {response.status_code}")
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching flight plan (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Error parsing flight plan response (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error fetching flight plan (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)

        return None

    def get_random_flight_plan(self, departure: str, arrival: str) -> Dict[str, Any]:
        """
        Get a flight plan or generate a fallback if API fails

        Args:
            departure: Departure airport ICAO code
            arrival: Arrival airport ICAO code

        Returns:
            Dict with 'route', 'altitude', and 'aircraft_type'
        """
        result = self.get_flight_plan(departure, arrival)

        if result:
            return result

        # Fallback to generated data
        logger.info(f"Using fallback flight plan for {departure} -> {arrival}")

        from utils.constants import COMMON_JETS

        aircraft_type = random.choice(COMMON_JETS) + '/L'  # Add /L suffix for jets
        return {
            'route': 'DCT',  # Direct
            'altitude': random.choice(['31000', '33000', '35000', '37000', '39000']),
            'aircraft_type': aircraft_type,
            'callsign': None,  # Will be generated by scenario
            'cruise_speed': self._calculate_cruise_speed(aircraft_type)
        }
