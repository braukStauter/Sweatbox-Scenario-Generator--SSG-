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
from utils.data_pipeline import load_cifp_index

logger = logging.getLogger(__name__)


class _LazyCifpMap(dict):
    """Dict-like wrapper around `self.cifp_parsers` that lazily materializes a
    CIFPIndex for any airport on first access. Lets enroute code keep its
    ``self.cifp_parsers.get(icao)`` call pattern while actually loading
    procedure data (the bridge previously passed an empty dict, so every
    lookup silently returned None).
    """

    def get(self, icao, default=None):
        if not icao:
            return default
        if icao in self:
            return dict.__getitem__(self, icao)
        try:
            idx = load_cifp_index(icao)
            self[icao] = idx
            return idx
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Lazy CIFP load failed for {icao}: {exc}")
            return default

    def __getitem__(self, icao):
        val = self.get(icao)
        if val is None:
            raise KeyError(icao)
        return val


class _LazyGeoJSONMap(dict):
    """Parallel to _LazyCifpMap: lazy-loads `airport_data/{ICAO}.geojson`.

    Enroute departures need per-airport parking data. The bridge doesn't
    pre-build these parsers (the list of departure airports is a runtime
    config), so we load on demand keyed by ICAO. Falls back to stripping
    the leading `K` (the geojson files are named by 3-letter FAA code).
    """

    def get(self, icao, default=None):
        if not icao:
            return default
        if icao in self:
            return dict.__getitem__(self, icao)
        from parsers.geojson_parser import GeoJSONParser
        # Go through the bridge's resource_path helper so we pick up the
        # user-editable `<install>/resources/airport_data/` first and fall
        # back to the PyInstaller-baked copy second. Works identically in
        # dev mode (both paths resolve to the repo's airport_data).
        from ssg_bridge import resource_path
        candidates = [resource_path('airport_data', f"{icao}.geojson")]
        if icao.startswith('K') and len(icao) == 4:
            candidates.append(resource_path('airport_data', f"{icao[1:]}.geojson"))
        for path in candidates:
            if path.exists():
                try:
                    parser = GeoJSONParser(str(path))
                    self[icao] = parser
                    return parser
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to load GeoJSON for {icao}: {exc}")
                    return default
        logger.warning(f"No GeoJSON file for {icao}; enroute departures from this airport will be skipped")
        return default

    def __getitem__(self, icao):
        val = self.get(icao)
        if val is None:
            raise KeyError(icao)
        return val


