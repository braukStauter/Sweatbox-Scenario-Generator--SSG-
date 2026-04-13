"""
Base scenario class
"""
import random
import logging
import json
import threading
from typing import List, Dict, Tuple, Optional
from abc import ABC, abstractmethod
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from parsers.geojson_parser import GeoJSONParser
# NOTE: scenarios accept either parsers.CIFPParser or utils.data_pipeline.CIFPIndex
# (duck-typed). The legacy PyQt GUI still instantiates CIFPParser directly; the
# Electron bridge uses CIFPIndex for per-process caching + the runway fix.
from utils.api_client import FlightDataAPIClient
from utils.constants import POPULAR_US_AIRPORTS, LESS_COMMON_AIRPORTS, COMMON_JETS, COMMON_GA_AIRCRAFT
from utils.flight_data_filter import (
    filter_valid_flights, categorize_flights, filter_by_parking_airline, is_ga_aircraft,
    get_airline_from_callsign, clean_route_string
)
from utils.data_pipeline import (
    matches_any,
    strip_suffix,
    format_procedures_param,
    WakeBudget,
    WAKE_CATEGORIES,
    bucket_by_wake,
    normalize_category,
    to_icao,
    dedupe_by_gufi,
)
# Back-compat alias for the leading-underscore form used inside this module.
_normalize_category = normalize_category

logger = logging.getLogger(__name__)


