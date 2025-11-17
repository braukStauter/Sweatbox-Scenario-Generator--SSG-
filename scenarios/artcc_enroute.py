"""
ARTCC Enroute scenario for Center-level operations
Supports enroute transient, arrival, and departure aircraft
"""
import logging
import random
import re
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.flight_data_filter import filter_valid_flights, clean_route_string
from utils.route_positioning import RouteParser
from utils.artcc_utils import get_artcc_boundaries

logger = logging.getLogger(__name__)


class ArtccEnrouteScenario(BaseScenario):
    """Scenario for ARTCC enroute operations"""

    def __init__(self, artcc_id: str, api_client, config: Dict = None,
                 geojson_parsers: Dict = None, cifp_parsers: Dict = None):
        """
        Initialize ARTCC scenario

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB", "ZLA")
            api_client: API client for flight data
            config: Configuration dictionary from config.json
            geojson_parsers: Dictionary mapping airport ICAO to GeoJSONParser instances
            cifp_parsers: Dictionary mapping airport ICAO to CIFPParser instances
        """
        import threading

        # Initialize ARTCC data
        self.artcc_id = artcc_id.upper()
        self.api_client = api_client
        self.aircraft: List[Aircraft] = []
        self.used_callsigns: set = set()
        self.used_spawn_points: set = set()  # Track used spawn waypoints to prevent duplicates
        self.artcc_boundaries = get_artcc_boundaries()
        self.route_parser = RouteParser()

        # Thread-safety locks for parallel generation
        self.aircraft_lock = threading.Lock()
        self.callsign_lock = threading.Lock()
        self.spawn_point_lock = threading.Lock()

        # Store airport-specific parsers
        self.geojson_parsers = geojson_parsers or {}
        self.cifp_parsers = cifp_parsers or {}

        # Load config (handle being passed the full config or just loading it)
        if config:
            self.config = config
        else:
            self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load config.json file"""
        import json
        from pathlib import Path

        config_path = Path('config.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        return {}

    def generate(self,
                 num_enroute: int = 0,
                 num_arrivals: int = 0,
                 num_departures: int = 0,
                 arrival_airports: Optional[List[str]] = None,
                 departure_airports: Optional[List[str]] = None,
                 arrival_airport_runways: Optional[Dict[str, List[str]]] = None,
                 departure_airport_runways: Optional[Dict[str, List[str]]] = None,
                 difficulty_config_enroute: Dict = None,
                 difficulty_config_arrivals: Dict = None,
                 difficulty_config_departures: Dict = None,
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None,
                 total_session_minutes: int = None,
                 cached_departures_pool: Optional[List[Dict]] = None,
                 cached_arrivals_pool: Optional[List[Dict]] = None,
                 cached_transient_pool: Optional[List[Dict]] = None) -> List[Aircraft]:
        """
        Generate ARTCC enroute scenario

        Args:
            num_enroute: Number of enroute transient aircraft
            num_arrivals: Number of arrival aircraft
            num_departures: Number of departure aircraft
            arrival_airports: List of arrival airport ICAOs
            departure_airports: List of departure airport ICAOs
            arrival_airport_runways: Dict mapping airport ICAO to list of active runways
            departure_airport_runways: Dict mapping airport ICAO to list of active runways
            difficulty_config_enroute: Difficulty distribution for enroute aircraft
            difficulty_config_arrivals: Difficulty distribution for arrivals
            difficulty_config_departures: Difficulty distribution for departures
            spawn_delay_mode: Spawn delay mode
            delay_value: Delay value/range
            total_session_minutes: Total session minutes for TOTAL mode
            cached_departures_pool: Optional pre-loaded departures pool (skips API fetch if provided)
            cached_arrivals_pool: Optional pre-loaded arrivals pool (skips API fetch if provided)
            cached_transient_pool: Optional pre-loaded transient pool (skips API fetch if provided)

        Returns:
            List of Aircraft objects
        """
        import concurrent.futures
        from pathlib import Path

        self.aircraft = []
        self.used_callsigns = set()
        self.used_spawn_points = set()

        # Store configuration for filtering and runway assignment
        self.arrival_airports = arrival_airports or []
        self.arrival_airport_runways = arrival_airport_runways or {}

        logger.info(f"Generating ARTCC {self.artcc_id} scenario: {num_enroute} enroute, {num_arrivals} arrivals, {num_departures} departures")

        departures_pool = []
        arrivals_pool = []
        transient_pool = []

        # Use cached pools if provided, otherwise fetch
        if cached_departures_pool is not None:
            logger.info(f"Using cached Departures Pool: {len(cached_departures_pool)} flights")
            departures_pool = cached_departures_pool
        if cached_arrivals_pool is not None:
            logger.info(f"Using cached Arrivals Pool: {len(cached_arrivals_pool)} flights")
            arrivals_pool = cached_arrivals_pool
        if cached_transient_pool is not None:
            logger.info(f"Using cached Transient Pool: {len(cached_transient_pool)} flights")
            transient_pool = cached_transient_pool

            # Filter out arrivals to configured airports (since cache was loaded before airports were selected)
            if arrival_airports and transient_pool:
                arrival_set = set(airport.upper() for airport in arrival_airports)
                before_count = len(transient_pool)
                transient_pool = [
                    f for f in transient_pool
                    if f.get('arrivalAirport', '').upper() not in arrival_set
                ]
                if before_count != len(transient_pool):
                    logger.info(f"Filtered cached Transient Pool: removed {before_count - len(transient_pool)} arrivals to configured airports")

        # Only fetch pools that weren't cached
        if cached_departures_pool is None or cached_arrivals_pool is None or cached_transient_pool is None:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}

                # 1. Fetch Departures Pool if needed and not cached
                if cached_departures_pool is None and num_departures > 0 and departure_airports:
                    logger.info(f"Fetching Departures Pool from {departure_airports}")
                    futures['departures'] = executor.submit(
                        self._fetch_pool_departures,
                        departure_airports
                    )

                # 2. Fetch Arrivals Pool if needed and not cached
                if cached_arrivals_pool is None and num_arrivals > 0 and arrival_airports:
                    logger.info(f"Fetching Arrivals Pool to {arrival_airports}")
                    futures['arrivals'] = executor.submit(
                        self._fetch_pool_arrivals,
                        arrival_airports
                    )

                # 3. Fetch Transient Pool if needed and not cached
                if cached_transient_pool is None and num_enroute > 0:
                    logger.info(f"Fetching Transient Pool for ARTCC {self.artcc_id}")
                    futures['transient'] = executor.submit(
                        self._fetch_pool_transient,
                        arrival_airports or []
                    )

                # Wait for all fetches to complete
                for pool_name, future in futures.items():
                    try:
                        result = future.result()
                        if pool_name == 'departures':
                            departures_pool = result
                            logger.info(f"Departures Pool: {len(departures_pool)} flights")
                        elif pool_name == 'arrivals':
                            arrivals_pool = result
                            logger.info(f"Arrivals Pool: {len(arrivals_pool)} flights")
                        elif pool_name == 'transient':
                            transient_pool = result
                            logger.info(f"Transient Pool: {len(transient_pool)} flights")
                    except Exception as e:
                        logger.error(f"Error fetching {pool_name} pool: {e}")

        # Generate aircraft from pools in parallel using threading
        generation_futures = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            if num_departures > 0 and departures_pool:
                logger.info(f"Generating {num_departures} departure aircraft...")
                generation_futures['departures'] = executor.submit(
                    self._generate_departure_aircraft,
                    num_departures, departures_pool, difficulty_config_departures,
                    departure_airport_runways
                )

            if num_arrivals > 0 and arrivals_pool:
                logger.info(f"Generating {num_arrivals} arrival aircraft...")
                generation_futures['arrivals'] = executor.submit(
                    self._generate_arrival_aircraft,
                    num_arrivals, arrivals_pool, difficulty_config_arrivals
                )

            if num_enroute > 0 and transient_pool:
                logger.info(f"Generating {num_enroute} enroute aircraft...")
                generation_futures['enroute'] = executor.submit(
                    self._generate_enroute_aircraft,
                    num_enroute, transient_pool, difficulty_config_enroute
                )

            # Wait for all generation tasks to complete
            for gen_type, future in generation_futures.items():
                try:
                    future.result()
                    logger.debug(f"Completed {gen_type} generation")
                except Exception as e:
                    logger.error(f"Error generating {gen_type} aircraft: {e}")

        # Apply spawn delays across all aircraft
        self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} total aircraft for ARTCC {self.artcc_id}")
        return self.aircraft

    def _fetch_pool_departures(self, departure_airports: List[str]) -> List[Dict]:
        """
        Fetch Departures Pool from API (fetches each airport individually)

        Args:
            departure_airports: List of departure airport ICAOs

        Returns:
            Filtered list of departure flights
        """
        all_flights = []

        # Fetch from each departure airport individually (API only supports single airports)
        for airport in departure_airports:
            try:
                logger.info(f"Fetching departures from {airport}")
                flights = self.api_client.fetch_flights(
                    departure=airport,
                    limit=800
                )

                if flights:
                    all_flights.extend(flights)
                    logger.info(f"Fetched {len(flights)} departures from {airport}")
                else:
                    logger.warning(f"No departures fetched for {airport}")

            except Exception as e:
                logger.error(f"Error fetching departures from {airport}: {e}")

        if not all_flights:
            logger.warning(f"No departures fetched for any airports")
            return []

        # Filter: no ACTIVE status, no lat/long in routes
        filtered = self._filter_pool(all_flights, "Departures")

        logger.info(f"Departures Pool: Fetched {len(all_flights)} total, filtered to {len(filtered)}")
        return filtered

    def _fetch_pool_arrivals(self, arrival_airports: List[str]) -> List[Dict]:
        """
        Fetch Arrivals Pool from API (fetches each airport individually)

        Args:
            arrival_airports: List of arrival airport ICAOs

        Returns:
            Filtered list of arrival flights
        """
        all_flights = []

        # Fetch from each arrival airport individually (API only supports single airports)
        for airport in arrival_airports:
            try:
                logger.info(f"Fetching arrivals to {airport}")
                flights = self.api_client.fetch_flights(
                    arrival=airport,
                    limit=800
                )

                if flights:
                    all_flights.extend(flights)
                    logger.info(f"Fetched {len(flights)} arrivals to {airport}")
                else:
                    logger.warning(f"No arrivals fetched for {airport}")

            except Exception as e:
                logger.error(f"Error fetching arrivals to {airport}: {e}")

        if not all_flights:
            logger.warning(f"No arrivals fetched for any airports")
            return []

        # Filter: no ACTIVE status, no lat/long in routes
        filtered = self._filter_pool(all_flights, "Arrivals")

        logger.info(f"Arrivals Pool: Fetched {len(all_flights)} total, filtered to {len(filtered)}")
        return filtered

    def _fetch_pool_transient(self, arrival_airports: List[str]) -> List[Dict]:
        """
        Fetch Transient Pool from API

        Args:
            arrival_airports: List of arrival airports to filter out

        Returns:
            Filtered list of transient flights
        """
        try:
            # Fetch from API using artcc parameter
            flights = self.api_client.fetch_artcc_flights(
                self.artcc_id,
                limit=800
            )

            if not flights:
                logger.warning(f"No transient flights fetched for ARTCC {self.artcc_id}")
                return []

            # Filter: no ACTIVE status, no lat/long in routes
            filtered = self._filter_pool(flights, "Transient")

            # Additional filter: Remove arrivals to specified airports
            if arrival_airports:
                arrival_set = set(airport.upper() for airport in arrival_airports)
                before_count = len(filtered)
                filtered = [
                    f for f in filtered
                    if f.get('arrivalAirport', '').upper() not in arrival_set
                ]
                logger.info(f"Transient Pool: Filtered out {before_count - len(filtered)} arrivals to specified airports")

            logger.info(f"Transient Pool: Fetched {len(flights)}, filtered to {len(filtered)}")
            return filtered

        except Exception as e:
            logger.error(f"Error fetching Transient Pool: {e}")
            return []

    def _filter_pool(self, flights: List[Dict], pool_name: str) -> List[Dict]:
        """
        Filter flight pool: Accept ACTIVE and PROPOSED flights with complete flight plans

        Args:
            flights: Raw flight data from API
            pool_name: Name of pool for logging

        Returns:
            Filtered list of valid flights
        """
        # Count initial status distribution
        status_counts = {}
        for f in flights:
            status = f.get('flightStatus', 'UNKNOWN')
            status_counts[status] = status_counts.get(status, 0) + 1
        logger.debug(f"{pool_name}: Initial status distribution: {status_counts}")

        # NEW: Accept both ACTIVE and PROPOSED flights
        # We filter for complete flight plans instead of just status
        accepted_flights = [f for f in flights if f.get('flightStatus') in ['ACTIVE', 'PROPOSED']]
        logger.debug(f"{pool_name}: Accepted {len(accepted_flights)} ACTIVE/PROPOSED flights (from {len(flights)} total)")

        # Apply standard validity filtering (checks for basic required fields)
        valid_flights = filter_valid_flights(accepted_flights)

        # Determine if altitude is required based on pool type
        # For Transient and Arrivals pools, altitude is optional (we'll estimate it if missing)
        # For Departures, altitude is required (they start on ground)
        require_altitude = (pool_name == "Departures")

        # Filter for required fields and no lat/long in routes
        clean_flights = []
        missing_dep_proc = 0
        missing_arr_proc = 0

        for flight in valid_flights:
            callsign = flight.get('aircraftIdentification', '')
            route = flight.get('route', '')
            altitude = flight.get('requestedAltitude') or flight.get('assignedAltitude')
            speed = flight.get('requestedAirspeed')  # API uses 'requestedAirspeed' not 'cruiseSpeed'
            dep_proc = flight.get('departureProcedure', '')
            arr_proc = flight.get('arrivalProcedure', '')
            arrival_airport = flight.get('arrivalAirport', '')

            # NEW: For Arrivals pool, only accept flights to user-selected airports
            if pool_name == "Arrivals" and arrival_airport:
                if arrival_airport not in self.arrival_airports:
                    logger.debug(f"{pool_name}: Skipping {callsign} - arrival airport {arrival_airport} not in configured list")
                    continue

            # NEW: Require complete flight plans (both departure and arrival procedures)
            if not dep_proc:
                missing_dep_proc += 1
                logger.debug(f"{pool_name}: Skipping {callsign} - missing departure procedure")
                continue
            if not arr_proc:
                missing_arr_proc += 1
                logger.debug(f"{pool_name}: Skipping {callsign} - missing arrival procedure")
                continue

            # Validate STAR name for arrivals (skip single-letter airways and missing STARs)
            if pool_name == "Arrivals" and arr_proc:
                # Skip single-letter STARs (these are airways, not STARs)
                if len(arr_proc) == 1:
                    logger.debug(f"{pool_name}: Skipping {callsign} - STAR '{arr_proc}' is single letter (likely airway)")
                    continue

                # Check if CIFP parser exists and STAR is valid
                if arrival_airport in self.cifp_parsers:
                    cifp_parser = self.cifp_parsers[arrival_airport]
                    available_stars = cifp_parser.get_available_stars()

                    # Match STAR base name (strip numbers)
                    import re
                    star_base = re.sub(r'\d+$', '', arr_proc.upper())
                    star_found = False

                    for cifp_star in available_stars:
                        cifp_star_base = re.sub(r'\d+$', '', cifp_star.upper())
                        if cifp_star_base == star_base:
                            star_found = True
                            break

                    if not star_found:
                        logger.debug(f"{pool_name}: Skipping {callsign} - STAR '{arr_proc}' not found in CIFP for {arrival_airport}")
                        continue

            # Check for lat/long in routes
            if self._has_lat_long_format(route):
                logger.debug(f"{pool_name}: Skipping {callsign} - route contains lat/long")
                continue

            # Require valid route and speed
            if not route:
                logger.debug(f"{pool_name}: Skipping {callsign} - missing route")
                continue
            if not speed:
                logger.debug(f"{pool_name}: Skipping {callsign} - missing cruise speed")
                continue

            # Altitude is only required for Arrivals/Departures
            if require_altitude and not altitude:
                logger.debug(f"{pool_name}: Skipping {callsign} - missing altitude")
                continue

            clean_flights.append(flight)

        logger.info(f"{pool_name}: Filtered to {len(clean_flights)} flights with complete data (from {len(valid_flights)} valid)")
        if missing_dep_proc > 0 or missing_arr_proc > 0:
            logger.info(f"  - Filtered out {missing_dep_proc} flights missing departure procedure")
            logger.info(f"  - Filtered out {missing_arr_proc} flights missing arrival procedure")

        return clean_flights

    def _procedure_matches_runways(self, procedure: str, active_runways: List[str],
                                   airport_icao: str, is_sid: bool) -> bool:
        """
        Check if a SID or STAR matches the active runways using CIFP data

        Args:
            procedure: SID or STAR name (e.g., "EAGUL6")
            active_runways: List of active runway identifiers (e.g., ["08", "7R"])
            airport_icao: Airport ICAO code
            is_sid: True if checking SID, False if checking STAR

        Returns:
            True if procedure is valid for at least one active runway
        """
        if not procedure:
            return False

        # Get CIFP parser for this airport
        cifp_parser = self.cifp_parsers.get(airport_icao)
        if not cifp_parser:
            logger.debug(f"No CIFP parser for {airport_icao}, accepting all procedures")
            return True

        # Strip numeric suffix from procedure name
        proc_base = re.sub(r'\d+$', '', procedure)

        # Check each active runway
        for runway in active_runways:
            if is_sid:
                # Get SIDs for this runway
                sids = cifp_parser.get_sids_for_runway(runway)
                if any(re.sub(r'\d+$', '', sid) == proc_base for sid in sids):
                    return True
            else:
                # Get STARs for this runway
                stars = cifp_parser.get_stars_for_runway(runway)
                if any(re.sub(r'\d+$', '', star) == proc_base for star in stars):
                    return True

        return False


    def _generate_enroute_aircraft(self, count: int, flight_pool: List[Dict],
                                    difficulty_config: Dict = None):
        """Generate enroute transient aircraft"""
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        if not flight_pool:
            logger.warning("No flights in Transient Pool")
            return

        created = 0
        attempts = 0
        max_attempts = count * 20

        while created < count and attempts < max_attempts and flight_pool:
            flight_data = random.choice(flight_pool)

            # Create enroute aircraft
            aircraft = self._create_enroute_aircraft(flight_data)

            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                # Thread-safe append
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                created += 1

            attempts += 1

        logger.info(f"Created {created} enroute aircraft (requested {count})")

    def _generate_arrival_aircraft(self, count: int, flight_pool: List[Dict],
                                    difficulty_config: Dict = None):
        """Generate arrival aircraft"""
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        if not flight_pool:
            logger.warning("No flights in Arrivals Pool")
            return

        created = 0
        attempts = 0
        max_attempts = count * 20

        while created < count and attempts < max_attempts and flight_pool:
            flight_data = random.choice(flight_pool)

            aircraft = self._create_arrival_aircraft(flight_data)

            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                # Thread-safe append
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                created += 1

            attempts += 1

        logger.info(f"Created {created} arrival aircraft (requested {count})")

    def _generate_departure_aircraft(self, count: int, flight_pool: List[Dict],
                                      difficulty_config: Dict = None,
                                      departure_airport_runways: Dict[str, List[str]] = None):
        """Generate departure aircraft at parking spots with geojson validation and SID filtering"""
        from pathlib import Path

        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        if not flight_pool:
            logger.warning("No flights in Departures Pool")
            return

        # Get unique departure airports from pool
        departure_airports = set()
        for flight in flight_pool:
            dep_airport = flight.get('departureAirport', '').upper()
            if dep_airport:
                departure_airports.add(dep_airport)

        # Validate geojson files exist for all departure airports
        airport_data_dir = Path('airport_data')
        valid_airports = {}

        for airport_icao in departure_airports:
            # Extract 3-letter code (e.g., KPHX -> PHX)
            airport_3letter = airport_icao[1:] if airport_icao.startswith('K') else airport_icao[-3:]
            geojson_path = airport_data_dir / f"{airport_3letter}.geojson"

            if not geojson_path.exists():
                logger.warning(f"WARNING: No geojson file found for {airport_icao} at {geojson_path}, aircraft from this airport will be skipped")
            else:
                # Check if we have a parser for this airport
                parser = self.geojson_parsers.get(airport_icao)
                if parser:
                    valid_airports[airport_icao] = parser
                    logger.debug(f"Validated geojson for {airport_icao}")

        if not valid_airports:
            logger.error("ERROR: No valid airport GeoJSON data available for departure aircraft spawning")
            logger.error(f"Skipping {count} requested departure aircraft")
            return

        # Collect all parking spots from valid airports
        all_parking_spots = []
        airport_parking_map = {}

        for airport_icao, geojson_parser in valid_airports.items():
            parking_spots = geojson_parser.get_parking_spots()
            logger.info(f"Found {len(parking_spots)} parking spots at {airport_icao}")

            for spot in parking_spots:
                all_parking_spots.append(spot)
                airport_parking_map[spot.name] = airport_icao

        if not all_parking_spots:
            logger.error("ERROR: No parking spots found in airport GeoJSON data")
            logger.error(f"Skipping {count} requested departure aircraft")
            return

        if count > len(all_parking_spots):
            logger.warning(f"Requested {count} departures but only {len(all_parking_spots)} parking spots available")
            count = len(all_parking_spots)

        # Shuffle parking spots for variety
        random.shuffle(all_parking_spots)

        created = 0
        for spot in all_parking_spots:
            if created >= count:
                break

            # Get the airport for this parking spot
            airport_icao = airport_parking_map[spot.name]

            # Filter flights departing from this airport
            airport_flights = [f for f in flight_pool if f.get('departureAirport', '').upper() == airport_icao]

            if not airport_flights:
                logger.debug(f"No flights available for departure airport {airport_icao}")
                continue

            # If active runways specified for this airport, filter by SID compatibility
            active_runways = departure_airport_runways.get(airport_icao) if departure_airport_runways else None

            if active_runways:
                # Filter flights with SIDs that match active runways
                valid_flights = []
                for flight in airport_flights:
                    sid = flight.get('departureProcedure', '')
                    if not sid or self._procedure_matches_runways(sid, active_runways, airport_icao, is_sid=True):
                        valid_flights.append(flight)

                if valid_flights:
                    airport_flights = valid_flights
                    logger.debug(f"Filtered to {len(valid_flights)} flights with valid SIDs for runways {active_runways} at {airport_icao}")
                else:
                    logger.warning(f"No flights with valid SIDs for runways {active_runways} at {airport_icao}, using any available flight")

            flight_data = random.choice(airport_flights)

            aircraft = self._create_departure_aircraft(flight_data, spot, airport_icao)

            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                # Thread-safe append
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                created += 1

        logger.info(f"Created {created} departure aircraft at parking spots (requested {count})")

    def _create_enroute_aircraft(self, flight_data: Dict) -> Optional[Aircraft]:
        """Create enroute transient aircraft spawned along their route within ARTCC"""
        # Extract flight data - preserve API route exactly
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')  # Keep exact API route
        departure = flight_data.get('departureAirport', 'KORD')
        arrival = flight_data.get('arrivalAirport', 'KLAX')

        # Check callsign uniqueness (thread-safe)
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        # Add equipment suffix
        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        # Find spawn waypoint along route within ARTCC (use clean version for parsing only)
        clean_route = clean_route_string(filed_route)
        spawn_info = self._find_spawn_waypoint_on_route(clean_route, is_arrival=False)

        if not spawn_info:
            logger.debug(f"Could not find spawn waypoint for {callsign} on route: {filed_route}")
            self.used_callsigns.remove(callsign)  # Return callsign to pool
            return None

        # Check if this spawn point is already used (thread-safe)
        spawn_key = f"{spawn_info['waypoint']}"
        with self.spawn_point_lock:
            if spawn_key in self.used_spawn_points:
                logger.warning(f"Spawn point {spawn_key} already in use, skipping {callsign}")
                with self.callsign_lock:
                    self.used_callsigns.remove(callsign)
                return None
            self.used_spawn_points.add(spawn_key)

        # Get filed altitude from API, or estimate if not available
        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            altitude = int(float(requested_alt))
        else:
            # API doesn't provide altitude for PROPOSED flights, estimate it
            altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
            logger.debug(f"{callsign}: Estimated altitude {altitude} ft (API data not available)")
        cruise_altitude = str(altitude)

        # Get filed speed from API - guaranteed to exist due to filtering
        filed_speed = flight_data.get('requestedAirspeed')  # API uses 'requestedAirspeed' not 'cruiseSpeed'
        ground_speed = int(float(filed_speed))
        cruise_speed = ground_speed

        # Navigation path: next waypoint after spawn, followed by remainder of filed route
        initial_route = spawn_info.get('initial_route', clean_route)

        # For transient aircraft, set primary_airport to the ARTCC's primary airport
        # Use the first arrival airport from the configuration
        primary_airport_3letter = None
        if self.arrival_airport_runways:
            first_airport = list(self.arrival_airport_runways.keys())[0]
            primary_airport_3letter = first_airport[1:] if first_airport.startswith('K') else first_airport[-3:]

        # Create aircraft
        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=spawn_info['latitude'],
            longitude=spawn_info['longitude'],
            altitude=altitude,
            heading=int(spawn_info['heading']),
            ground_speed=ground_speed,
            starting_conditions_type='Fix',
            fix=spawn_info['waypoint'],
            departure=departure,
            arrival=arrival,
            route=clean_route,  # Cleaned route (dots to spaces, airports/time removed)
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            flight_rules="I",
            primary_airport=primary_airport_3letter,  # Set ARTCC's primary airport for vNAS
            spawn_delay=0
        )

        return aircraft

    def _create_arrival_aircraft(self, flight_data: Dict) -> Optional[Aircraft]:
        """Create arrival aircraft spawned at STAR waypoint within ARTCC using CIFP data"""
        # Extract flight data
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')
        departure = flight_data.get('departureAirport', 'KORD')
        arrival = flight_data.get('arrivalAirport', 'KPHX')
        arr_proc = flight_data.get('arrivalProcedure', '')

        # Check callsign uniqueness (thread-safe)
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        # Get STAR spawn waypoint from CIFP (first STAR waypoint within ARTCC)
        spawn_waypoint_name, spawn_waypoint_obj, actual_star_name = self._find_star_spawn_waypoint(arrival, arr_proc)

        if not spawn_waypoint_name or not spawn_waypoint_obj or not actual_star_name:
            logger.debug(f"Could not find STAR waypoint within ARTCC for arrival {callsign}")
            with self.callsign_lock:
                self.used_callsigns.remove(callsign)
            return None

        # Use actual STAR name from CIFP (not API's potentially incorrect version)
        arr_proc = actual_star_name

        # Check if this spawn point is already used (thread-safe)
        spawn_key = f"{spawn_waypoint_name}"
        with self.spawn_point_lock:
            if spawn_key in self.used_spawn_points:
                logger.warning(f"Spawn point {spawn_key} already in use, skipping {callsign}")
                with self.callsign_lock:
                    self.used_callsigns.remove(callsign)
                return None
            self.used_spawn_points.add(spawn_key)

        # Get altitude from CIFP constraints (with fallback to estimation)
        altitude = self._get_altitude_from_cifp(spawn_waypoint_obj, arr_proc, departure, arrival, aircraft_type)
        cruise_altitude = str(altitude)

        # Get filed speed from API - guaranteed to exist due to filtering
        filed_speed = flight_data.get('requestedAirspeed')
        ground_speed = int(float(filed_speed))
        cruise_speed = ground_speed

        # Calculate heading from CIFP inbound course
        if spawn_waypoint_obj.inbound_course:
            heading = int(spawn_waypoint_obj.inbound_course)
        else:
            # Fallback: calculate heading from position to next waypoint
            cifp_parser = self.cifp_parsers.get(arrival)
            # Use list-based lookup instead of sequence numbers
            star_waypoints_list = cifp_parser.get_arrival_waypoints(arr_proc) if cifp_parser else []

            # Find spawn waypoint index in list
            spawn_idx = -1
            for idx, wp_name in enumerate(star_waypoints_list):
                if wp_name.upper() == spawn_waypoint_name.upper():
                    spawn_idx = idx
                    break

            # Get next waypoint from list (if exists)
            next_wp = None
            if spawn_idx >= 0 and spawn_idx + 1 < len(star_waypoints_list):
                next_wp_name = star_waypoints_list[spawn_idx + 1]
                next_wp = cifp_parser.get_transition_waypoint(next_wp_name, arr_proc) if cifp_parser else None

            if next_wp and next_wp.latitude and next_wp.longitude:
                heading = int(self.route_parser.calculate_bearing(
                    spawn_waypoint_obj.latitude, spawn_waypoint_obj.longitude,
                    next_wp.latitude, next_wp.longitude
                ))
            else:
                heading = 0  # Fallback

        # Extract 3-letter airport code from ICAO (e.g., KPHX -> PHX)
        arrival_3letter = arrival[1:] if arrival.startswith('K') else arrival[-3:]

        # Get arrival runway based on STAR (if available)
        arrival_runway = None
        if arr_proc and arrival in self.arrival_airport_runways:
            active_runways = self.arrival_airport_runways[arrival]
            arrival_runway = self._get_runway_for_star(arrival, arr_proc, active_runways)
            logger.debug(f"Assigned runway {arrival_runway} for {callsign} with STAR {arr_proc} to {arrival}")

        # Get next waypoint in STAR for navigation path
        # Use list-based lookup instead of sequence numbers (more reliable)
        cifp_parser = self.cifp_parsers.get(arrival)
        star_waypoints_list = cifp_parser.get_arrival_waypoints(arr_proc) if cifp_parser else []

        # Find spawn waypoint index in list
        spawn_idx = -1
        for idx, wp_name in enumerate(star_waypoints_list):
            if wp_name.upper() == spawn_waypoint_name.upper():
                spawn_idx = idx
                break

        # Get next waypoint from list (if exists)
        next_fix_name = None
        if spawn_idx >= 0 and spawn_idx + 1 < len(star_waypoints_list):
            next_fix_name = star_waypoints_list[spawn_idx + 1]
            logger.debug(f"Found next waypoint after {spawn_waypoint_name}: {next_fix_name} (index {spawn_idx + 1} in STAR {arr_proc})")
        else:
            # Fallback to spawn waypoint if no next waypoint (last waypoint in STAR)
            next_fix_name = spawn_waypoint_name
            logger.debug(f"No next waypoint found after {spawn_waypoint_name}, using spawn waypoint as fallback")

        if arr_proc and arrival_runway:
            # Clean runway format (remove 'RW' prefix if present)
            runway_suffix = arrival_runway.replace('RW', '')
            navigation_path = f"{next_fix_name} {arr_proc}.{runway_suffix}"
            logger.debug(f"Navigation path for {callsign}: {navigation_path} (spawn at {spawn_waypoint_name}, navigate to {next_fix_name})")
        elif arr_proc:
            # STAR without specific runway
            navigation_path = f"{next_fix_name} {arr_proc}"
            logger.debug(f"Navigation path for {callsign}: {navigation_path}")
        else:
            # No STAR, just next waypoint and arrival airport
            navigation_path = f"{next_fix_name} {arrival}"
            logger.debug(f"Navigation path for {callsign}: {navigation_path}")

        # Clean route for vNAS (convert dots to spaces, remove airports/time)
        clean_route = clean_route_string(filed_route)

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=spawn_waypoint_obj.latitude,
            longitude=spawn_waypoint_obj.longitude,
            altitude=altitude,
            heading=heading,
            ground_speed=ground_speed,
            starting_conditions_type='Fix',
            fix=spawn_waypoint_name,
            departure=departure,
            arrival=arrival,
            route=clean_route,  # Cleaned route (dots to spaces, airports/time removed)
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            navigation_path=navigation_path,
            arrival_runway=arrival_runway,  # Assign runway based on STAR
            star=arr_proc,  # Store the STAR/arrival procedure
            flight_rules="I",
            primary_airport=arrival_3letter,  # Set arrival airport for vNAS
            spawn_delay=0
        )

        return aircraft

    def _create_departure_aircraft(self, flight_data: Dict, parking_spot, airport_icao: str) -> Optional[Aircraft]:
        """Create departure aircraft at parking spot"""
        # Extract flight data - clean route for vNAS
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')
        departure = airport_icao  # Use the actual departure airport from parking assignment
        arrival = flight_data.get('arrivalAirport', 'KORD')
        dep_proc = flight_data.get('departureProcedure', '')  # Fixed: was 'departureProc', should be 'departureProcedure'

        # Check callsign uniqueness (thread-safe)
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        # Clean route for vNAS (convert dots to spaces, remove airports/time)
        clean_route = clean_route_string(filed_route)

        # Extract 3-letter airport code from ICAO (e.g., KPHX -> PHX)
        departure_3letter = departure[1:] if departure.startswith('K') else departure[-3:]

        # Get filed altitude from API - guaranteed to exist due to filtering
        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        cruise_altitude = str(int(float(requested_alt)))

        # Get filed speed from API - guaranteed to exist due to filtering
        filed_speed = flight_data.get('requestedAirspeed')  # API uses 'requestedAirspeed' not 'cruiseSpeed'
        cruise_speed = int(float(filed_speed))

        # Create aircraft at parking spot
        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=parking_spot.latitude,
            longitude=parking_spot.longitude,
            altitude=0,  # Ground level
            heading=int(parking_spot.heading),
            ground_speed=0,  # Stationary at gate
            starting_conditions_type='Parking',
            parking_spot_name=parking_spot.name,
            departure=departure,
            arrival=arrival,
            route=clean_route,  # Cleaned route (dots to spaces, airports/time removed)
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            sid=dep_proc,  # Store SID in the sid field
            flight_rules="I",
            primary_airport=departure_3letter,  # Set departure airport for vNAS
            spawn_delay=0
        )

        return aircraft

    def _find_spawn_waypoint_on_route(self, route: str, is_arrival: bool = False,
                                      star_name: str = '') -> Optional[Dict]:
        """
        Find a waypoint on the route that is within ARTCC boundaries

        Args:
            route: Route string
            is_arrival: True if this is an arrival (spawn before STAR)
            star_name: STAR name for arrivals

        Returns:
            Dict with 'waypoint', 'heading', or None if no suitable waypoint found
        """
        # Parse route into waypoints
        waypoints = self.route_parser.parse_route_string(route)

        if not waypoints:
            return None

        # Get coordinates for waypoints
        route_coords = self.route_parser.get_route_waypoint_coordinates(waypoints)

        if len(route_coords) < 2:
            return None

        # Find waypoints within ARTCC
        waypoints_in_artcc = []
        for i, (wp_name, lat, lon) in enumerate(route_coords):
            if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
                waypoints_in_artcc.append((i, wp_name, lat, lon))

        if not waypoints_in_artcc:
            logger.debug(f"No waypoints found within ARTCC {self.artcc_id}")
            return None

        # For arrivals, find STAR waypoints and spawn before them
        if is_arrival and star_name:
            # Strip numeric suffix from STAR name
            star_base = re.sub(r'\d+$', '', star_name.upper())

            # Try to find STAR waypoint in route (look for exact match or match with numbers)
            star_index = None
            for i, wp_name in enumerate(waypoints):
                wp_upper = wp_name.upper()
                # Match either exact STAR base name or with numbers (DINGO or DINGO6)
                if wp_upper == star_base or wp_upper == star_name.upper():
                    star_index = i
                    break

            # Filter to waypoints before STAR
            if star_index is not None:
                logger.debug(f"Found STAR {star_name} at waypoint index {star_index} ({waypoints[star_index]})")
                waypoints_in_artcc = [
                    (idx, name, lat, lon) for idx, name, lat, lon in waypoints_in_artcc
                    if idx < star_index
                ]
                logger.debug(f"Filtered to {len(waypoints_in_artcc)} waypoints before STAR")
            else:
                # STAR not found in route - this is unusual but can happen
                logger.warning(f"STAR {star_name} not found in route, using all ARTCC waypoints")

        if not waypoints_in_artcc:
            logger.warning(f"No suitable waypoints found before STAR, cannot spawn arrival")
            return None

        # For arrivals, select the FIRST waypoint in ARTCC (maximize time in airspace)
        # For enroute, select a random waypoint
        if is_arrival:
            # Select first waypoint in ARTCC (maximize time aircraft spends in airspace)
            selected_idx, wp_name, lat, lon = waypoints_in_artcc[0]
            logger.debug(f"Selected first waypoint within ARTCC: {wp_name} at index {selected_idx}")
        else:
            # Select a random waypoint from those in ARTCC
            selected_idx, wp_name, lat, lon = random.choice(waypoints_in_artcc)

        # Calculate heading to next waypoint
        heading = 0
        if selected_idx + 1 < len(route_coords):
            next_wp_name, next_lat, next_lon = route_coords[selected_idx + 1]
            heading = int(self.route_parser.calculate_bearing(lat, lon, next_lat, next_lon))

        # Build initial route string (waypoints after the spawn point)
        remaining_waypoints = waypoints[selected_idx + 1:] if selected_idx + 1 < len(waypoints) else []
        initial_route = ' '.join(remaining_waypoints) if remaining_waypoints else ''

        return {
            'waypoint': wp_name,
            'heading': heading,
            'latitude': lat,
            'longitude': lon,
            'waypoint_index': selected_idx,
            'all_waypoints': waypoints,
            'initial_route': initial_route
        }

    def _add_equipment_suffix(self, aircraft_type: str, is_ga: bool) -> str:
        """Add equipment suffix to aircraft type"""
        if '/' in aircraft_type:
            return aircraft_type

        suffix = '/G' if is_ga else '/L'
        return f"{aircraft_type}{suffix}"

    def _estimate_cruise_altitude(self, dep_airport: str, arr_airport: str, aircraft_type: str) -> int:
        """
        Estimate a reasonable cruise altitude based on aircraft type when API doesn't provide it

        Args:
            dep_airport: Departure airport ICAO
            arr_airport: Arrival airport ICAO
            aircraft_type: Aircraft type code (e.g., B738, A320)

        Returns:
            Estimated cruise altitude in feet
        """
        if not aircraft_type:
            return 35000  # Default to typical jet altitude

        # Remove equipment suffix if present
        ac_type = aircraft_type.split('/')[0].upper()

        # Jets - typically cruise FL340-FL410
        jet_types = [
            'B7', 'A3', 'B737', 'B738', 'B739', 'B737', 'A320', 'A321', 'A319',
            'B752', 'B753', 'B763', 'B764', 'B772', 'B773', 'B77W', 'B788', 'B789',
            'CRJ', 'E170', 'E175', 'E190', 'E195', 'A21N', 'B38M', 'B39M',
            'MD8', 'MD9', 'DC9', 'E545', 'E135', 'E145', 'CL30', 'CL60', 'GLF'
        ]

        # Turboprops - typically cruise FL240-FL280
        turboprop_types = [
            'DH8', 'AT7', 'AT4', 'SF34', 'BE20', 'BE35', 'PC12', 'TBM'
        ]

        # Light aircraft - typically cruise 8000-12000 ft
        ga_types = ['C1', 'C2', 'P28', 'BE', 'PA', 'SR2', 'COL']

        # Check if it's a jet
        if any(ac_type.startswith(j) for j in jet_types):
            # Jets typically cruise FL340-FL410, with FL350-FL380 most common
            return random.choice([34000, 35000, 36000, 37000, 38000, 39000, 40000])

        # Check if it's a turboprop
        if any(ac_type.startswith(tp) for tp in turboprop_types):
            # Turboprops typically cruise FL240-FL280
            return random.choice([24000, 25000, 26000, 27000, 28000])

        # Check if it's a GA aircraft
        if any(ac_type.startswith(ga) for ga in ga_types):
            return random.choice([8000, 9000, 10000, 11000, 12000])

        # Default to typical commercial jet altitude
        logger.debug(f"Unknown aircraft type {aircraft_type}, defaulting to FL350")
        return 35000

    def _get_altitude_from_cifp(self, waypoint, star_name: str, departure: str, arrival: str, aircraft_type: str) -> int:
        """
        Get altitude from CIFP waypoint data with fallback to API/estimation

        Args:
            waypoint: Waypoint object from CIFP (may be None)
            star_name: STAR name
            departure: Departure airport ICAO
            arrival: Arrival airport ICAO
            aircraft_type: Aircraft type code

        Returns:
            Altitude in feet MSL
        """
        # Priority 1: CIFP max_altitude (top of altitude window)
        if waypoint and waypoint.max_altitude:
            logger.debug(f"Using CIFP max_altitude: {waypoint.max_altitude} ft for STAR {star_name}")
            return waypoint.max_altitude

        # Priority 2: CIFP min_altitude
        if waypoint and waypoint.min_altitude:
            logger.debug(f"Using CIFP min_altitude: {waypoint.min_altitude} ft for STAR {star_name}")
            return waypoint.min_altitude

        # Priority 3: Estimate based on aircraft type (CIFP data not available)
        altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        logger.debug(f"No CIFP altitude constraints, estimating {altitude} ft for {aircraft_type}")
        return altitude

    def _find_star_spawn_waypoint(self, arrival_airport: str, star_name: str):
        """
        Find the first STAR waypoint within ARTCC boundaries using CIFP data

        Args:
            arrival_airport: Arrival airport ICAO code
            star_name: STAR name (e.g., "EAGUL6", "DINGO6", or "BRUSR" from API)

        Returns:
            Tuple of (waypoint_name, waypoint_object, actual_star_name) if found, (None, None, None) otherwise
        """
        # Get CIFP parser for arrival airport
        cifp_parser = self.cifp_parsers.get(arrival_airport)
        if not cifp_parser:
            logger.warning(f"No CIFP parser available for {arrival_airport}")
            return None, None, None

        # Try to find matching STAR - API may return "BRUSR" but CIFP has "BRUSR1"
        # Get available STARs from CIFP
        available_stars = cifp_parser.get_available_stars()
        matching_star = None

        # Strip numbers from input star name to match base name
        import re
        star_base = re.sub(r'\d+$', '', star_name.upper())

        # Look for STAR that starts with the base name
        for cifp_star in available_stars:
            cifp_star_base = re.sub(r'\d+$', '', cifp_star.upper())
            if cifp_star_base == star_base:
                matching_star = cifp_star
                logger.debug(f"Matched API STAR '{star_name}' to CIFP STAR '{cifp_star}'")
                break

        if not matching_star:
            logger.warning(f"No matching STAR found in CIFP for API STAR '{star_name}' at {arrival_airport}")
            logger.debug(f"Available STARs: {available_stars}")
            return None, None, None

        # Get all waypoints in the STAR from CIFP
        star_waypoints_list = cifp_parser.get_arrival_waypoints(matching_star)
        if not star_waypoints_list:
            logger.warning(f"No waypoints found for STAR {matching_star} at {arrival_airport}")
            return None, None, None

        logger.debug(f"Found {len(star_waypoints_list)} waypoints in STAR {matching_star}: {star_waypoints_list}")

        # Find first STAR waypoint within ARTCC boundaries
        for wp_name in star_waypoints_list:
            waypoint = cifp_parser.get_transition_waypoint(wp_name, matching_star)
            if waypoint and waypoint.latitude and waypoint.longitude:
                # Check if waypoint is within ARTCC boundaries
                if self.artcc_boundaries.is_point_in_artcc(waypoint.latitude, waypoint.longitude, self.artcc_id):
                    logger.debug(f"Found STAR waypoint {wp_name} within ARTCC {self.artcc_id} at {waypoint.latitude}, {waypoint.longitude}")
                    return wp_name, waypoint, matching_star
                else:
                    logger.debug(f"STAR waypoint {wp_name} outside ARTCC {self.artcc_id}")

        logger.warning(f"No STAR waypoints within ARTCC {self.artcc_id} for {matching_star}")
        return None, None, None

    def _get_runway_for_star(self, airport_icao: str, star_name: str, active_runways: List[str]) -> Optional[str]:
        """
        Get the appropriate arrival runway for a STAR

        Args:
            airport_icao: Airport ICAO code
            star_name: STAR name (e.g., "EAGUL6")
            active_runways: List of active runways from configuration

        Returns:
            Runway identifier or None
        """
        if not star_name or not active_runways:
            return None

        # Get CIFP parser for this airport
        cifp_parser = self.cifp_parsers.get(airport_icao)
        if not cifp_parser:
            # No CIFP parser, return first active runway
            return active_runways[0] if active_runways else None

        # Strip numeric suffix from STAR name
        star_base = re.sub(r'\d+$', '', star_name.upper())

        # Check if this STAR is valid for any of the active runways
        star_runways = cifp_parser.get_runways_for_arrival(star_name)
        if not star_runways:
            # No runway information, return first active runway
            return active_runways[0] if active_runways else None

        # Find first active runway that matches STAR's runways
        for runway in active_runways:
            runway_clean = runway.replace('RW', '').upper()
            if any(runway_clean in str(sr).upper() for sr in star_runways):
                return runway

        # No match found, return first runway from STAR
        if star_runways:
            return str(star_runways[0])

        # Fallback
        return active_runways[0] if active_runways else None

    def _has_lat_long_format(self, route: str) -> bool:
        """
        Check if route contains lat/long format coordinates or problematic airways (which vNAS can't parse)

        Args:
            route: Route string to check

        Returns:
            True if route contains lat/long format or unsupported airways
        """
        if not route:
            return False

        # Check for common lat/long patterns:
        # - N/S followed by digits (latitude)
        # - Followed by W/E and digits (longitude)
        # Examples: "N40W075", "4012N07805W", "0100S/15500W"

        # Pattern 1: DDMMN/SDDDMMW/E (e.g., 4012N07805W)
        if re.search(r'\d{4}[NS]\d{5}[EW]', route):
            return True

        # Pattern 2: Lat/Long with slashes (e.g., 0100S/15500W)
        if re.search(r'\d{4}[NS]/\d{5}[EW]', route):
            return True

        # Pattern 3: N/SDD.DD W/EDD.DD or similar decimal formats
        if re.search(r'[NS]\d+\.\d+[EW]\d+\.\d+', route):
            return True

        # Pattern 4: Simple coordinate pairs like "N40 W075"
        if re.search(r'[NS]\d+\s+[EW]\d+', route):
            return True

        # Check for G-airways (Pacific routes) which often cause errors
        # Example: G457, G345, etc.
        if re.search(r'\bG\d{3,4}\b', route):
            return True

        return False

    def _setup_difficulty_assignment(self, difficulty_config):
        """Setup difficulty assignment (copied from BaseScenario)"""
        if not difficulty_config:
            return None, 0

        difficulty_list = []
        difficulty_list.extend(['Easy'] * difficulty_config.get('easy', 0))
        difficulty_list.extend(['Medium'] * difficulty_config.get('medium', 0))
        difficulty_list.extend(['Hard'] * difficulty_config.get('hard', 0))

        random.shuffle(difficulty_list)

        return difficulty_list, 0

    def _assign_difficulty(self, aircraft, difficulty_list, difficulty_index):
        """Assign difficulty to aircraft (copied from BaseScenario)"""
        if difficulty_list and difficulty_index < len(difficulty_list):
            aircraft.difficulty = difficulty_list[difficulty_index]
            return difficulty_index + 1
        return difficulty_index

    def apply_spawn_delays(self, aircraft_list: List[Aircraft],
                          spawn_delay_mode: SpawnDelayMode,
                          delay_value: str = None,
                          total_session_minutes: int = None):
        """
        Apply spawn delays (simplified version from BaseScenario)
        """
        if spawn_delay_mode == SpawnDelayMode.NONE:
            for aircraft in aircraft_list:
                aircraft.spawn_delay = 0
        elif spawn_delay_mode == SpawnDelayMode.INCREMENTAL:
            if delay_value:
                # Parse delay value
                try:
                    delay_minutes = int(delay_value.split('-')[0])
                    delay_seconds = delay_minutes * 60

                    for i, aircraft in enumerate(aircraft_list):
                        aircraft.spawn_delay = i * delay_seconds
                except:
                    logger.warning(f"Invalid delay value: {delay_value}")
        elif spawn_delay_mode == SpawnDelayMode.TOTAL:
            if total_session_minutes:
                total_seconds = total_session_minutes * 60
                for aircraft in aircraft_list:
                    aircraft.spawn_delay = random.randint(0, total_seconds)
