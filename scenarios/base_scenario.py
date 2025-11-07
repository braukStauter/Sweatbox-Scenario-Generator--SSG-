"""
Base scenario class
"""
import random
import logging
import json
import threading
from typing import List, Dict, Tuple
from abc import ABC, abstractmethod
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from parsers.geojson_parser import GeoJSONParser
from parsers.cifp_parser import CIFPParser
from utils.api_client import FlightDataAPIClient
from utils.constants import POPULAR_US_AIRPORTS, LESS_COMMON_AIRPORTS, COMMON_JETS, COMMON_GA_AIRCRAFT
from utils.flight_data_filter import (
    filter_valid_flights, categorize_flights, filter_departures_by_sid,
    filter_arrivals_by_waypoint, filter_arrivals_by_stars, filter_by_parking_airline, is_ga_aircraft,
    get_airline_from_callsign, clean_route_string
)

logger = logging.getLogger(__name__)


class BaseScenario(ABC):
    """Base class for all scenario types"""

    def __init__(self, airport_icao: str, geojson_parser: GeoJSONParser,
                 cifp_parser: CIFPParser, api_client: FlightDataAPIClient,
                 cached_flights: Dict[str, List] = None):
        """
        Initialize the scenario

        Args:
            airport_icao: ICAO code of the primary airport
            geojson_parser: Parser for airport GeoJSON data
            cifp_parser: Parser for CIFP data
            api_client: API client for flight data
            cached_flights: Pre-loaded flight data dict with 'departures' and 'arrivals' keys
        """
        self.airport_icao = airport_icao
        self.geojson_parser = geojson_parser
        self.cifp_parser = cifp_parser
        self.api_client = api_client
        self.aircraft: List[Aircraft] = []
        self.used_callsigns: set = set()
        self.used_parking_spots: set = set()
        self.config = self._load_config()

        # Cached flight data from API
        self.cached_flights = cached_flights or {'departures': [], 'arrivals': []}
        self.departure_flight_pool = []
        self.arrival_flight_pool = []

        # Thread safety locks
        self.callsign_lock = threading.Lock()
        self.parking_lock = threading.Lock()
        self.aircraft_lock = threading.Lock()

    @abstractmethod
    def generate(self, **kwargs) -> List[Aircraft]:
        """
        Generate aircraft for this scenario

        Returns:
            List of Aircraft objects
        """
        pass

    def _reset_tracking(self):
        """Reset tracking sets for a new generation"""
        self.used_callsigns.clear()
        self.used_parking_spots.clear()
        self.aircraft.clear()
        logger.debug("Reset tracking sets for new generation")

    def _setup_difficulty_assignment(self, difficulty_config):
        """
        Setup difficulty assignment tracking

        Args:
            difficulty_config: Dict with 'easy', 'medium', 'hard' counts, or None

        Returns:
            Tuple of (difficulty_list, difficulty_index) for sequential assignment
        """
        if not difficulty_config:
            return None, 0

        # Create a list of difficulty levels in the order they should be assigned
        difficulty_list = []
        difficulty_list.extend(['Easy'] * difficulty_config['easy'])
        difficulty_list.extend(['Medium'] * difficulty_config['medium'])
        difficulty_list.extend(['Hard'] * difficulty_config['hard'])

        # Shuffle to randomize difficulty assignment
        import random
        random.shuffle(difficulty_list)

        logger.info(f"Difficulty assignment enabled: {difficulty_config['easy']} Easy, {difficulty_config['medium']} Medium, {difficulty_config['hard']} Hard")

        return difficulty_list, 0

    def _assign_difficulty(self, aircraft, difficulty_list, difficulty_index):
        """
        Assign difficulty level to an aircraft

        Args:
            aircraft: Aircraft object to assign difficulty to
            difficulty_list: List of difficulty levels
            difficulty_index: Current index in difficulty list

        Returns:
            Updated difficulty_index
        """
        if difficulty_list and difficulty_index < len(difficulty_list):
            aircraft.difficulty = difficulty_list[difficulty_index]
            logger.debug(f"Assigned difficulty {aircraft.difficulty} to {aircraft.callsign}")
            return difficulty_index + 1
        return difficulty_index

    def _get_runways_for_arrival(self, arrival_name: str, active_runways: list = None) -> list:
        """
        Get runways that this arrival/STAR can feed

        Args:
            arrival_name: Name of the arrival/STAR (e.g., "HYDRR1")
            active_runways: Optional list of active runways to filter by

        Returns:
            List of runway designators (e.g., ['25L', '25R'])
        """
        # Use CIFP data to get runways for this STAR
        if self.cifp_parser:
            runways = self.cifp_parser.get_runways_for_arrival(arrival_name)
        else:
            # Fallback: get all runways if CIFP not available
            runways_objs = self.geojson_parser.get_runways()
            runways = []
            for runway in runways_objs:
                if hasattr(runway, 'runway1_name'):
                    runways.append(runway.runway1_name)
                if hasattr(runway, 'runway2_name'):
                    runways.append(runway.runway2_name)

        # Filter by active runways if provided
        if active_runways and runways:
            runways = [rwy for rwy in runways if rwy in active_runways]

        return runways if runways else []

    def _parse_spawn_delay_range(self, spawn_delay_range: str) -> tuple:
        """
        Parse spawn delay range string into min/max values in seconds

        Args:
            spawn_delay_range: String in format "min-max" in MINUTES (e.g., "0-0" or "1-5")

        Returns:
            Tuple of (min_delay, max_delay) in SECONDS
        """
        min_delay_minutes, max_delay_minutes = 0, 0  # defaults - spawn all at once
        if spawn_delay_range:
            try:
                parts = spawn_delay_range.split('-')
                if len(parts) == 2:
                    min_delay_minutes = int(parts[0])
                    max_delay_minutes = int(parts[1])
            except ValueError:
                logger.warning(f"Invalid spawn delay range: {spawn_delay_range}, using default (0-0)")

        # Convert minutes to seconds for vNAS
        min_delay_seconds = min_delay_minutes * 60
        max_delay_seconds = max_delay_minutes * 60

        return min_delay_seconds, max_delay_seconds

    def apply_spawn_delays(self, aircraft_list: List[Aircraft],
                          spawn_delay_mode: SpawnDelayMode,
                          delay_value: str = None,
                          total_session_minutes: int = None):
        """
        Apply spawn delays to a list of aircraft based on the selected mode

        Args:
            aircraft_list: List of Aircraft objects to apply delays to
            spawn_delay_mode: The SpawnDelayMode enum value (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: "min-max" range in minutes (e.g., "2-5")
                        or single value (e.g., "3") for fixed increments
            total_session_minutes: For TOTAL mode: total training session length in minutes

        Notes:
            - NONE: All aircraft spawn at 0 seconds (simultaneous)
            - INCREMENTAL: Delays accumulate between each aircraft
                          Example: delay=3 min → a/c1: 0s, a/c2: 180s, a/c3: 360s, etc.
            - TOTAL: Random spawn times distributed across session length
                     Example: 30 min session → random spawns between 0 and 1800s
        """
        if spawn_delay_mode == SpawnDelayMode.NONE:
            # All aircraft spawn immediately
            for aircraft in aircraft_list:
                aircraft.spawn_delay = 0
            logger.info(f"Applied NONE spawn delays: all {len(aircraft_list)} aircraft spawn at 0s")

        elif spawn_delay_mode == SpawnDelayMode.INCREMENTAL:
            # Parse delay value (can be range or single value)
            min_delay_minutes, max_delay_minutes = self._parse_delay_value(delay_value)

            # Apply cumulative delays
            cumulative_delay = 0
            for i, aircraft in enumerate(aircraft_list):
                aircraft.spawn_delay = cumulative_delay

                # Generate next increment
                increment_minutes = random.randint(min_delay_minutes, max_delay_minutes)
                increment_seconds = increment_minutes * 60
                cumulative_delay += increment_seconds

            logger.info(f"Applied INCREMENTAL spawn delays: {len(aircraft_list)} aircraft, "
                       f"delay range {min_delay_minutes}-{max_delay_minutes} min, "
                       f"final spawn at {cumulative_delay}s")

        elif spawn_delay_mode == SpawnDelayMode.TOTAL:
            # Validate total session minutes
            if not total_session_minutes or total_session_minutes <= 0:
                logger.warning("Invalid total_session_minutes for TOTAL mode, defaulting to 30")
                total_session_minutes = 30

            # Convert to seconds
            max_delay_seconds = total_session_minutes * 60

            # Assign random spawn times within the session window
            for aircraft in aircraft_list:
                aircraft.spawn_delay = random.randint(0, max_delay_seconds)

            # Sort aircraft by spawn_delay for logical ordering
            aircraft_list.sort(key=lambda a: a.spawn_delay)

            logger.info(f"Applied TOTAL spawn delays: {len(aircraft_list)} aircraft "
                       f"distributed across {total_session_minutes} minutes (0-{max_delay_seconds}s)")

    def _parse_delay_value(self, delay_value: str) -> tuple:
        """
        Parse delay value into min/max range in minutes

        Args:
            delay_value: String in format "min-max" (e.g., "2-5") or single value (e.g., "3")

        Returns:
            Tuple of (min_delay_minutes, max_delay_minutes)
        """
        if not delay_value:
            return 0, 0

        try:
            if '-' in delay_value:
                # Range format: "min-max"
                parts = delay_value.split('-')
                min_val = int(parts[0])
                max_val = int(parts[1])
                return min_val, max_val
            else:
                # Single value: use same for min and max
                val = int(delay_value)
                return val, val
        except (ValueError, IndexError):
            logger.warning(f"Invalid delay value: {delay_value}, using default (0-0)")
            return 0, 0

    def _load_config(self) -> Dict:
        """
        Load configuration from config.json file

        Returns:
            Configuration dictionary
        """
        config_path = Path("config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded configuration from {config_path}")
                    return config
            except Exception as e:
                logger.warning(f"Error loading config file: {e}. Using default configuration.")
                return {}
        else:
            logger.info("No config.json found. Using default configuration.")
            return {}

    def _add_equipment_suffix(self, aircraft_type: str, is_ga: bool = False) -> str:
        """
        Ensure aircraft type has proper equipment suffix

        Args:
            aircraft_type: Base aircraft type (e.g., "B738", "C172")
            is_ga: True if GA aircraft, False if airline

        Returns:
            Aircraft type with equipment suffix (/L for airlines, /G for GA)
        """
        # If already has suffix, return as-is
        if '/' in aircraft_type:
            return aircraft_type

        # Add appropriate suffix
        suffix = '/G' if is_ga else '/L'
        return f"{aircraft_type}{suffix}"

    def _is_ga_aircraft_type(self, aircraft_type: str) -> bool:
        """
        Check if an aircraft type is a GA aircraft based on common GA types

        Args:
            aircraft_type: Aircraft type code (e.g., "C172", "P28A", "B738")

        Returns:
            True if GA aircraft type, False if airline/commercial
        """
        from utils.constants import COMMON_GA_AIRCRAFT

        # Remove equipment suffix if present
        base_type = aircraft_type.split('/')[0]

        # Check against known GA aircraft list
        return base_type in COMMON_GA_AIRCRAFT

    def _expand_gate_range(self, range_str: str) -> List[str]:
        """
        Expand a gate range string into individual gate names

        Examples:
            "B1-B11" -> ["B1", "B2", "B3", ..., "B11"]
            "A10-A15" -> ["A10", "A11", "A12", "A13", "A14", "A15"]
            "C1-C3" -> ["C1", "C2", "C3"]

        Args:
            range_str: Range string in format "PREFIX#-PREFIX#"

        Returns:
            List of expanded gate names
        """
        import re

        # Match pattern like "B1-B11" or "A10-A15"
        match = re.match(r'^([A-Z]+)(\d+)-([A-Z]+)(\d+)$', range_str)

        if not match:
            return []

        prefix1, start_num, prefix2, end_num = match.groups()

        # Prefixes must match
        if prefix1 != prefix2:
            logger.warning(f"Gate range prefixes don't match: {prefix1} vs {prefix2} in '{range_str}'")
            return []

        start = int(start_num)
        end = int(end_num)

        if start > end:
            logger.warning(f"Gate range start > end: {start} > {end} in '{range_str}'")
            return []

        # Generate all gates in range
        gates = [f"{prefix1}{num}" for num in range(start, end + 1)]
        logger.debug(f"Expanded gate range '{range_str}' to {len(gates)} gates: {gates[:3]}...")

        return gates

    def _get_airline_for_parking(self, parking_name: str) -> str:
        """
        Get a specific airline code for a parking spot based on configuration

        Supports:
        1. Specific gates (highest priority): "B3" -> ["JBU"]
        2. Gate ranges: "B1-B11" -> ["AAL"]
        3. Wildcards (lowest priority): "B#" -> ["AAL"]

        Priority order: Specific > Range > Wildcard

        Args:
            parking_name: Name of the parking spot (e.g., "B3", "A10")

        Returns:
            Random airline from matching configuration, or None
        """
        parking_airlines = self.config.get('parking_airlines', {})

        if self.airport_icao not in parking_airlines:
            return None

        airport_config = parking_airlines[self.airport_icao]

        # Priority 1: Check for exact match (specific gate override)
        if parking_name in airport_config:
            airlines = airport_config[parking_name]
            if airlines:
                logger.debug(f"Gate {parking_name}: Using specific assignment -> {airlines}")
                return random.choice(airlines)

        # Priority 2: Check for range matches
        for pattern, airlines in airport_config.items():
            if '-' in pattern and '#' not in pattern:
                # This is a range pattern
                expanded_gates = self._expand_gate_range(pattern)
                if parking_name in expanded_gates:
                    if airlines:
                        logger.debug(f"Gate {parking_name}: Matched range '{pattern}' -> {airlines}")
                        return random.choice(airlines)

        # Priority 3: Check for wildcard matches
        for pattern, airlines in airport_config.items():
            if '#' in pattern:
                prefix = pattern.replace('#', '')
                if parking_name.startswith(prefix):
                    if airlines:
                        logger.debug(f"Gate {parking_name}: Matched wildcard '{pattern}' -> {airlines}")
                        return random.choice(airlines)

        return None

    def _get_available_parking_spots(self, all_spots: List, ga_only: bool = None) -> List:
        """Get available parking spots that haven't been used yet"""
        available = []
        for spot in all_spots:
            if spot.name in self.used_parking_spots:
                continue

            is_ga_spot = 'GA' in spot.name.upper()
            if ga_only is True and not is_ga_spot:
                continue
            if ga_only is False and is_ga_spot:
                continue

            available.append(spot)

        return available

    def _generate_callsign(self, number_suffix: str = None, airline: str = None) -> str:
        """Generate a random callsign, ensuring it's unique"""
        airlines = ["AAL", "DAL", "UAL", "SWA", "JBU", "ASA", "SKW", "FFT", "FDX", "UPS"]

        for _ in range(100):
            selected_airline = airline if airline else random.choice(airlines)

            if number_suffix:
                base_number = random.randint(10, 99)
                flight_number = f"{base_number}{number_suffix}"
            else:
                flight_number = str(random.randint(100, 9999))

            callsign = f"{selected_airline}{flight_number}"

            if callsign not in self.used_callsigns:
                return callsign

        logger.warning("Could not generate unique callsign after 100 attempts, using fallback")
        return f"{selected_airline}{flight_number}{len(self.used_callsigns)}"

    def _generate_ga_callsign(self) -> str:
        """Generate a general aviation N-number callsign, ensuring it's unique"""
        letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        digits = "0123456789"

        for _ in range(100):
            n_number = "N"
            n_number += ''.join(random.choices(digits, k=3))
            n_number += ''.join(random.choices(letters, k=2))

            if n_number not in self.used_callsigns:
                return n_number

        logger.warning("Could not generate unique GA callsign after 100 attempts, using fallback")
        return f"N{len(self.used_callsigns):03d}AB"

    def _get_random_destination(self, exclude: str = None, less_common: bool = False) -> str:
        """Get a random US airport"""
        if less_common:
            airports = [apt for apt in LESS_COMMON_AIRPORTS if apt != exclude]
        else:
            airports = [apt for apt in POPULAR_US_AIRPORTS if apt != exclude]
        return random.choice(airports)

    def _get_random_aircraft_type(self, is_ga: bool = False) -> str:
        """Get a random aircraft type"""
        if is_ga:
            return random.choice(COMMON_GA_AIRCRAFT)
        else:
            return random.choice(COMMON_JETS)

    def _extract_sid_from_route(self, api_route: str) -> str:
        """
        Extract the SID from an API route string

        Args:
            api_route: Route string from API (e.g., "DCT XMRKS" or "RDRNR3 XMRKS J100")

        Returns:
            SID name if found, None otherwise
        """
        if not api_route or not self.cifp_parser:
            return None

        route_parts = api_route.strip().split()
        if not route_parts:
            return None

        # Get all available SIDs from CIFP
        known_sids = self.cifp_parser.get_available_sids()

        # Check first few elements for a known SID
        for part in route_parts[:3]:  # Check first 3 elements
            if part.upper() in [sid.upper() for sid in known_sids]:
                return part.upper()

        return None

    def _validate_route_for_runways(self, api_route: str, active_runways: List[str] = None,
                                     manual_sids: List[str] = None) -> bool:
        """
        Validate if an API route's SID matches the active runways

        Args:
            api_route: Route string from API
            active_runways: List of active runway designators
            manual_sids: Optional list of specific SIDs to allow

        Returns:
            True if route is valid for the runway configuration, False otherwise
        """
        # If CIFP SIDs are not being filtered, all routes are valid
        if not self.cifp_parser or (not active_runways and not manual_sids):
            return True

        # Extract SID from the route
        sid_in_route = self._extract_sid_from_route(api_route)

        # If no SID in route, it's valid (DCT routes are allowed)
        if not sid_in_route:
            logger.debug(f"No SID found in route '{api_route}', accepting as valid")
            return True

        # If manual SIDs specified, check against those
        if manual_sids:
            is_valid = sid_in_route.upper() in [s.upper() for s in manual_sids]
            if is_valid:
                logger.debug(f"Route SID '{sid_in_route}' matches manual SID list")
            else:
                logger.debug(f"Route SID '{sid_in_route}' not in manual SID list {manual_sids}")
            return is_valid

        # Otherwise, check if SID is valid for active runways
        if active_runways:
            sid_runways = self.cifp_parser.get_runways_for_departure(sid_in_route)
            if not sid_runways:
                logger.debug(f"No runway data found for SID '{sid_in_route}', accepting as valid")
                return True

            # Check if any active runway matches the SID's runways
            for active_rwy in active_runways:
                for sid_rwy in sid_runways:
                    # Normalize runway formats (remove leading zeros)
                    active_normalized = active_rwy.lstrip('0') or '0'
                    sid_normalized = sid_rwy.lstrip('0') or '0'
                    if active_normalized == sid_normalized or active_rwy == sid_rwy:
                        logger.debug(f"Route SID '{sid_in_route}' valid for runway {active_rwy}")
                        return True

            logger.debug(f"Route SID '{sid_in_route}' (runways: {sid_runways}) does not match active runways {active_runways}")
            return False

        return True

    def _get_cifp_sid_route(self, active_runways: List[str] = None,
                           manual_sids: List[str] = None) -> str:
        """
        Get a CIFP SID route based on active runways or manual SID specification

        Args:
            active_runways: List of active runway designators (e.g., ['08', '26'])
            manual_sids: Optional list of specific SIDs to use

        Returns:
            SID route string (e.g., "RDRNR3") or None if no SID available
        """
        available_sids = []

        # If manual SIDs are specified, use those
        if manual_sids and len(manual_sids) > 0:
            available_sids = manual_sids
            logger.debug(f"Using manual SIDs: {', '.join(manual_sids)}")
        # Otherwise, filter by active runways
        elif active_runways and len(active_runways) > 0:
            # Get SIDs for each active runway
            for runway in active_runways:
                runway_sids = self.cifp_parser.get_sids_for_runway(runway)
                available_sids.extend(runway_sids)

            # Remove duplicates
            available_sids = list(set(available_sids))

            if available_sids:
                logger.debug(f"Found {len(available_sids)} SIDs for runways {', '.join(active_runways)}: {', '.join(available_sids)}")
            else:
                logger.warning(f"No SIDs found for runways {', '.join(active_runways)}")
        else:
            logger.warning("No active runways or manual SIDs specified for SID selection")
            return None

        # Randomly select a SID from available options
        if available_sids:
            selected_sid = random.choice(available_sids)
            logger.debug(f"Selected SID: {selected_sid}")
            return selected_sid

        return None

    def _prepare_departure_flight_pool(self, active_runways: List[str] = None,
                                        enable_cifp_sids: bool = False,
                                        manual_sids: List[str] = None):
        """
        Prepare the pool of departure flights from cached data

        Args:
            active_runways: List of active runway names
            enable_cifp_sids: Whether to filter by SID/runway compatibility
            manual_sids: Manual SID list if specified
        """
        # Start with cached departures
        valid_flights = filter_valid_flights(self.cached_flights['departures'])
        logger.info(f"Filtered {len(valid_flights)} valid departures from {len(self.cached_flights['departures'])} cached")

        # Apply SID filtering if enabled
        if enable_cifp_sids and self.cifp_parser and active_runways:
            available_sids = manual_sids if manual_sids else self.cifp_parser.get_available_sids()
            valid_flights = filter_departures_by_sid(valid_flights, available_sids, active_runways)
            logger.info(f"After SID filtering: {len(valid_flights)} departures remain")

        self.departure_flight_pool = valid_flights

    def _get_next_departure_flight(self, parking_spot_name: str = None, is_ga_spot: bool = False) -> Dict:
        """
        Get the next departure flight from the pool

        Args:
            parking_spot_name: Optional parking spot name for airline matching
            is_ga_spot: True if this is a GA parking spot

        Returns:
            Flight dictionary or None if pool is empty
        """
        if not self.departure_flight_pool:
            # Pool depleted, fetch more
            logger.warning("Departure flight pool depleted, fetching more from API...")
            additional_flights = self.api_client.fetch_departures(self.airport_icao, limit=50)
            if additional_flights:
                valid_flights = filter_valid_flights(additional_flights)
                self.departure_flight_pool.extend(valid_flights)
                logger.info(f"Added {len(valid_flights)} more departures to pool")
            else:
                logger.error("Failed to fetch additional departures from API")
                return None

        # If parking spot has airline preference, try to match
        if parking_spot_name:
            parking_airline = self._get_airline_for_parking(parking_spot_name)
            if parking_airline:
                # Try to find flight from preferred airline
                for i, flight in enumerate(self.departure_flight_pool):
                    aircraft_type = flight.get('aircraftType', '')
                    # Skip GA aircraft at non-GA gates
                    if not is_ga_spot and self._is_ga_aircraft_type(aircraft_type):
                        continue
                    if flight.get('operator') == parking_airline:
                        return self.departure_flight_pool.pop(i)

        # Return first available non-GA flight (or any flight if GA spot)
        for i, flight in enumerate(self.departure_flight_pool):
            aircraft_type = flight.get('aircraftType', '')
            # If not a GA spot, skip GA aircraft types
            if not is_ga_spot and self._is_ga_aircraft_type(aircraft_type):
                continue
            return self.departure_flight_pool.pop(i)

        return None

    def _create_departure_aircraft(self, parking_spot, destination: str = None,
                                   callsign: str = None, aircraft_type: str = None,
                                   active_runways: List[str] = None, enable_cifp_sids: bool = False,
                                   manual_sids: List[str] = None) -> Aircraft:
        """Create a departure aircraft at a parking spot using cached flight data"""
        # Thread-safe parking spot reservation
        with self.parking_lock:
            if parking_spot.name in self.used_parking_spots:
                logger.warning(f"Parking spot {parking_spot.name} is already in use, skipping")
                return None
            self.used_parking_spots.add(parking_spot.name)

        logger.debug(f"Assigned parking spot: {parking_spot.name}")

        # Check if this is a GA parking spot
        is_ga_spot = "GA" in parking_spot.name.upper()

        # Get flight from pool
        flight_data = self._get_next_departure_flight(parking_spot.name, is_ga_spot)

        if not flight_data:
            logger.error("No flight data available for departure aircraft")
            with self.parking_lock:
                self.used_parking_spots.discard(parking_spot.name)
            return None

        # Extract data from API flight
        raw_route = flight_data.get('route', '')
        route = clean_route_string(raw_route)
        destination = destination or flight_data.get('arrivalAirport', self._get_random_destination())
        api_callsign = flight_data.get('aircraftIdentification', '')
        api_aircraft_type = flight_data.get('aircraftType', 'B738')

        # Calculate cruise altitude from requested altitude or default
        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            cruise_altitude = str(int(float(requested_alt)))
        else:
            cruise_altitude = '35000'

        # Calculate cruise speed
        cruise_speed_str = flight_data.get('requestedAirspeed')
        if cruise_speed_str:
            try:
                cruise_speed = int(float(cruise_speed_str))
            except (ValueError, TypeError):
                cruise_speed = self.api_client._calculate_cruise_speed(api_aircraft_type)
        else:
            cruise_speed = self.api_client._calculate_cruise_speed(api_aircraft_type)

        # Use provided parameters or API data
        aircraft_type = aircraft_type or api_aircraft_type

        # Ensure equipment suffix (/L for airlines, /G for GA)
        is_ga_type = self._is_ga_aircraft_type(aircraft_type)
        aircraft_type = self._add_equipment_suffix(aircraft_type, is_ga_type)

        # ALWAYS use API callsign if provided - never generate for real flight data
        # This ensures aircraft/route/callsign data stays matched from the API
        if callsign is None:
            if api_callsign and api_callsign.strip():
                callsign = api_callsign
            else:
                # Only generate if API didn't provide a callsign
                logger.warning(f"No callsign from API for flight to {destination}, generating one")
                callsign = self._generate_callsign()

        # Thread-safe callsign assignment - ensure uniqueness
        with self.callsign_lock:
            # If callsign is already used, we have a duplicate from API
            if callsign in self.used_callsigns:
                logger.warning(f"Duplicate callsign from API: {callsign}, skipping this flight")
                # Don't use this flight - return None to skip it
                with self.parking_lock:
                    self.used_parking_spots.discard(parking_spot.name)
                return None
            self.used_callsigns.add(callsign)

        ground_altitude = self.geojson_parser.field_elevation

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=parking_spot.latitude,
            longitude=parking_spot.longitude,
            altitude=ground_altitude,
            heading=parking_spot.heading,
            ground_speed=0,
            departure=self.airport_icao,
            arrival=destination,
            route=route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            flight_rules=flight_data.get('initialFlightRules', 'I')[0] if flight_data.get('initialFlightRules') else 'I',
            engine_type="J",
            parking_spot_name=parking_spot.name,
            # Additional API fields
            gufi=flight_data.get('gufi'),
            registration=flight_data.get('registration'),
            operator=flight_data.get('operator'),
            estimated_arrival_time=flight_data.get('estimatedArrivalTime'),
            wake_turbulence=flight_data.get('wakeTurbulence')
        )

        return aircraft

    def _prepare_ga_flight_pool(self):
        """Prepare pool of GA flights from cached departure data"""
        # Filter for GA aircraft (N-number callsigns)
        valid_flights = filter_valid_flights(self.cached_flights['departures'])
        ga_flights, _ = categorize_flights(valid_flights)

        self.ga_flight_pool = ga_flights
        logger.info(f"Prepared GA flight pool with {len(ga_flights)} aircraft")

    def _get_next_ga_flight(self) -> Dict:
        """Get next GA flight from pool"""
        if not hasattr(self, 'ga_flight_pool'):
            self._prepare_ga_flight_pool()

        if not self.ga_flight_pool:
            # Try to fetch more
            logger.warning("GA flight pool depleted, fetching more...")
            additional_flights = self.api_client.fetch_departures(self.airport_icao, limit=50)
            if additional_flights:
                valid_flights = filter_valid_flights(additional_flights)
                ga_flights, _ = categorize_flights(valid_flights)
                self.ga_flight_pool.extend(ga_flights)
                logger.info(f"Added {len(ga_flights)} more GA flights to pool")

        return self.ga_flight_pool.pop(0) if self.ga_flight_pool else None

    def _create_ga_aircraft(self, parking_spot, destination: str = None) -> Aircraft:
        """Create a GA (general aviation) aircraft using API data"""
        if parking_spot.name in self.used_parking_spots:
            logger.warning(f"Parking spot {parking_spot.name} is already in use, skipping")
            return None

        self.used_parking_spots.add(parking_spot.name)
        logger.debug(f"Assigned parking spot: {parking_spot.name}")

        # Try to get GA flight from API
        flight_data = self._get_next_ga_flight()

        if flight_data:
            # Use API data - ALWAYS use the API callsign to keep data matched
            api_callsign = flight_data.get('aircraftIdentification', '')
            if api_callsign and api_callsign.strip():
                callsign = api_callsign
            else:
                # API didn't provide callsign, generate one
                logger.warning("GA flight from API missing callsign, generating one")
                callsign = self._generate_ga_callsign()
            aircraft_type = flight_data.get('aircraftType', 'C172')
            destination = destination or flight_data.get('arrivalAirport', self._get_random_destination(exclude=self.airport_icao, less_common=True))
            raw_route = flight_data.get('route', 'DCT')
            route = clean_route_string(raw_route) if raw_route != 'DCT' else 'DCT'

            # Get altitude and speed from API
            requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
            if requested_alt:
                cruise_altitude = str(int(float(requested_alt)))
            else:
                cruise_altitude = str(random.randint(3000, 8000))

            cruise_speed_str = flight_data.get('requestedAirspeed')
            if cruise_speed_str:
                try:
                    cruise_speed = int(float(cruise_speed_str))
                except (ValueError, TypeError):
                    cruise_speed = self.api_client._calculate_cruise_speed(aircraft_type)
            else:
                cruise_speed = self.api_client._calculate_cruise_speed(aircraft_type)

            flight_rules = flight_data.get('initialFlightRules', 'I')[0] if flight_data.get('initialFlightRules') else 'I'
            gufi = flight_data.get('gufi')
            registration = flight_data.get('registration')
            operator = flight_data.get('operator')
            estimated_arrival_time = flight_data.get('estimatedArrivalTime')
            wake_turbulence = flight_data.get('wakeTurbulence')
        else:
            # Fallback to generated GA aircraft
            logger.warning("No GA flight data available, generating manually")
            callsign = self._generate_ga_callsign()
            aircraft_type = self._get_random_aircraft_type(is_ga=True)
            destination = destination or self._get_random_destination(exclude=self.airport_icao, less_common=True)
            route = 'DCT'
            cruise_altitude = str(random.randint(3000, 8000))
            cruise_speed = self.api_client._calculate_cruise_speed(aircraft_type)
            flight_rules = 'I'
            gufi = None
            registration = None
            operator = None
            estimated_arrival_time = None
            wake_turbulence = 'L'

        # Ensure callsign uniqueness
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                # If from API data, skip this flight to maintain data integrity
                if flight_data and flight_data.get('aircraftIdentification'):
                    logger.warning(f"Duplicate GA callsign from API: {callsign}, skipping this flight")
                    self.used_parking_spots.discard(parking_spot.name)
                    return None
                # Otherwise generate new callsign (only for fallback generated aircraft)
                while callsign in self.used_callsigns:
                    callsign = self._generate_ga_callsign()
            self.used_callsigns.add(callsign)

        # Ensure equipment suffix
        if '/' not in aircraft_type:
            aircraft_type = f"{aircraft_type}/G"

        ground_altitude = self.geojson_parser.field_elevation

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=parking_spot.latitude,
            longitude=parking_spot.longitude,
            altitude=ground_altitude,
            heading=parking_spot.heading,
            ground_speed=0,
            departure=self.airport_icao,
            arrival=destination,
            route=route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            flight_rules=flight_rules,
            engine_type="P",
            parking_spot_name=parking_spot.name,
            gufi=gufi,
            registration=registration,
            operator=operator,
            estimated_arrival_time=estimated_arrival_time,
            wake_turbulence=wake_turbulence
        )

        return aircraft

    def _prepare_arrival_flight_pool(self, waypoint: str = None, star_name: str = None, star_transitions: List[Tuple[str, str]] = None):
        """
        Prepare the pool of arrival flights from cached data

        Args:
            waypoint: Optional single waypoint to filter by (legacy)
            star_name: Optional single STAR name to filter by (legacy)
            star_transitions: Optional list of (waypoint, STAR) tuples for filtering by multiple STARs
        """
        # Start with cached arrivals
        valid_flights = filter_valid_flights(self.cached_flights['arrivals'])
        logger.info(f"Filtered {len(valid_flights)} valid arrivals from {len(self.cached_flights['arrivals'])} cached")

        # Apply STAR filtering if multiple transitions specified
        if star_transitions:
            valid_flights = filter_arrivals_by_stars(valid_flights, star_transitions)
            logger.info(f"After STAR filtering: {len(valid_flights)} arrivals remain")
        # Legacy: Apply waypoint filtering if specified
        elif waypoint:
            valid_flights = filter_arrivals_by_waypoint(valid_flights, waypoint, star_name)
            logger.info(f"After waypoint filtering ({waypoint}): {len(valid_flights)} arrivals remain")

        self.arrival_flight_pool = valid_flights

    def _get_next_arrival_flight(self) -> Dict:
        """
        Get the next arrival flight from the pool

        Returns:
            Flight dictionary or None if pool is empty
        """
        if not self.arrival_flight_pool:
            # Pool depleted, fetch more
            logger.warning("Arrival flight pool depleted, fetching more from API...")
            additional_flights = self.api_client.fetch_arrivals(self.airport_icao, limit=50)
            if additional_flights:
                valid_flights = filter_valid_flights(additional_flights)
                self.arrival_flight_pool.extend(valid_flights)
                logger.info(f"Added {len(valid_flights)} more arrivals to pool")
            else:
                logger.error("Failed to fetch additional arrivals from API")
                return None

        # Return first available flight
        return self.arrival_flight_pool.pop(0) if self.arrival_flight_pool else None

    def get_aircraft(self) -> List[Aircraft]:
        """Get generated aircraft list"""
        return self.aircraft
