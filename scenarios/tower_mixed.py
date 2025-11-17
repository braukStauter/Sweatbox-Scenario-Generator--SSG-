"""
Tower (Departures/Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple
from collections import defaultdict

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.flight_data_filter import clean_route_string

logger = logging.getLogger(__name__)


class TowerMixedScenario(BaseScenario):
    """Scenario for Tower position with departures and arrivals"""

    def generate(self, num_departures: int, num_arrivals: int, active_runways: List[str],
                 additional_separation: int = 0,
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None,
                 enable_cifp_sids: bool = False, manual_sids: List[str] = None,
                 num_vfr: int = 0, vfr_spawn_locations: List[str] = None) -> List[Aircraft]:
        """
        Generate tower scenario with departures and arrivals

        Args:
            num_departures: Number of departure aircraft
            num_arrivals: Number of arrival aircraft
            active_runways: List of active runway designators
            additional_separation: Fixed additional NM to add to minimum separation for each aircraft
            spawn_delay_mode: SpawnDelayMode enum (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: delay range/value in minutes (e.g., "2-5" or "3")
            total_session_minutes: For TOTAL mode: total session length in minutes
            spawn_delay_range: LEGACY parameter - kept for backward compatibility
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts for difficulty levels
            enable_cifp_sids: Whether to use CIFP SID procedures
            manual_sids: Optional list of specific SIDs to use
            num_vfr: Number of VFR aircraft to generate
            vfr_spawn_locations: Optional list of FRD strings for VFR spawn locations

        Returns:
            List of Aircraft objects
        """
        # Reset tracking for new generation
        self._reset_tracking()

        # Validate VFR aircraft count
        if num_vfr > 0 and num_vfr > num_departures:
            logger.warning(f"VFR aircraft count ({num_vfr}) exceeds departure count ({num_departures}). "
                          f"Limiting VFR aircraft to {num_departures}")
            num_vfr = num_departures

        # Prepare flight pools from cached data
        logger.info("Preparing flight pools...")
        self._prepare_departure_flight_pool(active_runways, enable_cifp_sids, manual_sids)
        self._prepare_ga_flight_pool()
        self._prepare_arrival_flight_pool()

        # Get parallel runway information for separation calculations
        parallel_info = self.geojson_parser.get_parallel_runway_info()

        # Get runway groups for per-group distance tracking
        runway_groups = self.geojson_parser.get_runway_groups()

        # Setup difficulty assignment
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        # Handle legacy spawn_delay_range parameter
        if spawn_delay_range and not delay_value:
            logger.warning("Using legacy spawn_delay_range parameter. Consider upgrading to spawn_delay_mode.")
            min_delay, max_delay = self._parse_spawn_delay_range(spawn_delay_range)

        parking_spots = self.geojson_parser.get_parking_spots()
        ga_spots = self.geojson_parser.get_parking_spots(filter_ga=True)

        if num_departures > len(parking_spots):
            raise ValueError(
                f"Cannot create {num_departures} departures - only {len(parking_spots)} parking spots available at {self.airport_icao}. "
                f"Please reduce the number of departures to {len(parking_spots)} or fewer."
            )

        logger.info(f"Generating Tower scenario: {num_departures} departures, {num_arrivals} arrivals")

        # Calculate how many GA aircraft to include (10-20% of departures if GA spots exist)
        num_ga = 0
        if ga_spots:
            num_ga = min(len(ga_spots), max(1, int(num_departures * 0.15)))

        # Generate commercial departures
        num_commercial = num_departures - num_ga
        commercial_spots = [spot for spot in parking_spots if 'GA' not in spot.name.upper()]

        if num_commercial > 0:
            attempts = 0
            max_attempts = len(commercial_spots) * 2
            available_spots = commercial_spots.copy()
            failed_gates = []  # Track gates that couldn't be filled

            while len(self.aircraft) < num_commercial and attempts < max_attempts and available_spots:
                spot = random.choice(available_spots)

                aircraft = self._create_departure_aircraft(
                    spot,
                    active_runways=active_runways,
                    enable_cifp_sids=enable_cifp_sids,
                    manual_sids=manual_sids
                )
                if aircraft is not None:
                    # Only remove spot if aircraft was successfully created
                    available_spots.remove(spot)
                    # Legacy mode: apply random spawn delay
                    if spawn_delay_range and not delay_value:
                        aircraft.spawn_delay = random.randint(min_delay, max_delay)
                        logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
                    difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                    self.aircraft.append(aircraft)
                else:
                    # Track failed gates
                    if spot.name not in failed_gates:
                        failed_gates.append(spot.name)
                    available_spots.remove(spot)  # Remove failed spot to avoid retrying

                attempts += 1

        # Generate GA departures
        if num_ga > 0 and ga_spots:
            attempts = 0
            max_attempts = len(ga_spots) * 2
            available_ga_spots = ga_spots.copy()
            num_ga_created = 0

            while num_ga_created < num_ga and attempts < max_attempts and available_ga_spots:
                spot = random.choice(available_ga_spots)

                aircraft = self._create_ga_aircraft(spot)
                if aircraft is not None:
                    # Only remove spot if aircraft was successfully created
                    available_ga_spots.remove(spot)
                    # Legacy mode: apply random spawn delay
                    if spawn_delay_range and not delay_value:
                        aircraft.spawn_delay = random.randint(min_delay, max_delay)
                        logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
                    difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                    self.aircraft.append(aircraft)
                    num_ga_created += 1

                attempts += 1

        # Generate arrivals using simple iterative algorithm with per-group distance counters
        # Each runway group maintains its own distance counter
        num_arrivals_created = 0
        attempts = 0
        max_attempts = num_arrivals * 10  # Allow up to 10 attempts per aircraft

        # Initialize per-group distance counters and previous runway tracking
        if spawn_delay_mode == SpawnDelayMode.NONE and not spawn_delay_range:
            # Dictionary: group_id -> current_distance
            group_distances = {}
            # Dictionary: group_id -> previous_runway
            group_prev_runway = {}

            # Initialize starting distance (6 NM) for each group
            for group_id in set(runway_groups.values()):
                group_distances[group_id] = 6
                group_prev_runway[group_id] = None
        else:
            # With spawn delays, use fixed 6 NM final approach position
            group_distances = {}
            group_prev_runway = {}

        while num_arrivals_created < num_arrivals and attempts < max_attempts:
            runway_name = active_runways[num_arrivals_created % len(active_runways)]

            # If using spawn delays, all aircraft at 6 NM (spacing controlled by spawn delays)
            if spawn_delay_mode != SpawnDelayMode.NONE or spawn_delay_range:
                distance_nm = 6
            else:
                # Determine which group this runway belongs to
                group_id = runway_groups.get(runway_name)

                # If runway not in any group, give it a unique group ID
                if group_id is None:
                    # Create unique group for this independent runway
                    group_id = f"independent_{runway_name}"
                    if group_id not in group_distances:
                        group_distances[group_id] = 6
                        group_prev_runway[group_id] = None
                        logger.info(f"Runway {runway_name} is independent (not parallel/crossing), using its own distance counter")

                # Get this group's current distance and previous runway
                current_distance = group_distances[group_id]
                prev_runway = group_prev_runway[group_id]

                # Simple iterative algorithm:
                # 1. First aircraft in group starts at current_distance (6 NM)
                # 2. Each subsequent aircraft adds separation increment based on runway pairing
                # 3. Add fixed additional separation on top of minimum
                if prev_runway is not None:
                    # Calculate minimum increment based on runway transition
                    min_increment = self._calculate_runway_separation_increment(
                        prev_runway, runway_name, parallel_info
                    )
                    # Add fixed additional separation on top of minimum
                    increment = min_increment + additional_separation
                    current_distance += increment
                    if additional_separation > 0:
                        logger.info(f"Group {group_id}: Runway transition {prev_runway} -> {runway_name}: "
                                   f"minimum {min_increment} NM + additional {additional_separation} NM = {increment} NM total "
                                   f"(new distance: {current_distance} NM)")
                    else:
                        logger.info(f"Group {group_id}: Runway transition {prev_runway} -> {runway_name}: "
                                   f"{increment} NM (new distance: {current_distance} NM)")
                else:
                    logger.info(f"Group {group_id}: First aircraft on {runway_name} at {current_distance} NM")

                distance_nm = current_distance

                # Update group's distance and previous runway
                group_distances[group_id] = current_distance
                group_prev_runway[group_id] = runway_name

            aircraft = self._create_arrival_aircraft(runway_name, distance_nm)
            if aircraft is not None:
                # Legacy mode: apply random spawn delay
                if spawn_delay_range and not delay_value:
                    aircraft.spawn_delay = random.randint(min_delay, max_delay)
                    logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                self.aircraft.append(aircraft)
                num_arrivals_created += 1

            attempts += 1

        if num_arrivals_created < num_arrivals:
            logger.warning(f"Only created {num_arrivals_created} of {num_arrivals} requested arrivals after {max_attempts} attempts")

        # Generate VFR aircraft if requested
        if num_vfr > 0:
            logger.info(f"Generating {num_vfr} VFR aircraft")
            vfr_aircraft = self._generate_vfr_aircraft(num_vfr, vfr_spawn_locations or [], active_runways, difficulty_list, difficulty_index)
            self.aircraft.extend(vfr_aircraft)

        # Apply new spawn delay system
        if not spawn_delay_range:
            self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        # Count actual aircraft by type
        num_departures_actual = sum(1 for a in self.aircraft if a.departure == self.airport_icao)
        num_arrivals_actual = sum(1 for a in self.aircraft if a.arrival == self.airport_icao and a.flight_rules == 'I')
        num_vfr_actual = sum(1 for a in self.aircraft if a.flight_rules == 'V')

        logger.info(f"Generated {len(self.aircraft)} total aircraft: "
                   f"{num_departures_actual} departures (requested {num_departures}), "
                   f"{num_arrivals_actual} arrivals (requested {num_arrivals}), "
                   f"{num_vfr_actual} VFR (requested {num_vfr})")

        # Only add warning if we couldn't generate the requested number of departures
        if num_departures_actual < num_departures:
            shortage = num_departures - num_departures_actual
            warning_msg = f"Generated {num_departures_actual}/{num_departures} departures. Missing {shortage}."

            # Show detailed failure reasons for failed gates
            if failed_gates and shortage <= len(failed_gates):
                logger.warning(warning_msg)
                logger.warning(f"Gate assignment failures ({len(failed_gates)} gates):")
                # Group gates by failure reason
                failures_by_reason = defaultdict(list)
                for gate in failed_gates:
                    reason = self.gate_failure_reasons.get(gate, "Unknown reason")
                    failures_by_reason[reason].append(gate)

                # Log each failure type with its gates
                for reason, gates in sorted(failures_by_reason.items()):
                    gate_list = ', '.join(gates[:10])
                    if len(gates) > 10:
                        gate_list += f" (and {len(gates) - 10} more)"
                    logger.warning(f"  {reason}: {gate_list}")

            else:
                logger.warning(warning_msg)

            self.gate_assignment_warnings.append(warning_msg)

        return self.aircraft

    def _create_arrival_aircraft(self, runway_name: str, distance_nm: float) -> Aircraft:
        """
        Create an arrival aircraft on final approach using cached flight data

        Args:
            runway_name: Runway designator
            distance_nm: Distance from runway threshold in nautical miles

        Returns:
            Aircraft object
        """
        # Get flight from pool
        flight_data = self._get_next_arrival_flight()

        if not flight_data:
            logger.error("No flight data available for arrival aircraft")
            return None

        # Extract data from API flight
        departure = flight_data.get('departureAirport', self._get_random_destination(exclude=self.airport_icao))
        raw_route = flight_data.get('route', '')
        route = clean_route_string(raw_route)
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

        # ALWAYS use API callsign to keep data matched - never generate
        if api_callsign and api_callsign.strip():
            callsign = api_callsign
        else:
            logger.warning(f"Arrival from {departure} missing callsign from API, generating one")
            callsign = self._generate_callsign()

        # Ensure callsign is unique
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                # If from API, skip this flight to maintain data integrity
                if api_callsign and api_callsign.strip():
                    logger.warning(f"Duplicate arrival callsign from API: {callsign}, skipping this flight")
                    return None
                # Otherwise generate new callsign (only for fallback)
                while callsign in self.used_callsigns:
                    callsign = self._generate_callsign()
            self.used_callsigns.add(callsign)

        # Ensure equipment suffix (/L for airlines, /G for GA)
        is_ga_type = self._is_ga_aircraft_type(api_aircraft_type)
        aircraft_type = self._add_equipment_suffix(api_aircraft_type, is_ga_type)

        # Calculate appropriate final approach speed based on aircraft type
        ground_speed = self._get_final_approach_speed(aircraft_type)

        # Use vNAS "On Final" starting condition - vNAS automatically positions aircraft
        # We only need to set arrival_runway and arrival_distance_nm
        # vNAS handles altitude, position, and heading based on the runway and distance
        logger.info(f"Creating arrival: {callsign} on final {runway_name}, {distance_nm:.1f} NM out at {ground_speed} knots")

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=0.0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            longitude=0.0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            altitude=0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            heading=0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            ground_speed=ground_speed,
            departure=departure,
            arrival=self.airport_icao,
            route=route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            flight_rules=flight_data.get('initialFlightRules', 'I')[0] if flight_data.get('initialFlightRules') else 'I',
            engine_type="J",
            arrival_runway=runway_name,
            arrival_distance_nm=distance_nm,
            # Additional API fields
            gufi=flight_data.get('gufi'),
            registration=flight_data.get('registration'),
            operator=flight_data.get('operator'),
            estimated_arrival_time=flight_data.get('estimatedArrivalTime'),
            wake_turbulence=flight_data.get('wakeTurbulence')
        )

        return aircraft

    def _get_final_approach_speed(self, aircraft_type: str) -> int:
        """
        Calculate appropriate final approach speed based on aircraft type

        Args:
            aircraft_type: Aircraft type code (e.g., 'B738', 'C172')

        Returns:
            Ground speed in knots appropriate for final approach
        """
        from utils.constants import COMMON_GA_AIRCRAFT

        # Extract base aircraft type (remove suffix like /L)
        base_type = aircraft_type.split('/')[0]

        # GA aircraft fly slower approach speeds (70-90 knots)
        if base_type in COMMON_GA_AIRCRAFT:
            return random.randint(70, 90)

        # Heavy jets (B744, B77W, B788, etc.) fly faster approaches (145-160 knots)
        heavy_jets = ['B744', 'B77W', 'B788', 'B789', 'A359', 'B763', 'A333', 'A332', 'B772']
        if base_type in heavy_jets:
            return random.randint(145, 160)

        # Standard jets (B738, A320, etc.) fly medium approach speeds (135-150 knots)
        return random.randint(135, 150)

    def _generate_vfr_aircraft(self, num_vfr: int, vfr_spawn_locations: List[str],
                               active_runways: List[str], difficulty_list: List[str],
                               difficulty_index: int) -> List[Aircraft]:
        """
        Generate VFR GA aircraft at specified or random FRD positions.

        Args:
            num_vfr: Number of VFR aircraft to generate
            vfr_spawn_locations: Optional list of FRD strings (e.g., ["KABQ020010", "KABQ090012"])
            active_runways: List of active runways
            difficulty_list: List of difficulty levels for assignment
            difficulty_index: Current index in difficulty list

        Returns:
            List of generated VFR Aircraft objects
        """
        from utils.geo_utils import calculate_destination, calculate_bearing

        vfr_aircraft = []

        # Determine spawn locations
        if vfr_spawn_locations and len(vfr_spawn_locations) > 0:
            # User provided FRD locations - parse them
            spawn_frds = []
            for frd_string in vfr_spawn_locations:
                try:
                    frd = self._parse_frd_string(frd_string)
                    spawn_frds.append(frd)
                except ValueError as e:
                    logger.warning(f"Invalid FRD string '{frd_string}': {e}")
                    continue

            if not spawn_frds:
                logger.warning("No valid FRD locations provided, using random generation")
                spawn_frds = [self._generate_random_frd() for _ in range(num_vfr)]
        else:
            # Generate random FRD locations
            spawn_frds = [self._generate_random_frd() for _ in range(num_vfr)]

        # Distribute aircraft across spawn locations
        for i in range(num_vfr):
            # Select spawn location (distribute evenly across available locations)
            frd = spawn_frds[i % len(spawn_frds)]

            # Retry up to 10 times if aircraft creation fails (e.g., duplicate callsign)
            aircraft = None
            attempts = 0
            max_attempts = 10
            while aircraft is None and attempts < max_attempts:
                aircraft = self._create_vfr_aircraft(frd, active_runways)
                attempts += 1

            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                vfr_aircraft.append(aircraft)
            else:
                logger.warning(f"Failed to create VFR aircraft at FRD position {i+1} after {max_attempts} attempts")

        logger.info(f"Generated {len(vfr_aircraft)} VFR aircraft at {len(spawn_frds)} spawn location(s)")
        return vfr_aircraft

    def _create_vfr_aircraft(self, frd: tuple, active_runways: List[str] = None) -> Aircraft:
        """
        Create a single VFR GA aircraft at the specified FRD position.

        Args:
            frd: Tuple of (fix_name, radial, distance_nm)
            active_runways: List of active runways (for destination selection)

        Returns:
            Aircraft object or None if creation failed
        """
        from utils.geo_utils import calculate_destination, calculate_bearing
        from utils.constants import COMMON_GA_AIRCRAFT

        fix_name, radial, distance_nm = frd

        # Generate GA callsign
        callsign = self._generate_ga_callsign()

        # Check callsign uniqueness
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                logger.warning(f"Duplicate VFR callsign: {callsign}, skipping")
                return None
            self.used_callsigns.add(callsign)

        # Random GA aircraft type
        aircraft_type_base = random.choice(COMMON_GA_AIRCRAFT)
        aircraft_type = self._add_equipment_suffix(aircraft_type_base, is_ga=True)

        # Get fix coordinates
        try:
            fix_lat, fix_lon = self._get_fix_coordinates(fix_name)
        except ValueError as e:
            logger.error(f"Cannot create VFR aircraft: {e}")
            return None

        # Calculate aircraft position from FRD
        # Aircraft is at distance_nm from fix on the specified radial
        aircraft_lat, aircraft_lon = calculate_destination(fix_lat, fix_lon, radial, distance_nm)

        # Get airport center for heading calculation
        airport_lat, airport_lon = self.geojson_parser.get_airport_center()

        # Calculate heading TO airport (direct)
        heading_to_airport = calculate_bearing(aircraft_lat, aircraft_lon, airport_lat, airport_lon)

        # Altitude: 1000 ft AGL
        field_elevation = self.geojson_parser.field_elevation
        altitude = field_elevation + 1000

        # VFR speeds (90-120 kts)
        ground_speed = random.randint(90, 120)
        cruise_speed = random.randint(100, 130)

        # Random departure airport
        departure = self._get_random_destination(exclude=self.airport_icao, less_common=True)

        # Construct FRD string for spawn point (e.g., "KPHX020010")
        frd_string = f"{fix_name}{radial:03d}{distance_nm:03d}"

        # Create aircraft
        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=aircraft_lat,
            longitude=aircraft_lon,
            altitude=altitude,
            heading=heading_to_airport,
            ground_speed=ground_speed,
            departure=departure,
            arrival=self.airport_icao,
            route='DCT',  # Direct
            cruise_speed=cruise_speed,
            cruise_altitude=str(altitude),
            flight_rules='V',  # VFR
            engine_type='P',  # Piston
            fix=frd_string,  # Spawn point - FRD string showing where aircraft spawned
            navigation_path=self.airport_icao,  # Route - airport where aircraft is going
            starting_conditions_type="Standard"  # Using actual lat/lon
        )

        logger.debug(f"Created VFR aircraft {callsign} at {fix_name} radial {radial:03d}, {distance_nm}NM, heading {heading_to_airport:03d}° to {self.airport_icao}")
        return aircraft
