"""
TRACON (Departures/Arrivals) scenario
"""
import re
import random
import logging
from typing import List, Tuple, Dict
from collections import defaultdict

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.geo_utils import calculate_bearing, calculate_destination, get_reciprocal_heading
from utils.flight_data_filter import filter_valid_flights, clean_route_string

logger = logging.getLogger(__name__)


class TraconMixedScenario(BaseScenario):
    """Scenario for TRACON with both departures and arrivals"""

    def generate(self, num_departures: int, num_arrivals: int, arrival_waypoints: List[str],
                 delay_range: Tuple[int, int] = (4, 7),
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None, active_runways: List[str] = None,
                 enable_cifp_sids: bool = False, manual_sids: List[str] = None) -> List[Aircraft]:
        """
        Generate TRACON mixed scenario

        Args:
            num_departures: Number of departure aircraft
            num_arrivals: Number of arrival aircraft
            arrival_waypoints: List of STAR waypoints in format "WAYPOINT.STAR"
                              Can be ANY waypoint along the STAR, not just transitions
                              (e.g., "EAGUL.JESSE3", "PINNG.PINNG1", "HOTTT.PINNG1")
            delay_range: Tuple of (min, max) spawn delay in minutes between aircraft
            spawn_delay_mode: SpawnDelayMode enum (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: delay range/value in minutes (e.g., "2-5" or "3")
            total_session_minutes: For TOTAL mode: total session length in minutes
            spawn_delay_range: LEGACY parameter - kept for backward compatibility
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts for difficulty levels
            active_runways: List of active runway designators
            enable_cifp_sids: Whether to use CIFP SID procedures
            manual_sids: Optional list of specific SIDs to use

        Returns:
            List of Aircraft objects
        """
        # Reset tracking for new generation
        self._reset_tracking()

        # Prepare flight pools from cached data (departures only)
        logger.info("Preparing departure flight pools...")
        self._prepare_departure_flight_pool(active_runways, enable_cifp_sids, manual_sids)
        self._prepare_ga_flight_pool()

        # Parse STAR transitions for arrivals
        star_transitions = self._parse_star_transitions(arrival_waypoints, active_runways)

        # Fetch and prepare arrival flights using new simplified approach
        flights_by_star = {}
        if star_transitions:
            star_names = list(set([self._strip_numbers(star) for _, star in star_transitions if star]))
            logger.info(f"Fetching flights for STARs: {star_names}")

            # Single API call to get ALL arrival flights
            all_flights = self.api_client.fetch_arrivals(self.airport_icao, limit=619, stars=star_names)
            if all_flights:
                # Filter valid flights (removes ACTIVE status, missing data, etc.)
                valid_flights = filter_valid_flights(all_flights)
                logger.info(f"Got {len(valid_flights)} valid arrival flights from API")

                # Deduplicate by GUFI
                unique_flights = self._deduplicate_by_gufi(valid_flights)
                logger.info(f"After deduplication: {len(unique_flights)} unique arrival flights")

                # Group by STAR
                flights_by_star = self._group_flights_by_star(unique_flights)
                for star, flights in flights_by_star.items():
                    logger.info(f"  {star}: {len(flights)} flights")
            else:
                logger.warning("Failed to fetch arrival flights from API")
        else:
            logger.info("No STAR transitions specified for arrivals")

        # Setup difficulty assignment
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        # Handle legacy spawn_delay_range parameter
        if spawn_delay_range and not delay_value:
            logger.warning("Using legacy spawn_delay_range parameter. Consider upgrading to spawn_delay_mode.")
            min_delay, max_delay = self._parse_spawn_delay_range(spawn_delay_range)

        parking_spots = self.geojson_parser.get_parking_spots()

        if num_departures > len(parking_spots):
            raise ValueError(
                f"Cannot create {num_departures} departures - only {len(parking_spots)} parking spots available at {self.airport_icao}. "
                f"Please reduce the number of departures to {len(parking_spots)} or fewer."
            )

        logger.info(f"Generating TRACON mixed scenario: {num_departures} departures, {num_arrivals} arrivals")

        # Generate departures, trying more spots if needed
        attempts = 0
        max_attempts = len(parking_spots) * 2
        available_spots = parking_spots.copy()

        while len(self.aircraft) < num_departures and attempts < max_attempts and available_spots:
            spot = random.choice(available_spots)
            available_spots.remove(spot)

            # Check if parking spot is for GA (has "GA" in the name)
            if "GA" in spot.name.upper():
                logger.info(f"Creating GA aircraft for parking spot: {spot.name}")
                aircraft = self._create_ga_aircraft(spot)
            else:
                aircraft = self._create_departure_aircraft(
                    spot,
                    active_runways=active_runways,
                    enable_cifp_sids=enable_cifp_sids,
                    manual_sids=manual_sids
                )

            if aircraft is not None:
                # Legacy mode: apply random spawn delay
                if spawn_delay_range and not delay_value:
                    aircraft.spawn_delay = random.randint(min_delay, max_delay)
                    logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                self.aircraft.append(aircraft)

            attempts += 1

        # Generate arrivals at waypoints using new simplified approach
        if not star_transitions:
            logger.warning("No valid STAR waypoints provided for arrivals")
        else:
            # Track which flight index we're using for each STAR
            star_flight_indices = defaultdict(int)

            arrivals_created = 0
            attempts = 0
            max_attempts = num_arrivals * 3  # Allow 3x attempts to handle missing data/waypoints

            while arrivals_created < num_arrivals and attempts < max_attempts:
                waypoint_name, star_name = star_transitions[attempts % len(star_transitions)]

                # Get waypoint for this STAR
                waypoint = self.cifp_parser.get_transition_waypoint(waypoint_name, star_name)

                if not waypoint:
                    logger.warning(f"Waypoint {waypoint_name}.{star_name} not found in CIFP data")
                    attempts += 1
                    continue

                # Check if waypoint has valid coordinates
                if waypoint.latitude == 0.0 and waypoint.longitude == 0.0:
                    logger.warning(f"Waypoint {waypoint.name} has no coordinate data")
                    attempts += 1
                    continue

                # Get flights for this STAR
                star_base = self._strip_numbers(star_name).upper() if star_name else None
                available_flights = flights_by_star.get(star_base, []) if star_base else []

                if not available_flights:
                    logger.warning(f"No flights available for STAR {star_base}")
                    attempts += 1
                    continue

                # Get next unused flight for this STAR
                flight_index = star_flight_indices[star_base]
                if flight_index >= len(available_flights):
                    logger.warning(f"Exhausted all flights for STAR {star_base}")
                    attempts += 1
                    continue

                flight_data = available_flights[flight_index]
                star_flight_indices[star_base] += 1

                # Create aircraft from flight data
                aircraft = self._create_arrival_at_waypoint(waypoint, flight_data, star_name, active_runways)
                if aircraft is not None:
                    # Legacy mode: apply random spawn delay
                    if spawn_delay_range and not delay_value:
                        aircraft.spawn_delay = random.randint(min_delay, max_delay)
                        logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
                    difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                    self.aircraft.append(aircraft)
                    arrivals_created += 1

                attempts += 1

            if arrivals_created < num_arrivals:
                logger.warning(f"Could only generate {arrivals_created}/{num_arrivals} arrivals after {attempts} attempts (limited API data or missing waypoints)")

        # Apply new spawn delay system
        if not spawn_delay_range:
            self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} total aircraft")
        return self.aircraft

    def _create_arrival_at_waypoint(self, waypoint, flight_data: Dict, star_name: str, active_runways: List[str] = None) -> Aircraft:
        """
        Create an arrival aircraft at a waypoint

        Args:
            waypoint: Waypoint object from CIFP
            flight_data: Flight dictionary from API
            star_name: STAR name (with numbers)
            active_runways: List of active runways

        Returns:
            Aircraft object or None
        """
        # Extract flight data
        departure = flight_data.get('departureAirport', 'KORD')
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        route = clean_route_string(flight_data.get('route', ''))

        # Check callsign uniqueness
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                logger.warning(f"Duplicate callsign {callsign}, skipping")
                return None
            self.used_callsigns.add(callsign)

        # Add equipment suffix
        is_ga = self._is_ga_aircraft_type(aircraft_type)
        aircraft_type = self._add_equipment_suffix(aircraft_type, is_ga)

        # Get altitude from CIFP
        altitude = self._get_altitude_from_cifp(waypoint, star_name)

        # Get cruise speed (for flight plan only, not initial speed)
        cruise_speed = self._get_cruise_speed(flight_data, aircraft_type)

        # Calculate realistic initial speed based on altitude
        initial_speed = self._calculate_realistic_arrival_speed(altitude, aircraft_type)

        # Determine runway
        runway = self._select_arrival_runway(active_runways, star_name) if active_runways else "08L"

        # Calculate FRD fix string (FIX/RADIAL/DISTANCE format)
        frd_fix = self._calculate_frd_fix(waypoint, star_name, runway)

        # Calculate initial path (spawn waypoint.STAR.RUNWAY)
        initial_path = self._calculate_initial_path(waypoint, star_name, runway)

        # Create aircraft with FixOrFrd starting conditions
        # vNAS will calculate lat/lon/heading from the FRD fix
        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=0.0,  # vNAS calculates from FRD
            longitude=0.0,  # vNAS calculates from FRD
            altitude=altitude,
            heading=0,  # vNAS calculates from FRD
            ground_speed=initial_speed,  # Realistic speed based on altitude
            departure=departure,
            arrival=self.airport_icao,
            route=route,
            cruise_speed=cruise_speed,
            cruise_altitude=str(altitude),
            navigation_path=initial_path,
            fix=frd_fix,
            starting_conditions_type="FixOrFrd"
        )

        return aircraft

    def _get_altitude_from_cifp(self, waypoint, star_name: str) -> int:
        """Get altitude from CIFP waypoint data"""
        if waypoint.max_altitude:
            return waypoint.max_altitude
        if waypoint.min_altitude:
            return waypoint.min_altitude
        return 11000

    def _calculate_realistic_arrival_speed(self, altitude: int, aircraft_type: str) -> int:
        """
        Calculate realistic arrival speed based on altitude.

        Uses an exponential relationship where speed increases with altitude.
        Higher altitudes = higher speeds (descending jets at 280-300 kts)
        Lower altitudes = lower speeds (approach speeds 140-180 kts)

        Args:
            altitude: Altitude in feet MSL
            aircraft_type: Aircraft type code

        Returns:
            Speed in knots
        """
        # Determine if this is a GA aircraft
        is_ga = self._is_ga_aircraft_type(aircraft_type.split('/')[0])

        if is_ga:
            # General aviation speeds are lower
            # Base: 120 kts, increases to ~180 kts at high altitude
            base_speed = 110
            max_speed = 170
        else:
            # Jet/turboprop speeds
            # Base: 180 kts (approach speed), increases to ~290 kts at cruise descent
            base_speed = 140
            max_speed = 380

        # Exponential formula: speed = base + (max - base) * (1 - e^(-altitude / scale))
        # Scale factor controls how quickly speed increases with altitude
        scale_factor = 8000  # Altitude in feet where speed reaches ~63% of max

        import math
        speed_ratio = 1 - math.exp(-altitude / scale_factor)
        calculated_speed = base_speed + (max_speed - base_speed) * speed_ratio

        # Round to nearest 5 knots for realism
        speed = int(round(calculated_speed / 5) * 5)

        logger.debug(f"Calculated arrival speed: {speed} kts for altitude {altitude} ft (aircraft: {aircraft_type})")
        return speed

    def _find_next_waypoint_for_runway(self, star_name: str, current_waypoint, runway: str):
        """
        Find the correct next waypoint in a STAR based on the runway assignment.

        Uses CIFP transition_name field to determine which waypoint path serves
        the specified runway. Works for any STAR procedure at any airport.

        Args:
            star_name: STAR name (with numbers)
            current_waypoint: Current waypoint object
            runway: Target runway (e.g., "08L", "25R")

        Returns:
            Next waypoint object, or None if not found
        """
        if not current_waypoint.sequence_number:
            return None

        # Get all waypoints at the next sequence number
        next_sequence = current_waypoint.sequence_number + 10
        candidate_waypoints = []

        if star_name in self.cifp_parser.star_waypoints:
            for waypoint_name, waypoint in self.cifp_parser.star_waypoints[star_name].items():
                if waypoint.sequence_number == next_sequence:
                    # Get coordinates from global waypoints if needed
                    if waypoint.latitude == 0.0 and waypoint.longitude == 0.0:
                        if waypoint_name in self.cifp_parser.waypoints:
                            waypoint.latitude = self.cifp_parser.waypoints[waypoint_name].latitude
                            waypoint.longitude = self.cifp_parser.waypoints[waypoint_name].longitude
                    candidate_waypoints.append((waypoint_name, waypoint))

        if not candidate_waypoints:
            logger.debug(f"No waypoints found at sequence {next_sequence} in {star_name}")
            return None

        # If only one candidate, return it
        if len(candidate_waypoints) == 1:
            return candidate_waypoints[0][1]

        # Multiple candidates - use CIFP transition_name to match runway
        # Normalize runway for comparison (e.g., "08L" -> "08L", "25R" -> "25R", "8" -> "08")
        runway_normalized = runway.replace('RW', '')

        # Pad single-digit runways with leading zero (8 -> 08, 8L -> 08L)
        if len(runway_normalized) >= 1 and runway_normalized[0].isdigit():
            if len(runway_normalized) == 1 or (len(runway_normalized) == 2 and not runway_normalized[1].isdigit()):
                # Single digit runway (8 or 8L) - pad with zero
                runway_normalized = '0' + runway_normalized

        # Build possible transition names to match
        # CIFP uses formats like "RW08", "RW08L", "RW25R", etc.
        possible_transitions = [
            f"RW{runway_normalized}",  # Exact: RW08L, RW25R
            f"RW{runway_normalized[:-1]}" if len(runway_normalized) > 2 else None,  # Base: RW08 (from 08L)
        ]

        logger.debug(f"Looking for waypoints with transition names: {[t for t in possible_transitions if t]}")

        # First pass: exact transition name match
        for waypoint_name, waypoint in candidate_waypoints:
            if waypoint.transition_name and waypoint.transition_name in possible_transitions:
                logger.debug(f"Found waypoint {waypoint_name} for runway {runway} (transition: {waypoint.transition_name})")
                return waypoint

        # Second pass: reverse base match (transition RW08 can serve runway 08L or 08R)
        # This handles cases where CIFP defines RW08 transition that serves both 08L and 08R
        runway_base = runway_normalized.rstrip('LRC')
        for waypoint_name, waypoint in candidate_waypoints:
            if waypoint.transition_name:
                trans_clean = waypoint.transition_name.replace('RW', '')
                trans_base = trans_clean.rstrip('LRC')

                # Check if transition base matches runway base
                if trans_base == runway_base:
                    logger.debug(f"Found waypoint {waypoint_name} for runway {runway} via base match (transition: {waypoint.transition_name})")
                    return waypoint

        # If no match found, log warning and return first candidate
        logger.warning(f"No CIFP transition match for runway {runway}. Available transitions: {[w.transition_name for n, w in candidate_waypoints if w.transition_name]}. Using first candidate: {candidate_waypoints[0][0]}")
        return candidate_waypoints[0][1]

    def _calculate_frd_fix(self, waypoint, star_name: str, runway: str) -> str:
        """
        Calculate FRD (Fix/Radial/Distance) string for vNAS starting conditions

        The radial is calculated from the lateral course of the arrival procedure:
        - If there's a previous waypoint, use bearing FROM previous TO current
        - If this is an entry/transition point, use bearing FROM current TO next waypoint
          (places aircraft on the arrival course leading into the STAR)
        - For STARs with multiple branches, uses the runway to determine correct path

        Format: WAYPOINTRADIALDISTANCE (no separators)
        Example: HOMRR02003 (3NM from HOMRR on the 020 radial)

        Args:
            waypoint: Waypoint object from CIFP
            star_name: STAR name (with numbers)
            runway: Runway designator (e.g., "08L", "25R")

        Returns:
            FRD string (e.g., "HOMRR02003")
        """
        distance_nm = 3  # Always 3 NM from the waypoint

        # Try to get the previous waypoint in the STAR to calculate actual lateral course
        inbound_course = None
        if waypoint.sequence_number:
            prev_waypoint = self.cifp_parser.get_previous_waypoint_in_star(star_name, waypoint.sequence_number)
            if prev_waypoint and prev_waypoint.latitude and prev_waypoint.longitude and waypoint.latitude and waypoint.longitude:
                # Calculate bearing from previous waypoint to current waypoint
                # This is the actual lateral course of the arrival TO this waypoint
                inbound_course = calculate_bearing(
                    prev_waypoint.latitude, prev_waypoint.longitude,
                    waypoint.latitude, waypoint.longitude
                )
                logger.debug(f"Calculated inbound course from previous {prev_waypoint.name} to {waypoint.name}: {inbound_course:.1f}°")
            else:
                # No previous waypoint - this is a transition/entry point
                # Use the next waypoint to determine the course that continues THROUGH the fix
                # For STARs with multiple branches, find the correct next waypoint for this runway
                next_waypoint = self._find_next_waypoint_for_runway(star_name, waypoint, runway)
                if next_waypoint and next_waypoint.latitude and next_waypoint.longitude and waypoint.latitude and waypoint.longitude:
                    # Calculate bearing from CURRENT to NEXT (the departure course from this fix)
                    # We'll spawn aircraft on this same course line, BEFORE reaching the fix
                    departure_course = calculate_bearing(
                        waypoint.latitude, waypoint.longitude,
                        next_waypoint.latitude, next_waypoint.longitude
                    )
                    # Use the departure course as the inbound course (aircraft arrive on same line)
                    inbound_course = departure_course
                    logger.debug(f"Using course from {waypoint.name} to next {next_waypoint.name} (for runway {runway}) as inbound: {inbound_course:.1f}°")

        # Fallback to waypoint's inbound_course field if we couldn't calculate
        if inbound_course is None:
            inbound_course = waypoint.inbound_course if waypoint.inbound_course else 200
            logger.debug(f"Using fallback inbound_course: {inbound_course}°")

        # Calculate the radial FROM the waypoint where aircraft is located
        # If flying inbound on course 200, aircraft is on the 020 radial FROM the fix
        radial_from_fix = get_reciprocal_heading(int(inbound_course))

        # Format: FIXRADIALDISTANCE (no slashes, radial=3 digits, distance=3 digits with leading zeros)
        frd_string = f"{waypoint.name}{radial_from_fix:03d}{distance_nm:03d}"
        logger.debug(f"FRD: {frd_string} ({distance_nm}NM from {waypoint.name} on {radial_from_fix:03d} radial)")
        return frd_string

    def _calculate_arrival_heading(self, waypoint, star_name: str) -> int:
        """Calculate initial heading for arrival"""
        if waypoint.inbound_course:
            return int(waypoint.inbound_course)
        if star_name and waypoint.sequence_number:
            prev_waypoint = self.cifp_parser.get_previous_waypoint_in_star(star_name, waypoint.sequence_number)
            if prev_waypoint and prev_waypoint.latitude and prev_waypoint.longitude:
                heading = calculate_bearing(
                    prev_waypoint.latitude, prev_waypoint.longitude,
                    waypoint.latitude, waypoint.longitude
                )
                return int(heading)
        return 200

    def _get_cruise_speed(self, flight_data: Dict, aircraft_type: str) -> int:
        """Get cruise speed from flight data or calculate default"""
        speed_str = flight_data.get('requestedAirspeed', '')
        if speed_str:
            try:
                return int(float(speed_str))
            except (ValueError, TypeError):
                pass
        return self.api_client._calculate_cruise_speed(aircraft_type)

    def _select_arrival_runway(self, active_runways: List[str], star_name: str) -> str:
        """
        Select a runway for arrival based on STAR-runway mapping

        Args:
            active_runways: List of active runways
            star_name: STAR name (with numbers, e.g., "EAGUL6")

        Returns:
            Runway designator that matches both active runways and STAR
        """
        if not active_runways:
            return "08L"

        # Get runways that this STAR can feed (use full STAR name with numbers)
        star_runways = self.cifp_parser.get_runways_for_arrival(star_name)

        # Find first active runway that matches this STAR
        # Handle exact matches, base matches, and normalized number matches
        for active_rwy in active_runways:
            # Try exact match first
            if active_rwy in star_runways:
                return active_rwy

            # Normalize runway numbers for comparison (8 -> 08, 9 -> 09)
            active_base = active_rwy.rstrip('LRC')
            active_normalized = active_base.zfill(2) if active_base.isdigit() else active_base

            for star_rwy in star_runways:
                star_base = star_rwy.rstrip('LRC')
                star_normalized = star_base.zfill(2) if star_base.isdigit() else star_base

                # Compare normalized bases (handles "8" == "08", "08L" == "08", etc.)
                if active_normalized == star_normalized:
                    return active_rwy

        # Fallback: use first active runway
        logger.warning(f"No active runway matches STAR {star_name} runways {star_runways}, using {active_runways[0]}")
        return active_runways[0]

    def _calculate_initial_path(self, current_waypoint, star_name: str, runway: str) -> str:
        """
        Calculate the initial path for arrival aircraft

        Format: SPAWN_WAYPOINT STAR.RUNWAY
        Example: HOMRR EAGUL6.08L (with leading zeros)

        The aircraft spawns 3NM before this waypoint and flies toward it via this STAR to the runway.

        Args:
            current_waypoint: Spawn waypoint (where aircraft is spawning 3NM before)
            star_name: STAR name (with numbers)
            runway: Runway designator

        Returns:
            Initial path string in format "SPAWN_WAYPOINT STAR.RUNWAY"
        """
        # Format: SPAWN_WAYPOINT STAR.RUNWAY (space between waypoint and STAR)
        # Remove any RW prefix but preserve leading zeros (08L, not 8L)
        runway_clean = runway.replace('RW', '')

        initial_path = f"{current_waypoint.name} {star_name}.{runway_clean}"
        logger.debug(f"Initial path: {initial_path} (spawn 3NM before {current_waypoint.name})")
        return initial_path

    def _strip_numbers(self, procedure: str) -> str:
        """Strip trailing numbers from procedure name (EAGUL6 -> EAGUL)"""
        return re.sub(r'\d+$', '', procedure)

    def _deduplicate_by_gufi(self, flights: List[Dict]) -> List[Dict]:
        """Remove duplicate flights by GUFI"""
        seen = set()
        unique = []
        for flight in flights:
            gufi = flight.get('gufi', '')
            if gufi and gufi not in seen:
                seen.add(gufi)
                unique.append(flight)
            elif not gufi:
                unique.append(flight)
        return unique

    def _group_flights_by_star(self, flights: List[Dict]) -> Dict[str, List[Dict]]:
        """Group flights by their arrivalProcedure field"""
        groups = defaultdict(list)
        for flight in flights:
            star = flight.get('arrivalProcedure', 'UNKNOWN').upper()
            groups[star].append(flight)
        return dict(groups)

    def _parse_star_transitions(self, arrival_waypoints: List[str], active_runways: List[str] = None) -> List[Tuple[str, str]]:
        """
        Parse STAR waypoint input format

        Users can specify ANY waypoint along a STAR procedure, not just transition points.
        If no waypoints are specified, random STAR transitions will be selected from CIFP.

        Args:
            arrival_waypoints: List of strings in format "WAYPOINT.STAR"
                              (e.g., "EAGUL.JESSE3", "PINNG.PINNG1", "HOTTT.PINNG1")
                              If empty or None, random transitions will be selected
            active_runways: Optional list of active runways to filter random selection

        Returns:
            List of (waypoint_name, star_name) tuples
        """
        # If no waypoints specified, get random STAR transitions from CIFP
        if not arrival_waypoints or (len(arrival_waypoints) == 1 and not arrival_waypoints[0].strip()):
            logger.info("No STAR waypoints specified, selecting random transitions from CIFP")
            # Select 3-5 random transitions
            import random
            count = random.randint(3, 5)
            star_transitions = self.cifp_parser.get_random_star_transitions(count, active_runways)
            if star_transitions:
                logger.info(f"Auto-selected {len(star_transitions)} random STAR transitions: {star_transitions}")
                return star_transitions
            else:
                logger.error("No STAR transitions available in CIFP data")
                return []

        star_transitions = []

        for entry in arrival_waypoints:
            entry = entry.strip()
            if not entry:
                continue

            # Check if it's in WAYPOINT.STAR format
            if '.' in entry:
                parts = entry.split('.')
                if len(parts) == 2:
                    waypoint_name = parts[0].strip()
                    star_name = parts[1].strip()

                    # If STAR part is empty, it means waypoint-only filtering
                    if not star_name:
                        star_transitions.append((waypoint_name, None))
                        logger.debug(f"Parsed waypoint-only filter: {waypoint_name}")
                    else:
                        star_transitions.append((waypoint_name, star_name))
                        logger.debug(f"Parsed STAR waypoint: {waypoint_name}.{star_name}")
                else:
                    logger.warning(f"Invalid STAR waypoint format: {entry} (expected WAYPOINT.STAR)")
            else:
                # Waypoint-only format (no STAR specified)
                # This will match any STAR containing this waypoint
                star_transitions.append((entry, None))
                logger.debug(f"Parsed waypoint-only filter: {entry}")

        return star_transitions