class BaseScenario(ABC):
    """Base class for all scenario types"""

    def __init__(self, airport_icao: str, geojson_parser: GeoJSONParser,
                 cifp_parser, api_client: FlightDataAPIClient,
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
        self.cifp_waypoint_errors: List[str] = []  # Track CIFP/waypoint errors for user notification
        self.gate_assignment_warnings: List[str] = []  # Track gate assignment mismatches for user notification
        self.config = self._load_config()

        self.cached_flights = cached_flights or {'departures': [], 'arrivals': []}
        self.departure_flight_pool = []
        self.current_sids = None

        # Wake-category budgets (populated by bridge before generate()).
        self.dep_wake_budget: Optional[WakeBudget] = None
        self.arr_wake_budget: Optional[WakeBudget] = None

        self.callsign_lock = threading.Lock()
        self.parking_lock = threading.Lock()
        self.aircraft_lock = threading.Lock()

    def set_wake_budgets(self, dep_counts: Dict[str, int], arr_counts: Dict[str, int]) -> None:
        """Install per-category target counts for departures and arrivals.

        Called by the bridge after scenario construction. Budgets are consumed
        as flights are picked; short categories backfill from whichever bucket
        still has supply (see WakeBudget for backfill accounting).
        """
        self.dep_wake_budget = WakeBudget.from_counts(dep_counts or {})
        self.arr_wake_budget = WakeBudget.from_counts(arr_counts or {})

    def set_ga_config(self, ga_config: Optional[Dict]) -> None:
        """Install the GA config block from the bridge.

        Expected shape: {
            enabled: bool,
            departures: {count: int, mode: 'VFR'|'IFR'},
            arrivals:   {count: int, mode: 'VFR'|'IFR'},
        }

        When `enabled` is False (the default), GA-tagged parking spots are
        skipped entirely and no synthetic GA arrivals are injected. When
        True, the per-direction count caps how many GA aircraft are placed;
        additional GA spots beyond the count are skipped (no airline
        aircraft placed on them).
        """
        self.ga_config = ga_config or {'enabled': False}
        self.ga_dep_consumed = 0
        self.ga_arr_consumed = 0
        self.ga_used_gufis: set = set()

    def _consume_ga_spot_for_departure(self) -> Optional[str]:
        """Return 'VFR'/'IFR' if this GA spot should be filled, or None to skip."""
        ga = getattr(self, 'ga_config', None) or {}
        if not ga.get('enabled'):
            return None
        dep = ga.get('departures') or {}
        count = int(dep.get('count') or 0)
        if getattr(self, 'ga_dep_consumed', 0) >= count:
            return None
        self.ga_dep_consumed = getattr(self, 'ga_dep_consumed', 0) + 1
        return dep.get('mode', 'VFR')

    def _ga_arrival_budget(self) -> int:
        """Number of GA arrival aircraft remaining to spawn."""
        ga = getattr(self, 'ga_config', None) or {}
        if not ga.get('enabled'):
            return 0
        arr = ga.get('arrivals') or {}
        total = int(arr.get('count') or 0)
        return max(0, total - getattr(self, 'ga_arr_consumed', 0))

    def _ga_arrival_mode(self) -> str:
        ga = getattr(self, 'ga_config', None) or {}
        arr = ga.get('arrivals') or {}
        return arr.get('mode', 'VFR')

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
        self.cifp_waypoint_errors.clear()
        self.gate_assignment_warnings.clear()
        self.gate_failure_reasons = {}  # Track why each gate failed

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

        difficulty_list = []
        difficulty_list.extend(['Easy'] * difficulty_config['easy'])
        difficulty_list.extend(['Medium'] * difficulty_config['medium'])
        difficulty_list.extend(['Hard'] * difficulty_config['hard'])

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
        if self.cifp_parser:
            runways = self.cifp_parser.get_runways_for_arrival(arrival_name)
        else:
            runways_objs = self.geojson_parser.get_runways()
            runways = []
            for runway in runways_objs:
                if hasattr(runway, 'runway1_name'):
                    runways.append(runway.runway1_name)
                if hasattr(runway, 'runway2_name'):
                    runways.append(runway.runway2_name)

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
        min_delay_minutes, max_delay_minutes = 0, 0
        if spawn_delay_range:
            try:
                parts = spawn_delay_range.split('-')
                if len(parts) == 2:
                    min_delay_minutes = int(parts[0])
                    max_delay_minutes = int(parts[1])
            except ValueError:
                logger.warning(f"Invalid spawn delay range: {spawn_delay_range}, using default (0-0)")

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
            for aircraft in aircraft_list:
                aircraft.spawn_delay = 0
            logger.info(f"Applied NONE spawn delays: all {len(aircraft_list)} aircraft spawn at 0s")

        elif spawn_delay_mode == SpawnDelayMode.INCREMENTAL:
            min_delay_minutes, max_delay_minutes = self._parse_delay_value(delay_value)

            cumulative_delay = 0
            for i, aircraft in enumerate(aircraft_list):
                aircraft.spawn_delay = cumulative_delay

                increment_minutes = random.randint(min_delay_minutes, max_delay_minutes)
                increment_seconds = increment_minutes * 60
                cumulative_delay += increment_seconds

            logger.info(f"Applied INCREMENTAL spawn delays: {len(aircraft_list)} aircraft, "
                       f"delay range {min_delay_minutes}-{max_delay_minutes} min, "
                       f"final spawn at {cumulative_delay}s")

        elif spawn_delay_mode == SpawnDelayMode.TOTAL:
            if not total_session_minutes or total_session_minutes <= 0:
                logger.warning("Invalid total_session_minutes for TOTAL mode, defaulting to 30")
                total_session_minutes = 30

            # "Realistic" spawn distribution. Pure uniform-random bunches
            # aircraft and leaves stagnant windows, so we use stratified
            # sampling: divide the session into N equal strata, pick one
            # time from each stratum's inner 60% (avoids the extremes of
            # adjacent strata colliding), then shuffle assignments so the
            # aircraft-to-stratum mapping isn't tied to creation order.
            max_delay_seconds = total_session_minutes * 60
            n = len(aircraft_list)
            if n == 0:
                return
            if n == 1:
                aircraft_list[0].spawn_delay = random.randint(0, max_delay_seconds)
            else:
                stratum = max_delay_seconds / n
                margin = stratum * 0.2  # 20 % padding on each side
                times = [
                    random.randint(
                        int(i * stratum + margin),
                        int((i + 1) * stratum - margin),
                    )
                    for i in range(n)
                ]
                random.shuffle(times)
                for aircraft, t in zip(aircraft_list, times):
                    aircraft.spawn_delay = max(0, min(max_delay_seconds, t))

            logger.info(
                f"Applied TOTAL spawn delays: {n} aircraft stratified across "
                f"{total_session_minutes} min ({max_delay_seconds}s window, "
                f"stratum ~{int(max_delay_seconds / max(1, n))}s)"
            )

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
                parts = delay_value.split('-')
                min_val = int(parts[0])
                max_val = int(parts[1])
                return min_val, max_val
            else:
                val = int(delay_value)
                return val, val
        except (ValueError, IndexError):
            logger.warning(f"Invalid delay value: {delay_value}, using default (0-0)")
            return 0, 0

    def _load_config(self) -> Dict:
        """
        Load configuration from config.json.

        Goes through `ssg_bridge.resource_path` so we prefer the user-editable
        copy at `<install>/resources/config.json` (shipped as extraResources
        by electron-builder) and fall back to the PyInstaller-baked default
        when the user hasn't customized anything.
        """
        try:
            from ssg_bridge import resource_path
            config_path = resource_path('config.json')
        except Exception:
            # Legacy PyQt path: fall back to CWD lookup.
            config_path = Path('config.json')
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
        if '/' in aircraft_type:
            return aircraft_type

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

        base_type = aircraft_type.split('/')[0]
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

        match = re.match(r'^([A-Z]+)(\d+)-([A-Z]+)(\d+)$', range_str)

        if not match:
            return []

        prefix1, start_num, prefix2, end_num = match.groups()

        if prefix1 != prefix2:
            logger.warning(f"Gate range prefixes don't match: {prefix1} vs {prefix2} in '{range_str}'")
            return []

        start = int(start_num)
        end = int(end_num)

        if start > end:
            logger.warning(f"Gate range start > end: {start} > {end} in '{range_str}'")
            return []

        gates = [f"{prefix1}{num}" for num in range(start, end + 1)]
        logger.debug(f"Expanded gate range '{range_str}' to {len(gates)} gates: {gates[:3]}...")

        return gates

    def _get_airline_for_parking(self, parking_name: str):
        """
        Get allowed airline codes for a parking spot based on configuration

        Supports:
        1. Specific gates (highest priority): "B3" -> ["JBU"]
        2. Gate ranges: "B1-B11" -> ["AAL"]
        3. Prefix wildcards: "B#" -> ["DAL"] (matches B1, B2, B3, etc.)
        4. Catch-all wildcard (lowest priority): "#" -> ["DEFAULT"] (matches any gate)
        5. Prohibited gates: ["BLANK"] -> Prevents aircraft from spawning at this gate/pattern

        Priority order: Specific > Range > Prefix Wildcard > Catch-all Wildcard

        Special value: Use ["BLANK"] to prohibit aircraft spawning at specified gates.
        Example: "C#": ["BLANK"] will prevent any aircraft from using C gates.

        Args:
            parking_name: Name of the parking spot (e.g., "B3", "A10")

        Returns:
            List of allowed airlines, "BLANK" if prohibited, or None if no restriction
        """
        parking_airlines = self.config.get('parking_airlines', {})

        if self.airport_icao not in parking_airlines:
            return None

        airport_config = parking_airlines[self.airport_icao]

        # Priority 1: Check for exact match (specific gate override)
        if parking_name in airport_config:
            airlines = airport_config[parking_name]
            if airlines:
                # Check for BLANK value to prohibit spawning
                if len(airlines) == 1 and airlines[0] == "BLANK":
                    logger.debug(f"Gate {parking_name}: Marked as BLANK (prohibited)")
                    return "BLANK"
                logger.debug(f"Gate {parking_name}: Using specific assignment -> {airlines}")
                return airlines  # Return list of allowed airlines

        # Priority 2: Check for range matches
        for pattern, airlines in airport_config.items():
            if '-' in pattern and '#' not in pattern:
                expanded_gates = self._expand_gate_range(pattern)
                if parking_name in expanded_gates:
                    if airlines:
                        # Check for BLANK value to prohibit spawning
                        if len(airlines) == 1 and airlines[0] == "BLANK":
                            logger.debug(f"Gate {parking_name}: Matched range '{pattern}' marked as BLANK (prohibited)")
                            return "BLANK"
                        logger.debug(f"Gate {parking_name}: Matched range '{pattern}' -> {airlines}")
                        return airlines  # Return list of allowed airlines

        # Priority 3: Check for prefix wildcard matches (e.g., "A#", "B#", "FEDX#")
        # Sort by prefix length (descending) so longer prefixes match first
        wildcard_patterns = []
        catchall_pattern = None

        for pattern, airlines in airport_config.items():
            if '#' in pattern:
                prefix = pattern.replace('#', '')
                if prefix:  # Has a prefix (e.g., "A#", "FEDX#")
                    wildcard_patterns.append((pattern, prefix, airlines))
                else:  # Bare "#" - this is the catch-all
                    catchall_pattern = (pattern, airlines)

        # Sort wildcard patterns by prefix length (longest first) for specificity
        wildcard_patterns.sort(key=lambda x: len(x[1]), reverse=True)

        # Try to match prefix wildcards
        for pattern, prefix, airlines in wildcard_patterns:
            if parking_name.startswith(prefix):
                if airlines:
                    # Check for BLANK value to prohibit spawning
                    if len(airlines) == 1 and airlines[0] == "BLANK":
                        logger.debug(f"Gate {parking_name}: Matched wildcard '{pattern}' marked as BLANK (prohibited)")
                        return "BLANK"
                    logger.debug(f"Gate {parking_name}: Matched wildcard '{pattern}' -> {airlines}")
                    return airlines  # Return list of allowed airlines

        # Priority 4: Check catch-all wildcard (lowest priority)
        if catchall_pattern:
            pattern, airlines = catchall_pattern
            if airlines:
                # Check for BLANK value to prohibit spawning
                if len(airlines) == 1 and airlines[0] == "BLANK":
                    logger.debug(f"Gate {parking_name}: Matched catch-all '{pattern}' marked as BLANK (prohibited)")
                    return "BLANK"
                logger.debug(f"Gate {parking_name}: Matched catch-all '{pattern}' -> {airlines}")
                return airlines  # Return list of allowed airlines

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

        known_sids = self.cifp_parser.get_available_sids()

        for part in route_parts[:3]:
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

        sid_in_route = self._extract_sid_from_route(api_route)

        # If no SID in route, it's valid (DCT routes are allowed)
        if not sid_in_route:
            logger.debug(f"No SID found in route '{api_route}', accepting as valid")
            return True

        if manual_sids:
            is_valid = sid_in_route.upper() in [s.upper() for s in manual_sids]
            if is_valid:
                logger.debug(f"Route SID '{sid_in_route}' matches manual SID list")
            else:
                logger.debug(f"Route SID '{sid_in_route}' not in manual SID list {manual_sids}")
            return is_valid

        if active_runways:
            sid_runways = self.cifp_parser.get_runways_for_departure(sid_in_route)
            if not sid_runways:
                logger.debug(f"No runway data found for SID '{sid_in_route}', accepting as valid")
                return True

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

        if manual_sids and len(manual_sids) > 0:
            available_sids = manual_sids
            logger.debug(f"Using manual SIDs: {', '.join(manual_sids)}")
        elif active_runways and len(active_runways) > 0:
            for runway in active_runways:
                runway_sids = self.cifp_parser.get_sids_for_runway(runway)
                available_sids.extend(runway_sids)

            available_sids = list(set(available_sids))

            if available_sids:
                logger.debug(f"Found {len(available_sids)} SIDs for runways {', '.join(active_runways)}: {', '.join(available_sids)}")
            else:
                logger.warning(f"No SIDs found for runways {', '.join(active_runways)}")
        else:
            logger.warning("No active runways or manual SIDs specified for SID selection")
            return None

        if available_sids:
            selected_sid = random.choice(available_sids)
            logger.debug(f"Selected SID: {selected_sid}")
            return selected_sid

        return None

    def _get_sids_for_active_runways(self, active_runways: List[str]) -> List[str]:
        """
        Get all valid SIDs from CIFP data that match the active runways

        Args:
            active_runways: List of active runway designators (e.g., ['08', '26', '21'])

        Returns:
            List of SID names that are valid for at least one of the active runways
        """
        if not active_runways:
            return []

        valid_sids = []
        for runway in active_runways:
            runway_sids = self.cifp_parser.get_sids_for_runway(runway)
            valid_sids.extend(runway_sids)

        # Remove duplicates while preserving order
        unique_sids = list(dict.fromkeys(valid_sids))

        return unique_sids

    def _resolve_allowed_sids(self, active_runways, enable_cifp_sids, manual_sids):
        """Return (allowed_sids, strict) per the SID rules.

        - enable_cifp_sids=False -> (None, False): no SID filter.
        - manual_sids provided -> use those verbatim, strict filter.
        - Otherwise: CIFP SIDs for active_runways union CIFP runway-agnostic SIDs.
          * If CIFP has no SIDs at all for this airport -> (None, False).
          * If CIFP has SIDs but none match the active runways (even after
            including runway-agnostic) -> raise ValueError.
        """
        if not enable_cifp_sids:
            return None, False

        if manual_sids:
            allowed = [s.strip().upper() for s in manual_sids if s and s.strip()]
            logger.info(f"Using manual SIDs: {allowed}")
            return allowed, True

        all_sids = self.cifp_parser.get_available_sids() or []
        if not all_sids:
            logger.info(
                f"CIFP has no SIDs for {self.airport_icao}; disabling SID filter (pass-through)."
            )
            return None, False

        runway_specific = []
        for rwy in (active_runways or []):
            runway_specific.extend(self.cifp_parser.get_sids_for_runway(rwy) or [])

        runway_agnostic = [
            s for s in all_sids
            if not (self.cifp_parser.get_runways_for_departure(s) or [])
        ]

        merged = list(dict.fromkeys([*runway_specific, *runway_agnostic]))
        if not merged:
            raise ValueError(
                f"No SIDs at {self.airport_icao} serve runways {active_runways} "
                f"(CIFP lists {len(all_sids)} SIDs overall). Pick different "
                "runways, supply manual SIDs, or disable CIFP SID filtering."
            )

        logger.info(
            f"Allowed SIDs for runways {active_runways}: "
            f"{len(runway_specific)} runway-specific + {len(runway_agnostic)} runway-agnostic "
            f"= {len(merged)} total"
        )
        return merged, True

    def _prepare_departure_flight_pool(self, active_runways=None,
                                        enable_cifp_sids=False,
                                        manual_sids=None,
                                        num_required=0):
        """Fetch and bucket departure flights for this airport.

        Uses `utils.data_pipeline.flight_pool.fetch_departures` so the API
        call is server-filtered by the allowed SID list and capped at a
        `num_required * 3` buffer (min 100, max 1000). Surviving flights are
        bucketed as `{airline: {L/M/H: [...]}}` for the wake-aware picker.
        """
        from collections import defaultdict
        from utils.flight_data_filter import extract_sid_from_route
        from utils.data_pipeline import fetch_departures as pool_fetch_departures

        self.active_runways = active_runways
        allowed_sids, strict_sid_filter = self._resolve_allowed_sids(
            active_runways, enable_cifp_sids, manual_sids,
        )
        self.current_sids = allowed_sids

        # Pass the wake budget so the pool can fan out per-category server-side
        # (wakecat=H/M/L). Without this, small airports with thin heavy traffic
        # wouldn't return enough H-wake flights to honor a heavy-biased budget.
        wake_counts = (self.dep_wake_budget.budget
                       if getattr(self, 'dep_wake_budget', None) else None)
        valid_flights, warnings = pool_fetch_departures(
            self.api_client, self.airport_icao,
            num_required=num_required, allowed_sids=allowed_sids,
            wake_counts=wake_counts,
        )
        self.pool_warnings = getattr(self, 'pool_warnings', []) + list(warnings)

        # by_airline_wake[airline][wake] -> list of flights
        self.departure_flights_by_airline_wake = defaultdict(
            lambda: {c: [] for c in WAKE_CATEGORIES}
        )
        self.ga_departure_flights = []

        stats = {
            'ga': 0, 'accepted': 0,
            'rejected_no_sid': 0, 'rejected_sid_mismatch': 0,
        }
        sids_seen = defaultdict(int)

        for flight in valid_flights:
            aircraft_type = flight.get('aircraftType', '')
            operator = flight.get('operator') or 'UNKNOWN'
            route = flight.get('route', '')

            sid = flight.get('departureProcedure') or ''
            if not sid and route:
                sid = extract_sid_from_route(route) or ''
            if sid:
                sids_seen[sid] += 1

            if self._is_ga_aircraft_type(aircraft_type):
                self.ga_departure_flights.append(flight)
                stats['ga'] += 1
                continue

            if strict_sid_filter and allowed_sids:
                # API already pre-filtered, but double-check in case the
                # server returned something unexpected.
                if not sid:
                    stats['rejected_no_sid'] += 1
                    continue
                if not matches_any(sid, allowed_sids):
                    stats['rejected_sid_mismatch'] += 1
                    continue

            wake = normalize_category(flight.get('wakeTurbulence'))
            self.departure_flights_by_airline_wake[operator][wake].append(flight)
            stats['accepted'] += 1

        # Flat back-compat view (wake-agnostic).
        self.departure_flights_by_airline = {
            airline: [f for bucket in cats.values() for f in bucket]
            for airline, cats in self.departure_flights_by_airline_wake.items()
        }

        logger.info(
            f"Departure pool: {stats['accepted']} airline accepted, "
            f"{stats['ga']} GA, {stats['rejected_no_sid']} rejected (no SID), "
            f"{stats['rejected_sid_mismatch']} rejected (SID mismatch)"
        )
        self.departure_flight_pool = valid_flights

    def _is_valid_departure_flight(self, flight: Dict) -> bool:
        """
        Validate if a departure flight's SID is compatible with active runways

        Args:
            flight: Flight dictionary from API

        Returns:
            True if the flight is valid (SID matches active runways or no validation needed)
        """
        # If no active runways stored, no validation needed
        if not hasattr(self, 'active_runways') or not self.active_runways:
            return True

        # Extract SID from flight data
        sid = flight.get('departureProcedure', '')
        if not sid:
            # No SID in flight data - allow it (might be assigned later)
            return True

        # Get runways that this SID serves from CIFP
        sid_runways = self.cifp_parser.get_runways_for_departure(sid)
        if not sid_runways:
            # SID not found in CIFP data - log warning but allow it
            logger.debug(f"SID {sid} not found in CIFP data, allowing flight")
            return True

        # Check if any of the SID's runways match the active runways
        for active_rwy in self.active_runways:
            # Normalize runway format for comparison
            active_normalized = active_rwy.lstrip('RW').zfill(2) if active_rwy.replace('RW', '').replace('L', '').replace('R', '').replace('C', '').isdigit() else active_rwy.lstrip('RW')

            for sid_rwy in sid_runways:
                sid_normalized = sid_rwy.lstrip('RW').zfill(2) if sid_rwy.replace('RW', '').replace('L', '').replace('R', '').replace('C', '').isdigit() else sid_rwy.lstrip('RW')

                # Check for exact match or base match (08 matches 08L, 08R)
                if active_normalized == sid_normalized:
                    return True
                # Also check if the bases match (stripping L/R/C suffixes)
                active_base = active_normalized.rstrip('LRC')
                sid_base = sid_normalized.rstrip('LRC')
                if active_base == sid_base:
                    return True

        # No match found - this SID doesn't serve any active runway
        logger.debug(f"Skipping flight with SID {sid} (serves runways {sid_runways}, but active runways are {self.active_runways})")
        return False

    def _get_next_departure_flight(self, parking_spot_name=None, is_ga_spot=False):
        """Pick the next departure flight.

        - GA spots draw from self.ga_departure_flights.
        - Airline spots honor the wake budget (prefer the wake category with
          the most remaining quota that still has flights for an acceptable
          airline) and the parking-spot airline restriction.
        - If the preferred wake category has no matching flight, we backfill
          from other categories (consuming the *preferred* category's budget
          slot and incrementing the backfill counter).
        """
        if is_ga_spot:
            if self.ga_departure_flights:
                return self.ga_departure_flights.pop(0)
            logger.warning("GA departure pool depleted")
            if parking_spot_name:
                self.gate_failure_reasons[parking_spot_name] = "GA pool depleted"
            return None

        allowed_airlines = None
        if parking_spot_name:
            parking_airlines = self._get_airline_for_parking(parking_spot_name)
            if parking_airlines == "BLANK":
                logger.debug(
                    f"Skipping gate {parking_spot_name} - marked as BLANK (prohibited)"
                )
                self.gate_failure_reasons[parking_spot_name] = "BLANK (prohibited)"
                return None
            if parking_airlines:
                allowed_airlines = (
                    [parking_airlines] if isinstance(parking_airlines, str)
                    else list(parking_airlines)
                )

        flight = self._pick_airline_flight(allowed_airlines)
        if flight is None:
            if allowed_airlines and parking_spot_name:
                counts = {a: sum(len(v) for v in
                                 self.departure_flights_by_airline_wake.get(a, {}).values())
                          for a in allowed_airlines}
                logger.warning(
                    f"[NO MATCH] Gate {parking_spot_name} allows {allowed_airlines} "
                    f"but no flights available: {counts}"
                )
                counts_str = ', '.join(f'{a}={c}' for a, c in counts.items())
                self.gate_failure_reasons[parking_spot_name] = (
                    f"No flights for allowed airlines ({counts_str})"
                )
            else:
                logger.warning("All departure flight pools depleted")
        return flight

    def _pick_airline_flight(self, allowed_airlines):
        """Wake-aware pick from self.departure_flights_by_airline_wake.

        Honors the README's airline-weighting convention: the `allowed_airlines`
        list may repeat codes (`["AAL", "AAL", "DAL"]` = 67 %/33 %), so we
        sample a preferred airline proportionally. If that airline's pool for
        the preferred wake cat is empty we redraw; if nothing matches after
        enough tries we fall back to the old first-match-wins order to avoid
        starving the scenario.

        Returns a flight dict (and updates wake budget) or None if no matching
        flight exists.
        """
        airlines = (
            allowed_airlines
            if allowed_airlines
            else list(self.departure_flights_by_airline_wake.keys())
        )
        budget = self.dep_wake_budget

        def pool(airline, wake):
            return self.departure_flights_by_airline_wake.get(airline, {}).get(wake, [])

        def pick_weighted(airlines_with_weight):
            """Weighted random sample of an airline from the list, preserving
            duplicates as the weight signal (random.choice already does this
            on a list with repeats). Returns the sampled airline or None if
            the list is empty."""
            if not airlines_with_weight:
                return None
            return random.choice(airlines_with_weight)

        # -------- No wake bias: pick weighted, fall back to any supplier --------
        if budget is None:
            # Try the weighted sample first (up to a few retries so a repeated
            # "heavy" weight doesn't deadlock on an empty pool).
            for _ in range(min(16, len(airlines) * 2)):
                airline = pick_weighted(airlines)
                for cat in WAKE_CATEGORIES:
                    if pool(airline, cat):
                        return pool(airline, cat).pop(0)
            # Retries exhausted — take the first non-empty airline in order.
            for airline in airlines:
                for cat in WAKE_CATEGORIES:
                    if pool(airline, cat):
                        return pool(airline, cat).pop(0)
            return None

        # -------- Wake bias active: prefer the highest-remaining-budget cat --------
        available = {c: sum(len(pool(a, c)) for a in airlines) for c in WAKE_CATEGORIES}
        preferred = budget.preferred_category(available)
        if preferred is not None:
            for _ in range(min(16, len(airlines) * 2)):
                airline = pick_weighted(airlines)
                if pool(airline, preferred):
                    flight = pool(airline, preferred).pop(0)
                    budget.consume(preferred, actual=preferred)
                    return flight
            # Fall through to ordered scan for the preferred cat only.
            for airline in airlines:
                if pool(airline, preferred):
                    flight = pool(airline, preferred).pop(0)
                    budget.consume(preferred, actual=preferred)
                    return flight

        # -------- Backfill: any wake cat, weighted by airline --------
        for _ in range(min(16, len(airlines) * 2)):
            airline = pick_weighted(airlines)
            for cat in WAKE_CATEGORIES:
                if pool(airline, cat):
                    flight = pool(airline, cat).pop(0)
                    shortfall = budget.shortfall_summary()
                    intended = max(
                        WAKE_CATEGORIES, key=lambda c: shortfall.get(c, 0),
                    ) if any(shortfall.values()) else cat
                    budget.consume(intended, actual=cat)
                    return flight
        # Final ordered scan.
        for airline in airlines:
            for cat in WAKE_CATEGORIES:
                if pool(airline, cat):
                    flight = pool(airline, cat).pop(0)
                    shortfall = budget.shortfall_summary()
                    intended = max(
                        WAKE_CATEGORIES, key=lambda c: shortfall.get(c, 0),
                    ) if any(shortfall.values()) else cat
                    budget.consume(intended, actual=cat)
                    return flight
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

        is_ga_spot = "GA" in parking_spot.name.upper()
        flight_data = self._get_next_departure_flight(parking_spot.name, is_ga_spot)

        if not flight_data:
            logger.error("No flight data available for departure aircraft")
            with self.parking_lock:
                self.used_parking_spots.discard(parking_spot.name)
            return None

        raw_route = flight_data.get('route', '')
        route = clean_route_string(raw_route)
        destination = destination or flight_data.get('arrivalAirport', self._get_random_destination())
        api_callsign = flight_data.get('aircraftIdentification', '')
        api_aircraft_type = flight_data.get('aircraftType', 'B738')

        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            cruise_altitude = str(int(float(requested_alt)))
        else:
            cruise_altitude = '35000'

        cruise_speed_str = flight_data.get('requestedAirspeed')
        if cruise_speed_str:
            try:
                cruise_speed = int(float(cruise_speed_str))
            except (ValueError, TypeError):
                cruise_speed = self.api_client._calculate_cruise_speed(api_aircraft_type)
        else:
            cruise_speed = self.api_client._calculate_cruise_speed(api_aircraft_type)

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
                logger.warning(f"No callsign from API for flight to {destination}, generating one")
                callsign = self._generate_callsign()

        # Thread-safe callsign assignment - ensure uniqueness
        with self.callsign_lock:
            # If callsign is already used, we have a duplicate from API
            if callsign in self.used_callsigns:
                logger.warning(f"Duplicate callsign from API: {callsign}, skipping this flight")
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
            gufi=flight_data.get('gufi'),
            registration=flight_data.get('registration'),
            operator=flight_data.get('operator'),
            estimated_arrival_time=flight_data.get('estimatedArrivalTime'),
            wake_turbulence=flight_data.get('wakeTurbulence'),
            sid=flight_data.get('departureProcedure'),
            star=flight_data.get('arrivalProcedure')
        )

        return aircraft

    def _prepare_ga_flight_pool(self):
        """
        Prepare pool of GA flights from cached departure data.
        Note: This is now handled by _prepare_departure_flight_pool which creates self.ga_departure_flights.
        This method kept for backward compatibility.
        """
        if not hasattr(self, 'ga_departure_flights'):
            logger.warning("GA departure flights not initialized, initializing now...")
            valid_flights = filter_valid_flights(self.cached_flights['departures'])
            ga_flights, _ = categorize_flights(valid_flights)
            self.ga_departure_flights = ga_flights
            logger.info(f"Prepared GA flight pool with {len(ga_flights)} aircraft")

    def _get_next_ga_flight(self) -> Dict:
        """
        Get next GA flight from pool.
        Note: This now uses self.ga_departure_flights created by _prepare_departure_flight_pool.
        """
        if not hasattr(self, 'ga_departure_flights'):
            self._prepare_ga_flight_pool()

        if not self.ga_departure_flights:
            logger.warning("GA flight pool depleted")
            return None

        # GA flights are already filtered, just return the next one
        return self.ga_departure_flights.pop(0)

    def _prepare_arrival_flight_pool(self, requested_stars=None, num_required=0):
        """Fetch and bucket arrival flights for this airport.

        Uses `utils.data_pipeline.flight_pool.fetch_arrivals` for server-side
        STAR filtering + buffered pagination. When `requested_stars` is given
        the pool is bucketed as `{star_base: {L/M/H: [...]}}` for the
        wake-aware picker; otherwise flights land in a flat commercial pool.
        """
        from utils.data_pipeline import fetch_arrivals as pool_fetch_arrivals

        wake_counts = (self.arr_wake_budget.budget
                       if getattr(self, 'arr_wake_budget', None) else None)
        valid_flights, warnings = pool_fetch_arrivals(
            self.api_client, self.airport_icao,
            num_required=num_required, requested_stars=requested_stars,
            wake_counts=wake_counts,
        )
        self.pool_warnings = getattr(self, 'pool_warnings', []) + list(warnings)
        _, commercial = categorize_flights(valid_flights)

        if requested_stars:
            bases = [b for b in (strip_suffix(s) for s in requested_stars) if b]
            from collections import defaultdict
            self.arrivals_by_star_wake = defaultdict(
                lambda: {c: [] for c in WAKE_CATEGORIES}
            )
            for f in commercial:
                proc = f.get('arrivalProcedure')
                if not proc:
                    continue
                proc_base = strip_suffix(proc)
                for b in bases:
                    if proc_base == b:
                        wake = normalize_category(f.get('wakeTurbulence'))
                        self.arrivals_by_star_wake[b][wake].append(f)
                        break
            per_star = {b: sum(len(v) for v in self.arrivals_by_star_wake[b].values())
                        for b in bases}
            logger.info(f"Arrival pool by STAR: {per_star}")
            self.arrival_flight_pool = commercial
            return

        self.arrival_flight_pool = commercial
        self.arrivals_by_star_wake = None
        logger.info(f"Prepared arrival flight pool with {len(commercial)} aircraft")

    def _pick_arrival_flight(self, star_base):
        """Pick one arrival flight for the given STAR base, honoring the wake
        budget. Returns None if no flight remains for that STAR."""
        if not getattr(self, 'arrivals_by_star_wake', None):
            return None
        key = strip_suffix(star_base)
        pools = self.arrivals_by_star_wake.get(key)
        if not pools:
            return None

        available = {c: len(pools[c]) for c in WAKE_CATEGORIES}
        budget = self.arr_wake_budget

        if budget is not None:
            preferred = budget.preferred_category(available)
            if preferred is not None and pools[preferred]:
                flight = pools[preferred].pop(0)
                budget.consume(preferred, actual=preferred)
                return flight

        # Backfill: any category with supply.
        for cat in WAKE_CATEGORIES:
            if pools[cat]:
                flight = pools[cat].pop(0)
                if budget is not None:
                    shortfall = budget.shortfall_summary()
                    intended = max(
                        WAKE_CATEGORIES, key=lambda c: shortfall.get(c, 0),
                    ) if any(shortfall.values()) else cat
                    budget.consume(intended, actual=cat)
                return flight
        return None

    def _get_next_arrival_flight(self) -> Dict:
        """Legacy flat-pool picker (no STAR/wake awareness). Kept for scenarios
        that haven't migrated to _pick_arrival_flight."""
        if not hasattr(self, 'arrival_flight_pool'):
            self._prepare_arrival_flight_pool()

        if not self.arrival_flight_pool:
            logger.warning("Arrival flight pool depleted, fetching more...")
            additional_flights = self.api_client.fetch_arrivals(self.airport_icao, limit=50)
            if additional_flights:
                valid_flights = filter_valid_flights(additional_flights)
                _, commercial_flights = categorize_flights(valid_flights)
                self.arrival_flight_pool.extend(commercial_flights)
                logger.info(f"Added {len(commercial_flights)} more arrival flights to pool")

        return self.arrival_flight_pool.pop(0) if self.arrival_flight_pool else None

    def _create_ga_aircraft(self, parking_spot, destination: str = None,
                            ga_mode: Optional[str] = None) -> Aircraft:
        """Create a GA aircraft at a parking spot.

        `ga_mode` ∈ {'VFR', 'IFR', None}:
          - 'VFR': synthesize a plan from `data_pipeline.ga_fleet` (no API).
          - 'IFR': pick a matching GA-type plan from the main departure pool
            that's already been fetched; falls back to the legacy auto-GA pool
            when no match is available.
          - None: legacy behavior (picks from `self.ga_departure_flights`).
        """
        if parking_spot.name in self.used_parking_spots:
            logger.warning(f"Parking spot {parking_spot.name} is already in use, skipping")
            return None

        self.used_parking_spots.add(parking_spot.name)
        logger.debug(f"Assigned parking spot: {parking_spot.name}")

        flight_data = None
        if ga_mode == 'VFR':
            from utils.data_pipeline import synthesize_vfr_plan
            flight_data = synthesize_vfr_plan(origin=self.airport_icao)
            logger.debug(f"Synthesized VFR GA plan {flight_data['aircraftIdentification']} at {parking_spot.name}")
        elif ga_mode == 'IFR':
            from utils.data_pipeline import pick_ifr_plan_from_pool
            flight_data = pick_ifr_plan_from_pool(
                self.departure_flight_pool, self.ga_used_gufis,
            )
            if flight_data is None:
                logger.info("No GA-type IFR flight in departure pool; falling back to legacy GA pool")
                flight_data = self._get_next_ga_flight()
        else:
            flight_data = self._get_next_ga_flight()

        if flight_data:
            # Use API data - ALWAYS use the API callsign to keep data matched
            api_callsign = flight_data.get('aircraftIdentification', '')
            if api_callsign and api_callsign.strip():
                callsign = api_callsign
            else:
                logger.warning("GA flight from API missing callsign, generating one")
                callsign = self._generate_ga_callsign()
            aircraft_type = flight_data.get('aircraftType', 'C172')
            destination = destination or flight_data.get('arrivalAirport', self._get_random_destination(exclude=self.airport_icao, less_common=True))
            raw_route = flight_data.get('route', 'DCT')
            route = clean_route_string(raw_route) if raw_route != 'DCT' else 'DCT'

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

    def _parse_frd_string(self, frd_string: str) -> Tuple[str, int, int]:
        """
        Parse FRD (Fix/Radial/Distance) string into components.

        Args:
            frd_string: FRD format string (e.g., "KABQ020010" or "HOMRR235012")

        Returns:
            Tuple of (fix_name, radial, distance_nm)

        Raises:
            ValueError: If FRD string format is invalid
        """
        # FRD format: FIXRADIALDISTANCE
        # Radial: 3 digits (000-359)
        # Distance: 3 digits (000-999 NM)
        # Minimum length: fix + 3 + 3 = 7 characters
        if len(frd_string) < 7:
            raise ValueError(f"Invalid FRD string: {frd_string} (too short)")

        # Extract distance (last 3 digits)
        try:
            distance_nm = int(frd_string[-3:])
        except ValueError:
            raise ValueError(f"Invalid FRD string: {frd_string} (distance not numeric)")

        # Extract radial (3 digits before distance)
        try:
            radial = int(frd_string[-6:-3])
        except ValueError:
            raise ValueError(f"Invalid FRD string: {frd_string} (radial not numeric)")

        if radial < 0 or radial > 359:
            raise ValueError(f"Invalid FRD string: {frd_string} (radial out of range 0-359)")

        # Extract fix name (everything before radial)
        fix_name = frd_string[:-6]

        if not fix_name:
            raise ValueError(f"Invalid FRD string: {frd_string} (no fix name)")

        logger.debug(f"Parsed FRD '{frd_string}': fix={fix_name}, radial={radial:03d}, distance={distance_nm}NM")
        return (fix_name, radial, distance_nm)

    def _generate_random_frd(self) -> Tuple[str, int, int]:
        """
        Generate random FRD position around the airport.

        Returns:
            Tuple of (fix_name, radial, distance_nm) where:
            - fix_name is the airport ICAO
            - radial is random 0-359
            - distance is random 8-12 NM
        """
        fix_name = self.airport_icao
        radial = random.randint(0, 359)
        distance_nm = random.randint(8, 12)

        logger.debug(f"Generated random FRD: fix={fix_name}, radial={radial:03d}, distance={distance_nm}NM")
        return (fix_name, radial, distance_nm)

    def _get_fix_coordinates(self, fix_name: str) -> Tuple[float, float]:
        """
        Get coordinates for a fix (waypoint or airport).

        Args:
            fix_name: Name of the fix (waypoint or airport ICAO)

        Returns:
            Tuple of (latitude, longitude)

        Raises:
            ValueError: If fix not found
        """
        if fix_name == self.airport_icao:
            return self.geojson_parser.get_airport_center()

        for procedure_type in ['stars', 'sids', 'approaches']:
            procedures = getattr(self.cifp_parser, procedure_type, {})
            for proc_name, waypoints in procedures.items():
                for waypoint in waypoints:
                    if waypoint.name == fix_name and waypoint.latitude and waypoint.longitude:
                        logger.debug(f"Found fix {fix_name} in {procedure_type}/{proc_name}: {waypoint.latitude}, {waypoint.longitude}")
                        return (waypoint.latitude, waypoint.longitude)

        raise ValueError(f"Fix '{fix_name}' not found in airport or CIFP data")

    def _calculate_runway_separation_increment(
        self,
        prev_runway: str,
        next_runway: str,
        parallel_info: Dict
    ) -> int:
        """
        Calculate the distance increment needed between successive aircraft on different runways.

        Implements FAA parallel runway separation standards:
        - < 2,500 ft or > 9,000 ft: 3 NM (treat as same runway)
        - 2,500-3,600 ft: 2 NM (rounded up from ~1.31 NM for 1 NM diagonal)
        - 3,600-8,300 ft: 2 NM (rounded up from 1.31-1.99 NM for 1.5 NM diagonal)
        - 8,300-9,000 ft: 2 NM (for 2 NM diagonal)

        Args:
            prev_runway: Previous runway end designator (e.g., '8')
            next_runway: Next runway end designator (e.g., '7L')
            parallel_info: Dict from get_parallel_runway_info() with parallel runway data

        Returns:
            Distance increment in NM (integer) to add to current distance
        """
        import math

        # If same runway, add standard separation
        if prev_runway == next_runway:
            return 3

        if not parallel_info:
            # No parallel info available, treat as independent runways
            return 3

        centerline_spacing_nm = None
        required_diagonal_nm = None

        if prev_runway in parallel_info:
            prev_data = parallel_info[prev_runway]
            if next_runway in prev_data.get('parallels', []):
                centerline_spacing_nm = prev_data['spacing_nm'].get(next_runway)
                required_diagonal_nm = prev_data['required_sep_nm'].get(next_runway)

        if centerline_spacing_nm is None and next_runway in parallel_info:
            next_data = parallel_info[next_runway]
            if prev_runway in next_data.get('parallels', []):
                centerline_spacing_nm = next_data['spacing_nm'].get(prev_runway)
                required_diagonal_nm = next_data['required_sep_nm'].get(prev_runway)

        # If not parallel, treat as independent runways
        if centerline_spacing_nm is None or required_diagonal_nm is None:
            logger.debug(f"{prev_runway} and {next_runway} are not parallel, using 3 NM separation")
            return 3

        # Calculate minimum along-track separation needed for required diagonal
        # Using inverse Pythagorean: along_track = sqrt(diagonal^2 - centerline^2)
        if required_diagonal_nm <= centerline_spacing_nm:
            # Centerline spacing alone satisfies diagonal requirement
            min_along_track = 0.0
        else:
            min_along_track = math.sqrt(required_diagonal_nm**2 - centerline_spacing_nm**2)

        # Round UP to nearest integer (vNAS requirement)
        increment = math.ceil(min_along_track)

        # Ensure at least 2 NM for parallel runways (common minimum)
        if increment < 2:
            increment = 2

        logger.debug(
            f"Runway pair {prev_runway}-{next_runway}: "
            f"centerline={centerline_spacing_nm:.3f} NM, "
            f"required diagonal={required_diagonal_nm:.1f} NM, "
            f"min along-track={min_along_track:.2f} NM, "
            f"increment={increment} NM"
        )

        return increment

    def get_aircraft(self) -> List[Aircraft]:
        """Get generated aircraft list"""
        return self.aircraft
