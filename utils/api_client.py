"""
API client for fetching real flight data from creativeshrimp.work.gd
"""
import requests
import time
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class FlightDataAPIClient:
    """Client for fetching real flight data from the Creative Shrimp API"""

    BASE_URL = "http://creativeshrimp.work.gd:3000/flights"

    def __init__(self, cache_timeout: int = 3600):
        """
        Initialize the API client

        Args:
            cache_timeout: How long to cache results in seconds (default: 1 hour)
        """
        self.cache: Dict[str, tuple] = {}
        self.cache_timeout = cache_timeout

    def _calculate_cruise_speed(self, aircraft_type: str) -> int:
        """
        Return default cruise speed fallback (used only when API doesn't provide speed)

        Args:
            aircraft_type: Aircraft type with optional equipment suffix (e.g., "B738")

        Returns:
            Cruise speed in knots (default: 450 for jets)
        """
        # Simple fallback - API should provide actual cruise speeds
        logger.debug(f"Using default cruise speed fallback for: {aircraft_type}")
        return 450

    def fetch_flights(
        self,
        departure: Optional[str] = None,
        arrival: Optional[str] = None,
        limit: int = 200,
        retries: int = 3
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch flights from the API

        Args:
            departure: Departure airport ICAO code (use "any" for all departures)
            arrival: Arrival airport ICAO code (use "any" for all arrivals)
            limit: Maximum number of flights to request (API returns up to this many)
            retries: Number of retries if request fails

        Returns:
            List of flight dictionaries or None if request fails
        """
        # Build cache key
        dep = departure or "any"
        arr = arrival or "any"
        cache_key = f"{dep}:{arr}:{limit}"

        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_timeout:
                logger.debug(f"Using cached data for {cache_key}")
                return cached_data

        # Build request parameters
        params = {}
        if departure:
            params['departure'] = departure
        if arrival:
            params['arrival'] = arrival

        # Try to fetch from API
        for attempt in range(retries):
            try:
                logger.info(f"Fetching flights: departure={dep}, arrival={arr}, limit={limit} (attempt {attempt + 1}/{retries})")

                response = requests.get(self.BASE_URL, params=params, timeout=15)

                if response.status_code == 200:
                    data = response.json()

                    # Validate response structure
                    if not isinstance(data, dict) or 'success' not in data:
                        logger.error(f"Invalid API response structure: {data}")
                        return None

                    if not data.get('success'):
                        logger.warning(f"API returned success=false: {data}")
                        return None

                    # Extract flight data
                    flights = data.get('data', [])

                    if not flights:
                        logger.warning(f"No flights found for {dep} -> {arr}")
                        return []

                    # Limit to requested count
                    flights = flights[:limit]

                    logger.info(f"Fetched {len(flights)} flights from API ({dep} -> {arr})")

                    # Cache the result
                    self.cache[cache_key] = (flights, time.time())

                    return flights

                elif response.status_code == 429:
                    # Rate limited, wait and retry
                    wait_time = (attempt + 1) * 2
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"API returned status code {response.status_code}")
                    if attempt < retries - 1:
                        time.sleep(1)

            except requests.exceptions.Timeout:
                logger.error(f"Request timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    time.sleep(2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error fetching flights (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2)
            except (KeyError, ValueError, TypeError) as e:
                logger.error(f"Error parsing API response (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Unexpected error fetching flights (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(1)

        logger.error(f"Failed to fetch flights after {retries} attempts")
        return None

    def fetch_departures(self, airport_icao: str, limit: int = 200) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch all departures from a specific airport

        Args:
            airport_icao: Airport ICAO code
            limit: Maximum number of flights to fetch

        Returns:
            List of departure flight dictionaries or None if request fails
        """
        return self.fetch_flights(departure=airport_icao, arrival=None, limit=limit)

    def fetch_arrivals(self, airport_icao: str, limit: int = 200) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch all arrivals to a specific airport

        Args:
            airport_icao: Airport ICAO code
            limit: Maximum number of flights to fetch

        Returns:
            List of arrival flight dictionaries or None if request fails
        """
        return self.fetch_flights(departure=None, arrival=airport_icao, limit=limit)

    def clear_cache(self):
        """Clear all cached flight data"""
        self.cache.clear()
        logger.info("Flight data cache cleared")