class ArtccEnrouteScenario(BaseScenario):
    """Scenario for ARTCC enroute operations"""

    # Minimum remaining route distance (NM) a transient-enroute aircraft must
    # have inside the ARTCC from its spawn waypoint. Prevents spawning aircraft
    # 10 NM from the edge that immediately hand off and leave.
    MIN_REMAINING_IN_ARTCC_NM: float = 50.0
    # Default band (NM) outside ARTCC boundary where overflights spawn.
    DEFAULT_OVERFLIGHT_BAND_NM: Tuple[float, float] = (10.0, 25.0)
    # Default band (NM) from destination airport for arrival spawns.
    DEFAULT_ARRIVAL_BAND_NM: Tuple[float, float] = (80.0, 140.0)

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

        # Store airport-specific parsers. For the bridge path (Electron) we
        # don't prepopulate a parser dict — instead, cifp_parsers lazy-loads
        # each airport's CIFPIndex on first access (LRU-cached per process),
        # so runway-aware code paths keep working without an explicit
        # construction loop. Legacy PyQt callers pass pre-built dicts.
        self.geojson_parsers = _LazyGeoJSONMap(geojson_parsers or {})
        self.cifp_parsers = _LazyCifpMap(cifp_parsers or {})

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
                 num_overflight: int = 0,
                 arrival_airports: Optional[List[str]] = None,
                 departure_airports: Optional[List[str]] = None,
                 arrival_airport_runways: Optional[Dict[str, List[str]]] = None,
                 departure_airport_runways: Optional[Dict[str, List[str]]] = None,
                 per_airport_arrival_counts: Optional[Dict[str, int]] = None,
                 per_airport_departure_counts: Optional[Dict[str, int]] = None,
                 arrival_spawn_band: Optional[Tuple[float, float]] = None,
                 overflight_spawn_band: Optional[Tuple[float, float]] = None,
                 per_airport_arrival_bands: Optional[Dict[str, Tuple[float, float]]] = None,
                 enroute_min_remaining_nm: Optional[float] = None,
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
        # Per-airport quotas for enroute arrivals/departures (new UI). Keys
        # are K-prefixed ICAO codes; values are integer counts. If empty,
        # generator code falls back to proportional splitting of the
        # aggregate `num_arrivals`/`num_departures` across listed airports.
        self.per_airport_arrival_counts = {
            k.upper(): max(0, int(v or 0))
            for k, v in (per_airport_arrival_counts or {}).items()
        }
        self.per_airport_departure_counts = {
            k.upper(): max(0, int(v or 0))
            for k, v in (per_airport_departure_counts or {}).items()
        }

        # Spawn-band configuration (falls back to class defaults when None).
        self.arrival_spawn_band = tuple(arrival_spawn_band) if arrival_spawn_band else self.DEFAULT_ARRIVAL_BAND_NM
        self.overflight_spawn_band = tuple(overflight_spawn_band) if overflight_spawn_band else self.DEFAULT_OVERFLIGHT_BAND_NM
        self.per_airport_arrival_bands = {
            k.upper(): (float(v[0]), float(v[1]))
            for k, v in (per_airport_arrival_bands or {}).items()
            if isinstance(v, (list, tuple)) and len(v) == 2
        }
        self.enroute_min_remaining_nm = (
            float(enroute_min_remaining_nm)
            if enroute_min_remaining_nm is not None
            else self.MIN_REMAINING_IN_ARTCC_NM
        )

        logger.info(f"Generating ARTCC {self.artcc_id} scenario: {num_enroute} enroute, {num_arrivals} arrivals, {num_departures} departures")
        # Total targets exposed for flight_pool buffer math inside
        # _fetch_pool_* helpers (they size each per-airport call as
        # target // len(airports)).
        self._num_departures_total = num_departures
        self._num_arrivals_total = num_arrivals
        self._num_enroute_total = num_enroute

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

            if num_overflight > 0 and transient_pool:
                logger.info(f"Generating {num_overflight} overflight aircraft...")
                generation_futures['overflight'] = executor.submit(
                    self._generate_overflight_aircraft,
                    num_overflight, transient_pool, difficulty_config_enroute,
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
        from utils.data_pipeline import fetch_departures as pool_fetch_deps

        all_flights = []
        # Roughly split the overall departure count across the listed airports
        # so each airport's buffer is sized proportionally.
        per_airport = max(5, getattr(self, '_num_departures_total', 20) // max(1, len(departure_airports)))
        for airport in departure_airports:
            try:
                flights, _ = pool_fetch_deps(
                    self.api_client, airport, num_required=per_airport,
                )
                all_flights.extend(flights)
                logger.info(f"Fetched {len(flights)} departures from {airport}")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error fetching departures from {airport}: {e}")

        if not all_flights:
            logger.warning("No departures fetched for any airports")
            return []
        filtered = self._filter_pool(all_flights, "Departures")
        logger.info(f"Departures Pool: Fetched {len(all_flights)} total, filtered to {len(filtered)}")
        return filtered

    def _fetch_pool_arrivals(self, arrival_airports: List[str]) -> List[Dict]:
        """Fetch arrivals across the configured airports via FlightPool."""
        from utils.data_pipeline import fetch_arrivals as pool_fetch_arrs

        all_flights = []
        per_airport = max(5, getattr(self, '_num_arrivals_total', 20) // max(1, len(arrival_airports)))
        for airport in arrival_airports:
            try:
                flights, _ = pool_fetch_arrs(
                    self.api_client, airport, num_required=per_airport,
                )
                all_flights.extend(flights)
                logger.info(f"Fetched {len(flights)} arrivals to {airport}")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error fetching arrivals to {airport}: {e}")

        if not all_flights:
            logger.warning("No arrivals fetched for any airports")
            return []
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
            from utils.data_pipeline import fetch_artcc as pool_fetch_artcc
            flights, _ = pool_fetch_artcc(
                self.api_client, self.artcc_id,
                num_required=getattr(self, '_num_enroute_total', 20),
            )
            if not flights:
                logger.warning(f"No transient flights fetched for ARTCC {self.artcc_id}")
                return []

            # Filter for valid flights with complete data (double-pass safety)
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
        Filter flight pool: Validate flights have complete flight plans

        Args:
            flights: Raw flight data from API
            pool_name: Name of pool for logging

        Returns:
            Filtered list of valid flights
        """
        # API now only returns PROPOSED flights, no client-side status filtering needed
        # Apply standard validity filtering (checks for basic required fields)
        valid_flights = filter_valid_flights(flights)
        logger.debug(f"{pool_name}: {len(valid_flights)}/{len(flights)} passed validity checks")

        # Altitude is optional on every pool: the downstream aircraft factory
        # falls back to the aircraft type's cruise altitude when the API
        # record omits requestedAltitude/assignedAltitude (which, empirically,
        # is common for filed departure records at many airports).
        require_altitude = False

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

            # Procedure requirements are direction-specific. The earlier
            # version rejected every flight without BOTH procedures, which
            # killed the Departures pool to zero because filed flight plans
            # commonly carry only the SID at the origin end.
            require_dep_proc = pool_name == "Departures"
            require_arr_proc = pool_name == "Arrivals"
            if require_dep_proc and not dep_proc:
                missing_dep_proc += 1
                logger.debug(f"{pool_name}: Skipping {callsign} - missing departure procedure")
                continue
            if require_arr_proc and not arr_proc:
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
        """Generate arrival aircraft with per-airport quotas when configured."""
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        if not flight_pool:
            logger.warning("No flights in Arrivals Pool")
            return

        per_airport = getattr(self, 'per_airport_arrival_counts', {}) or {}
        # Only honor per-airport mode when at least one airport has a
        # non-zero quota. Otherwise fall back to the old "just hit `count`"
        # behavior for legacy configs.
        use_quotas = any(v > 0 for v in per_airport.values())
        remaining = dict(per_airport) if use_quotas else None
        target = sum(remaining.values()) if use_quotas else count

        created = 0
        attempts = 0
        max_attempts = target * 20

        while created < target and attempts < max_attempts and flight_pool:
            if use_quotas:
                # Pick only from flights whose destination still has quota.
                eligible = [
                    f for f in flight_pool
                    if remaining.get((f.get('arrivalAirport') or '').upper(), 0) > 0
                ]
                if not eligible:
                    logger.info("All per-airport arrival quotas filled")
                    break
                flight_data = random.choice(eligible)
            else:
                flight_data = random.choice(flight_pool)

            aircraft = self._create_arrival_aircraft(flight_data)
            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                if use_quotas:
                    dest = (flight_data.get('arrivalAirport') or '').upper()
                    if dest in remaining:
                        remaining[dest] = max(0, remaining[dest] - 1)
                created += 1

            attempts += 1

        if use_quotas:
            short = {a: n for a, n in remaining.items() if n > 0}
            logger.info(
                f"Created {created} arrival aircraft (per-airport quotas: "
                f"filled {target - sum(remaining.values())}/{target}"
                + (f", unfilled {short}" if short else "") + ")"
            )
        else:
            logger.info(f"Created {created} arrival aircraft (requested {target})")

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

        # Collect all parking spots from valid airports. If an airport's
        # geojson has no parking spots but does contain runway geometry, fall
        # back to spawning at the runway threshold (the active runways for
        # this airport, if configured).
        from models.airport import ParkingSpot

        all_parking_spots = []
        airport_parking_map = {}

        for airport_icao, geojson_parser in valid_airports.items():
            parking_spots = geojson_parser.get_parking_spots()
            logger.info(f"Found {len(parking_spots)} parking spots at {airport_icao}")

            if parking_spots:
                for spot in parking_spots:
                    all_parking_spots.append(spot)
                    airport_parking_map[spot.name] = airport_icao
                continue

            # Runway-threshold fallback.
            active_for_airport = (departure_airport_runways or {}).get(airport_icao) or []
            runways = geojson_parser.get_runways() or []
            synthesized = 0
            for runway in runways:
                try:
                    ends = runway.get_runway_ends()
                except Exception:  # noqa: BLE001
                    continue
                for end in ends:
                    clean_end = end.replace('RW', '').strip().upper()
                    if active_for_airport and clean_end not in [r.upper() for r in active_for_airport]:
                        continue
                    try:
                        lat, lon = runway.get_threshold_position(end)
                        heading = int(runway.get_runway_heading(end))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(f"Skipping runway end {end} at {airport_icao}: {exc}")
                        continue
                    fake_spot = ParkingSpot(
                        name=f"RW{clean_end}@{airport_icao}",
                        latitude=lat, longitude=lon, heading=heading,
                    )
                    all_parking_spots.append(fake_spot)
                    airport_parking_map[fake_spot.name] = airport_icao
                    synthesized += 1
            if synthesized:
                logger.info(
                    f"No parking data at {airport_icao}; synthesized {synthesized} "
                    f"runway-threshold spawn points"
                )

        if not all_parking_spots:
            logger.error("ERROR: No parking spots found in airport GeoJSON data")
            logger.error(f"Skipping {count} requested departure aircraft")
            return

        if count > len(all_parking_spots):
            logger.warning(f"Requested {count} departures but only {len(all_parking_spots)} parking spots available")
            count = len(all_parking_spots)

        # Shuffle parking spots for variety
        random.shuffle(all_parking_spots)

        # Per-airport quotas override the aggregate `count` when configured.
        per_airport = getattr(self, 'per_airport_departure_counts', {}) or {}
        use_quotas = any(v > 0 for v in per_airport.values())
        remaining = dict(per_airport) if use_quotas else None
        if use_quotas:
            count = sum(remaining.values())

        created = 0
        for spot in all_parking_spots:
            if created >= count:
                break

            # Get the airport for this parking spot
            airport_icao = airport_parking_map[spot.name]

            # Skip spots at airports whose quota is already filled.
            if use_quotas and remaining.get(airport_icao, 0) <= 0:
                continue

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
                if use_quotas:
                    remaining[airport_icao] = max(0, remaining[airport_icao] - 1)
                created += 1

        if use_quotas:
            short = {a: n for a, n in remaining.items() if n > 0}
            logger.info(
                f"Created {created} departure aircraft (per-airport quotas: "
                f"{count - sum(remaining.values())}/{count}"
                + (f", unfilled {short}" if short else "") + ")"
            )
        else:
            logger.info(f"Created {created} departure aircraft at parking spots (requested {count})")

    def _generate_overflight_aircraft(self, count: int, flight_pool: List[Dict],
                                       difficulty_config: Dict = None):
        """Generate overflight aircraft that enter the ARTCC from a neighbor.

        Shares the transient flight pool (any flight whose filed route crosses
        our airspace but whose destination is outside our configured arrival
        list). The spawn position is offset ~15 NM outside the ARTCC boundary
        on the reverse bearing from the first inside-ARTCC waypoint, with
        heading pointed AT that waypoint — so the aircraft appears to be
        handed off from the adjacent facility.
        """
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)
        if not flight_pool:
            logger.warning("No flights in pool for overflights")
            return

        created = 0
        attempts = 0
        max_attempts = count * 20

        while created < count and attempts < max_attempts and flight_pool:
            flight_data = random.choice(flight_pool)
            aircraft = self._create_overflight_aircraft(flight_data)
            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                created += 1
            attempts += 1

        logger.info(f"Created {created} overflight aircraft (requested {count})")

    def _find_overflight_spawn_on_route(self, route: str) -> Optional[Dict]:
        """Return a spawn state for an overflight: position offset between
        ``overflight_spawn_band`` NM outside the ARTCC boundary on the reverse
        bearing from the first waypoint that's inside the ARTCC.

        Returns dict matching `_find_spawn_waypoint_on_route`'s contract:
        `{waypoint, latitude, longitude, heading, initial_route}`.
        """
        from utils.geo_utils import calculate_bearing, calculate_destination

        waypoints = self.route_parser.parse_route_string(route)
        if not waypoints:
            return None
        route_coords = self.route_parser.get_route_waypoint_coordinates(waypoints)
        if len(route_coords) < 2:
            return None

        # Find the first waypoint that's inside the ARTCC — that's our
        # handoff/entry point.
        entry_idx = None
        for i, (wp_name, lat, lon) in enumerate(route_coords):
            if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
                entry_idx = i
                break
        if entry_idx is None:
            return None

        entry_name, entry_lat, entry_lon = route_coords[entry_idx]

        # Establish the "outbound from the boundary" bearing:
        # - If there's a waypoint upstream (outside ARTCC), use its bearing
        #   to the entry waypoint — that's the actual approach direction.
        # - Otherwise fall back to the bearing FROM the NEXT in-ARTCC waypoint
        #   TO the entry, which still points roughly into our airspace.
        if entry_idx > 0:
            up_name, up_lat, up_lon = route_coords[entry_idx - 1]
            inbound_heading = calculate_bearing(up_lat, up_lon, entry_lat, entry_lon)
        elif entry_idx + 1 < len(route_coords):
            nxt_name, nxt_lat, nxt_lon = route_coords[entry_idx + 1]
            inbound_heading = calculate_bearing(entry_lat, entry_lon, nxt_lat, nxt_lon)
        else:
            return None

        # Sanity check: the inbound heading should actually point toward the
        # flight's downstream waypoints. If the filed route has at least one
        # more in-ARTCC waypoint, the bearing from entry to that waypoint
        # should be within 90° of the inbound_heading — otherwise we've
        # resolved waypoints out of order and would spawn the aircraft
        # pointing the wrong way.
        if entry_idx + 1 < len(route_coords):
            _, dn_lat, dn_lon = route_coords[entry_idx + 1]
            downstream_bearing = calculate_bearing(entry_lat, entry_lon, dn_lat, dn_lon)
            if abs((inbound_heading - downstream_bearing + 540) % 360 - 180) > 90:
                logger.debug(
                    f"Overflight entry heading {inbound_heading} conflicts with "
                    f"downstream bearing {downstream_bearing}; rejecting to avoid "
                    f"opposite-direction spawn"
                )
                return None

        # Place the aircraft in a configurable band BEHIND the entry waypoint
        # on the reverse bearing, still pointed AT the entry (matches what
        # the adjacent facility would see on their scope just before handoff).
        min_nm, max_nm = getattr(self, 'overflight_spawn_band', (10.0, 25.0))
        offset_nm = random.uniform(min_nm, max_nm) if max_nm > min_nm else min_nm
        reverse_bearing = (inbound_heading + 180) % 360
        spawn_lat, spawn_lon = calculate_destination(entry_lat, entry_lon, reverse_bearing, offset_nm)

        # Initial navigation: target the entry waypoint, then the rest of
        # the route. Start the initial_route at the entry waypoint.
        remainder = ' '.join(wp for wp, _, _ in route_coords[entry_idx:])
        return {
            'waypoint': entry_name,
            'latitude': spawn_lat,
            'longitude': spawn_lon,
            'heading': int(inbound_heading),
            'initial_route': remainder,
        }

    def _create_overflight_aircraft(self, flight_data: Dict) -> Optional[Aircraft]:
        """Build a single overflight aircraft. Same API-data plumbing as
        `_create_enroute_aircraft` but spawns at the boundary-entry position.
        """
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')
        departure = flight_data.get('departureAirport', 'KORD')
        arrival = flight_data.get('arrivalAirport', 'KLAX')

        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        clean_route = clean_route_string(filed_route)
        spawn_info = self._find_overflight_spawn_on_route(clean_route)
        if not spawn_info:
            logger.debug(f"No ARTCC boundary-entry found for {callsign}; skipping overflight")
            with self.callsign_lock:
                self.used_callsigns.discard(callsign)
            return None

        # Let two overflights share an entry waypoint (they're offset 15 NM
        # apart along the airway already); only dedupe if the exact lat/lon
        # pair collides. Key by rounded position.
        spawn_key = f"OVF:{round(spawn_info['latitude'], 3)},{round(spawn_info['longitude'], 3)}"
        with self.spawn_point_lock:
            if spawn_key in self.used_spawn_points:
                with self.callsign_lock:
                    self.used_callsigns.discard(callsign)
                return None
            self.used_spawn_points.add(spawn_key)

        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            try:
                altitude = int(float(requested_alt))
            except (ValueError, TypeError):
                altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        else:
            altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        cruise_altitude = str(altitude)

        cruise_kias, ground_speed, mach_value = self._derive_airborne_speed(
            flight_data, aircraft_type, altitude, on_star=False,
        )

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=spawn_info['latitude'],
            longitude=spawn_info['longitude'],
            altitude=altitude,
            heading=int(spawn_info['heading']),
            ground_speed=ground_speed,
            # Spawn at a bare lat/lon (no fix) — the aircraft isn't yet over
            # the entry waypoint, it's outside the boundary. vNAS handles
            # FixOrFrd spawns or we leave starting_conditions_type default.
            starting_conditions_type='FixOrFrd',
            fix=spawn_info['waypoint'],
            departure=departure,
            arrival=arrival,
            route=clean_route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_kias,
            mach=mach_value,
            flight_rules="I",
            primary_airport=None,
            spawn_delay=0,
        )
        return aircraft

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

        cruise_kias, ground_speed, mach_value = self._derive_airborne_speed(
            flight_data, aircraft_type, altitude, on_star=False,
        )

        # Navigation path: next waypoint after spawn, followed by remainder of filed route
        initial_route = spawn_info.get('initial_route', clean_route)

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
            cruise_speed=cruise_kias,
            mach=mach_value,
            flight_rules="I",
            primary_airport=None,
            spawn_delay=0
        )

        return aircraft

    def _create_arrival_aircraft(self, flight_data: Dict) -> Optional[Aircraft]:
        """Create arrival aircraft spawned inside ARTCC at a distance-from-
        destination band. Prefers real waypoints on the filed route or STAR;
        synthesizes an FRD-style point along the route leg if the band falls
        between named waypoints."""
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')
        departure = flight_data.get('departureAirport', 'KORD')
        arrival = flight_data.get('arrivalAirport', 'KPHX')
        arr_proc = flight_data.get('arrivalProcedure', '')

        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        # Per-airport band overrides the scenario-wide default.
        scenario_band = getattr(self, 'arrival_spawn_band',
                                self.DEFAULT_ARRIVAL_BAND_NM)
        per_airport_bands = getattr(self, 'per_airport_arrival_bands', {}) or {}
        min_nm, max_nm = per_airport_bands.get(arrival.upper(), scenario_band)

        spawn = self._find_arrival_spawn_on_route(filed_route, arrival, arr_proc,
                                                   min_nm, max_nm)
        if not spawn:
            logger.debug(f"No arrival spawn in [{min_nm},{max_nm}] NM from {arrival} for {callsign}")
            with self.callsign_lock:
                self.used_callsigns.discard(callsign)
            return None

        # Use the CIFP-resolved STAR name for downstream procedure strings.
        actual_star_name = spawn.get('actual_star_name') or arr_proc
        arr_proc = actual_star_name or arr_proc

        # Dedupe on rounded (lat,lon) so two aircraft can share a generic fix
        # so long as they aren't literally on top of each other (FRD points
        # at the same band midpoint on the same route would collide).
        spawn_key = f"ARR:{spawn['fix']}:{round(spawn['latitude'], 3)},{round(spawn['longitude'], 3)}"
        with self.spawn_point_lock:
            if spawn_key in self.used_spawn_points:
                logger.debug(f"Spawn point {spawn_key} already in use, skipping {callsign}")
                with self.callsign_lock:
                    self.used_callsigns.discard(callsign)
                return None
            self.used_spawn_points.add(spawn_key)

        # Altitude priority:
        # 1. CIFP altitude constraint at the chosen STAR waypoint (the
        #    published crossing altitude — always authoritative when present).
        # 2. Rule-of-3s profile from spawn distance-to-destination, capped at
        #    the type's typical cruise. This covers both FRD spawns on the
        #    filed route and un-constrained STAR waypoints, and keeps aircraft
        #    at sensible descending altitudes as they approach the field.
        star_wp_obj = spawn.get('star_waypoint_obj')
        dist_to_dest = spawn.get('distance_to_dest_nm')
        if star_wp_obj is not None and (star_wp_obj.max_altitude or star_wp_obj.min_altitude):
            altitude = self._get_altitude_from_cifp(star_wp_obj, arr_proc, departure, arrival, aircraft_type)
        elif dist_to_dest is not None:
            altitude = self._rule_of_3s_altitude(dist_to_dest, aircraft_type)
        else:
            altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        cruise_altitude = str(altitude)

        on_star = bool(spawn.get('on_star'))
        cruise_kias, ground_speed, mach_value = self._derive_airborne_speed(
            flight_data, aircraft_type, altitude, on_star=on_star,
        )

        # Extract 3-letter airport code from ICAO (e.g., KPHX -> PHX)
        arrival_3letter = arrival[1:] if arrival.startswith('K') else arrival[-3:]

        # Runway assignment unchanged.
        arrival_runway = None
        if arr_proc and arrival in self.arrival_airport_runways:
            active_runways = self.arrival_airport_runways[arrival]
            arrival_runway = self._get_runway_for_star(arrival, arr_proc, active_runways)

        # Navigation path: next waypoint (if spawn was on STAR, the next STAR
        # waypoint; otherwise the STAR itself) + procedure + runway suffix.
        navigation_path = self._build_arrival_navigation_path(
            arrival, arr_proc, arrival_runway, spawn,
        )

        clean_route = clean_route_string(filed_route)

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=spawn['latitude'],
            longitude=spawn['longitude'],
            altitude=altitude,
            heading=int(spawn['heading']),
            ground_speed=ground_speed,
            starting_conditions_type=spawn['starting_conditions_type'],
            fix=spawn['fix'],
            departure=departure,
            arrival=arrival,
            route=clean_route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_kias,
            mach=mach_value,
            navigation_path=navigation_path,
            arrival_runway=arrival_runway,
            star=arr_proc,
            flight_rules="I",
            primary_airport=arrival_3letter,
            spawn_delay=0,
        )
        return aircraft

    def _build_arrival_navigation_path(self, arrival_icao: str, star_name: str,
                                        arrival_runway: Optional[str],
                                        spawn: Dict) -> str:
        """Compose the vNAS navigation path for an arrival."""
        cifp_parser = self.cifp_parsers.get(arrival_icao)
        star_waypoints_list = (
            cifp_parser.get_arrival_waypoints(star_name) if (cifp_parser and star_name) else []
        )
        next_fix_name = spawn['fix']
        if spawn.get('on_star') and star_waypoints_list:
            for idx, wp_name in enumerate(star_waypoints_list):
                if wp_name.upper() == spawn['fix'].upper():
                    if idx + 1 < len(star_waypoints_list):
                        next_fix_name = star_waypoints_list[idx + 1]
                    break
        if star_name and arrival_runway:
            runway_suffix = arrival_runway.replace('RW', '')
            return f"{next_fix_name} {star_name}.{runway_suffix}"
        if star_name:
            return f"{next_fix_name} {star_name}"
        return f"{next_fix_name} {arrival_icao}"

    def _derive_airborne_speed(self, flight_data: Dict, aircraft_type: str,
                                altitude_ft: int, on_star: bool):
        """Return ``(cruise_kias, ground_speed, mach_or_none)`` for an airborne
        aircraft. Filed KIAS comes from the API when available, else from the
        type lookup. Above FL200 and not on a STAR we set cruise Mach and
        derive ground speed from it; otherwise ground speed is estimated from
        KIAS + altitude."""
        from utils.speed_estimator import (
            cruise_mach, ground_speed_from_mach, ground_speed_from_kias,
            indicated_cruise_kias,
        )
        filed_speed = flight_data.get('requestedAirspeed')
        try:
            cruise_kias = int(float(filed_speed)) if filed_speed else indicated_cruise_kias(aircraft_type)
        except (TypeError, ValueError):
            cruise_kias = indicated_cruise_kias(aircraft_type)

        use_mach = (altitude_ft >= 20000) and not on_star
        if use_mach:
            mach_value = cruise_mach(aircraft_type)
            ground_speed = ground_speed_from_mach(mach_value, altitude_ft)
            return cruise_kias, ground_speed, round(mach_value, 2)
        ground_speed = ground_speed_from_kias(cruise_kias, altitude_ft)
        return cruise_kias, ground_speed, None

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

        # The filter relaxed the altitude/speed requirement (many filed plans
        # omit these fields), so fall back to the aircraft-type defaults when
        # the API didn't supply a value.
        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            try:
                cruise_altitude = str(int(float(requested_alt)))
            except (ValueError, TypeError):
                cruise_altitude = '35000'
        else:
            cruise_altitude = '35000'  # sensible jet cruise default

        filed_speed = flight_data.get('requestedAirspeed')
        if filed_speed:
            try:
                cruise_speed = int(float(filed_speed))
            except (ValueError, TypeError):
                cruise_speed = self.api_client._calculate_cruise_speed(aircraft_type)
        else:
            cruise_speed = self.api_client._calculate_cruise_speed(aircraft_type)

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
            primary_airport=None,
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
        # For enroute, prefer a randomly-chosen *unused* waypoint so that two
        # transient aircraft on the same airway don't both claim the same fix
        # (which caused the earlier "Spawn point X already in use, skipping"
        # warnings and reduced the generated-count).
        if is_arrival:
            selected_idx, wp_name, lat, lon = waypoints_in_artcc[0]
            logger.debug(f"Selected first waypoint within ARTCC: {wp_name} at index {selected_idx}")
        else:
            from utils.geo_utils import route_remaining_inside_artcc
            shuffled = list(waypoints_in_artcc)
            random.shuffle(shuffled)
            used = getattr(self, 'used_spawn_points', set())
            unused = [w for w in shuffled if w[1] not in used]
            candidates = unused if unused else shuffled
            # Filter to candidates that have enough remaining route inside the
            # ARTCC — a transient aircraft that crosses our boundary within
            # a few miles of spawn is useless as a training target.
            min_remaining = getattr(self, 'enroute_min_remaining_nm',
                                     self.MIN_REMAINING_IN_ARTCC_NM)
            latlon_coords = [(lat_, lon_) for _, _, lat_, lon_ in route_coords]
            deep_candidates = []
            for cand in candidates:
                idx_ = cand[0]
                remaining_nm = route_remaining_inside_artcc(
                    latlon_coords, idx_, self.artcc_id,
                    self.artcc_boundaries,
                )
                if remaining_nm >= min_remaining:
                    deep_candidates.append(cand)
            if not deep_candidates:
                logger.debug(
                    f"No transient spawn candidates with >={min_remaining} NM "
                    f"remaining inside ARTCC {self.artcc_id}; skipping this flight"
                )
                return None
            # Pick the first candidate whose next-waypoint bearing points
            # roughly toward the end of the filed route. This catches
            # waypoint-db mismatches that would otherwise spawn the aircraft
            # pointing backwards along its filed route.
            from utils.geo_utils import calculate_bearing as _cb
            last_lat, last_lon = route_coords[-1][1], route_coords[-1][2]
            selected = None
            for cand in deep_candidates:
                idx_, name_, lat_, lon_ = cand
                if idx_ + 1 >= len(route_coords):
                    continue
                nx_lat, nx_lon = route_coords[idx_ + 1][1], route_coords[idx_ + 1][2]
                nx_bearing = _cb(lat_, lon_, nx_lat, nx_lon)
                dest_bearing = _cb(lat_, lon_, last_lat, last_lon)
                if abs((nx_bearing - dest_bearing + 540) % 360 - 180) <= 90:
                    selected = cand
                    break
            if selected is None:
                selected = deep_candidates[0]
            selected_idx, wp_name, lat, lon = selected

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

    def _rule_of_3s_altitude(self, distance_to_dest_nm: float,
                              aircraft_type: str, field_elevation_ft: int = 1000) -> int:
        """Standard 3-to-1 descent profile: 3 NM per 1,000 ft of descent.

        Returns a sensible pre-descent altitude for an arrival spawned
        ``distance_to_dest_nm`` away from the field. Clamps to the type's
        typical cruise so a 600 NM spawn doesn't end up at FL180 (you'd still
        be at cruise that far out).
        """
        nm = max(0.0, float(distance_to_dest_nm))
        # descent_ft ≈ NM * 1000 / 3. Round to the nearest 1,000 so the strip
        # shows a whole flight level. Add a small field-elevation cushion so
        # the aircraft doesn't spawn below the destination's pattern altitude.
        raw_ft = int(round((nm * 1000.0 / 3.0) / 1000.0)) * 1000 + field_elevation_ft
        cruise_cap = self._estimate_cruise_altitude('', '', aircraft_type)
        return max(3000, min(raw_ft, cruise_cap))

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

    def _find_boundary_entry_spawn(self, nodes: List[Tuple],
                                     anchor_lat: float, anchor_lon: float,
                                     matching_star: Optional[str]) -> Optional[Dict]:
        """Safety fallback for arrivals whose requested band falls entirely
        outside our ARTCC: spawn the aircraft just outside the boundary on
        the reverse bearing from where the filed route first enters our
        airspace, pointed inbound at that entry waypoint — same handoff
        geometry as an overflight.

        Keeps the arrival on its filed route and procedure rather than
        dropping it; the controller sees it check in from the adjacent
        facility instead of teleporting to a named fix inside the sector.
        """
        from utils.geo_utils import (
            calculate_bearing, calculate_destination, calculate_distance_nm,
        )

        # Find the first node inside the ARTCC — that's the route's entry.
        entry_idx = None
        for i, (_, lat, lon, _, _) in enumerate(nodes):
            if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
                entry_idx = i
                break
        if entry_idx is None:
            # Route never enters our airspace — nothing we can do.
            return None

        entry_name, entry_lat, entry_lon, entry_is_star, entry_wp_obj = nodes[entry_idx]

        # Establish the inbound bearing the same way overflights do.
        if entry_idx > 0:
            _, up_lat, up_lon, _, _ = nodes[entry_idx - 1]
            inbound_heading = calculate_bearing(up_lat, up_lon, entry_lat, entry_lon)
        elif entry_idx + 1 < len(nodes):
            _, nx_lat, nx_lon, _, _ = nodes[entry_idx + 1]
            inbound_heading = calculate_bearing(entry_lat, entry_lon, nx_lat, nx_lon)
        else:
            return None

        # Offset outside the boundary. Reuse the overflight band so the UI
        # knob controls both handoff geometries; clamp the min to a small
        # positive value so we always end up outside the polygon.
        min_nm, max_nm = getattr(self, 'overflight_spawn_band',
                                  self.DEFAULT_OVERFLIGHT_BAND_NM)
        offset_nm = random.uniform(min_nm, max_nm) if max_nm > min_nm else min_nm
        reverse_bearing = (inbound_heading + 180) % 360
        spawn_lat, spawn_lon = calculate_destination(
            entry_lat, entry_lon, reverse_bearing, offset_nm,
        )
        # Verify we actually ended up outside — for odd-shaped ARTCCs the
        # reverse-bearing offset can still land inside a lobe of the polygon.
        tries = 0
        while (self.artcc_boundaries.is_point_in_artcc(spawn_lat, spawn_lon, self.artcc_id)
                and tries < 4):
            offset_nm += 10
            spawn_lat, spawn_lon = calculate_destination(
                entry_lat, entry_lon, reverse_bearing, offset_nm,
            )
            tries += 1

        distance_to_dest = calculate_distance_nm(
            spawn_lat, spawn_lon, anchor_lat, anchor_lon,
        )

        return {
            'fix': entry_name,
            'latitude': spawn_lat,
            'longitude': spawn_lon,
            'heading': int(inbound_heading),
            'starting_conditions_type': 'FixOrFrd',
            # Boundary-entry spawns are always pre-STAR from our sector's
            # point of view even if the entry waypoint happens to be on the
            # STAR, so Mach dispatch still applies until the aircraft reaches
            # STAR territory.
            'on_star': False,
            'actual_star_name': matching_star,
            'star_waypoint_obj': None,
            'node_index': entry_idx,
            'distance_to_dest_nm': distance_to_dest,
            'boundary_entry': True,
        }

    def _find_arrival_spawn_on_route(self, filed_route: str, arrival_icao: str,
                                      star_name: str,
                                      min_nm: float, max_nm: float) -> Optional[Dict]:
        """Pick an arrival spawn point whose straight-line distance from the
        arrival airport falls in [min_nm, max_nm].

        Strategy:
        1. Build a forward polyline: cleaned filed-route waypoints + CIFP STAR
           waypoints (de-duplicated at the seam).
        2. Tag each node with distance-to-destination using the airport's
           reported center and the existing haversine helper.
        3. Prefer a *named* in-ARTCC node whose dist-to-dest is in the band.
        4. If none match, interpolate a synthetic FRD-style point along the
           leg that crosses the band (prefer the midpoint of the band that
           still falls inside the ARTCC).
        5. If nothing in the band is inside the ARTCC, return None — caller
           will try a different flight.

        Returns a dict with keys the arrival creator already expects:
        ``{fix, latitude, longitude, heading, starting_conditions_type,
           actual_star_name, star_waypoint_obj, on_star}``. ``on_star`` flags
        whether the chosen spawn falls on a STAR waypoint (used by the speed
        logic to decide whether Mach is appropriate).
        """
        from utils.geo_utils import (
            calculate_bearing, calculate_distance_nm, interpolate_along_path,
        )

        cifp_parser = self.cifp_parsers.get(arrival_icao)
        if not cifp_parser:
            return None

        # 1a. Clean filed route → named waypoints with coords.
        clean = clean_route_string(filed_route)
        filed_names = self.route_parser.parse_route_string(clean)
        filed_coords = self.route_parser.get_route_waypoint_coordinates(filed_names)

        # 1b. Resolve the STAR name via the same base-match the old code used.
        available_stars = cifp_parser.get_available_stars()
        star_base = re.sub(r'\d+$', '', (star_name or '').upper())
        matching_star = None
        for s in available_stars:
            if re.sub(r'\d+$', '', s.upper()) == star_base:
                matching_star = s
                break
        star_nodes: List[Tuple[str, float, float, object]] = []
        if matching_star:
            for wp_name in cifp_parser.get_arrival_waypoints(matching_star) or []:
                wp_obj = cifp_parser.get_transition_waypoint(wp_name, matching_star)
                if wp_obj and wp_obj.latitude and wp_obj.longitude:
                    star_nodes.append((wp_name, wp_obj.latitude, wp_obj.longitude, wp_obj))

        # 1c. Build the full forward polyline. Seam-dedupe: if the last filed
        # waypoint equals the first STAR waypoint, drop the duplicate.
        # Each node: (name, lat, lon, is_star, wp_obj_or_None).
        nodes: List[Tuple[str, float, float, bool, object]] = []
        for name, lat, lon in filed_coords:
            nodes.append((name, lat, lon, False, None))
        if star_nodes:
            start_idx = 0
            if nodes and nodes[-1][0].upper() == star_nodes[0][0].upper():
                # Replace the seam node with the STAR-tagged version so we
                # don't double-count it.
                nodes[-1] = (star_nodes[0][0], star_nodes[0][1], star_nodes[0][2], True, star_nodes[0][3])
                start_idx = 1
            for wp_name, lat, lon, wp_obj in star_nodes[start_idx:]:
                nodes.append((wp_name, lat, lon, True, wp_obj))

        if len(nodes) < 2:
            return None

        # 2. Distance to destination for each node. Use the last STAR waypoint
        # as the dest anchor if we have one; otherwise fall back to the last
        # route node. (Arrival airport ICAO → lat/lon lookup isn't always
        # reliable for the waypoint database.)
        anchor_lat, anchor_lon = nodes[-1][1], nodes[-1][2]
        dist_to_dest = [
            calculate_distance_nm(lat, lon, anchor_lat, anchor_lon)
            for _, lat, lon, _, _ in nodes
        ]

        # 3. Named-node path in band, inside ARTCC.
        in_band_named: List[Tuple[int, float]] = [
            (i, dist_to_dest[i])
            for i in range(len(nodes))
            if min_nm <= dist_to_dest[i] <= max_nm
            and self.artcc_boundaries.is_point_in_artcc(
                nodes[i][1], nodes[i][2], self.artcc_id
            )
        ]

        def _downstream_heading(idx: int, fallback_obj=None) -> Optional[int]:
            """Bearing from node[idx] to the next distinct-position node that's
            closer to the destination anchor. Returns None when no valid
            downstream node exists — the caller must then reject this
            candidate rather than spawning with a guessed heading."""
            for j in range(idx + 1, len(nodes)):
                lat_a, lon_a = nodes[idx][1], nodes[idx][2]
                lat_b, lon_b = nodes[j][1], nodes[j][2]
                # Skip duplicate / zero-length legs.
                if abs(lat_a - lat_b) < 1e-6 and abs(lon_a - lon_b) < 1e-6:
                    continue
                # Downstream means the next node is closer to destination
                # than current. Rejecting same-or-farther nodes filters out
                # malformed or reversed route segments (the "opposite
                # direction on the arrival" bug reported by users).
                if dist_to_dest[j] >= dist_to_dest[idx] - 0.5:
                    continue
                return int(calculate_bearing(lat_a, lon_a, lat_b, lon_b))
            # Last-resort: use CIFP inbound course only if it points roughly
            # toward the destination anchor.
            if fallback_obj is not None and getattr(fallback_obj, 'inbound_course', None):
                hdg = int(fallback_obj.inbound_course) % 360
                anchor_bearing = int(calculate_bearing(
                    nodes[idx][1], nodes[idx][2], anchor_lat, anchor_lon
                ))
                diff = abs((hdg - anchor_bearing + 540) % 360 - 180)
                if diff <= 90:
                    return hdg
            return None

        if in_band_named:
            # Prefer a named node closest to the band midpoint, tiebreak to
            # the deepest (farthest-from-airport) one so aircraft start with
            # more time in the sector when multiple waypoints cluster.
            midpoint = 0.5 * (min_nm + max_nm)
            in_band_named.sort(key=lambda t: (abs(t[1] - midpoint), -t[1]))
            for candidate_idx, dist_dest in in_band_named:
                name, lat, lon, is_star, wp_obj = nodes[candidate_idx]
                hdg = _downstream_heading(candidate_idx, wp_obj)
                if hdg is None:
                    continue
                return {
                    'fix': name,
                    'latitude': lat,
                    'longitude': lon,
                    'heading': hdg,
                    'starting_conditions_type': 'Fix',
                    'on_star': is_star,
                    'actual_star_name': matching_star,
                    'star_waypoint_obj': wp_obj if is_star else None,
                    'node_index': candidate_idx,
                    'distance_to_dest_nm': dist_dest,
                }

        # 4. Interpolate along the polyline at the band midpoint, measured
        # from the destination. We want `target_from_dest` NM back from the
        # anchor. Convert to forward distance along the polyline.
        polyline = [(lat, lon) for _, lat, lon, _, _ in nodes]
        total_len = sum(
            calculate_distance_nm(polyline[i][0], polyline[i][1],
                                   polyline[i + 1][0], polyline[i + 1][1])
            for i in range(len(polyline) - 1)
        )
        target_from_dest = 0.5 * (min_nm + max_nm)
        target_forward = total_len - target_from_dest
        if target_forward <= 0 or target_forward >= total_len:
            # Band is longer than the whole filed route (or inverted) — hand
            # off at the ARTCC boundary instead of silently dropping.
            return self._find_boundary_entry_spawn(nodes, anchor_lat, anchor_lon, matching_star)
        interp = interpolate_along_path(polyline, target_forward)
        if not interp:
            return self._find_boundary_entry_spawn(nodes, anchor_lat, anchor_lon, matching_star)
        synth_lat, synth_lon, heading = interp
        if not self.artcc_boundaries.is_point_in_artcc(
                synth_lat, synth_lon, self.artcc_id):
            # Band falls entirely outside our airspace — hand off from the
            # adjacent facility instead of skipping the aircraft.
            return self._find_boundary_entry_spawn(nodes, anchor_lat, anchor_lon, matching_star)
        # Sanity check: interpolated heading must point toward the anchor
        # (destination). If the route doubles back, the leg bearing can
        # actually point away from the dest — reject rather than produce a
        # wrong-direction spawn.
        anchor_bearing = calculate_bearing(synth_lat, synth_lon, anchor_lat, anchor_lon)
        if abs((heading - anchor_bearing + 540) % 360 - 180) > 90:
            return self._find_boundary_entry_spawn(nodes, anchor_lat, anchor_lon, matching_star)
        # Pin the synthetic fix to the nearest upstream *named* waypoint so
        # vNAS can render an FRD string from it.
        upstream_name = None
        cum = 0.0
        for i in range(len(polyline) - 1):
            leg = calculate_distance_nm(polyline[i][0], polyline[i][1],
                                         polyline[i + 1][0], polyline[i + 1][1])
            if cum + leg >= target_forward:
                upstream_name = nodes[i][0]
                break
            cum += leg
        # Great-circle distance from the synthesized point to the anchor.
        synth_dist_to_dest = calculate_distance_nm(
            synth_lat, synth_lon, anchor_lat, anchor_lon,
        )
        return {
            'fix': upstream_name or nodes[0][0],
            'latitude': synth_lat,
            'longitude': synth_lon,
            'heading': heading,
            'starting_conditions_type': 'FixOrFrd',
            'on_star': False,
            'actual_star_name': matching_star,
            'star_waypoint_obj': None,
            'node_index': None,
            'distance_to_dest_nm': synth_dist_to_dest,
        }

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

    # Enroute now inherits apply_spawn_delays from BaseScenario so all
    # scenarios share the stratified-realistic TOTAL mode and the proper
    # min-max range handling for INCREMENTAL mode.
