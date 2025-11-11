"""
TRACON (Arrivals) scenario - Simplified implementation
"""
import re
import logging
from typing import List, Dict
from collections import defaultdict

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.flight_data_filter import filter_valid_flights, clean_route_string
from utils.geo_utils import calculate_bearing, calculate_destination, get_reciprocal_heading

logger = logging.getLogger(__name__)


class TraconArrivalsScenario(BaseScenario):
    """Scenario for TRACON with arrivals only"""

    def generate(self, num_arrivals: int, arrival_waypoints: List[str],
                 delay_range=None, spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None, active_runways: List[str] = None) -> List[Aircraft]:
        """
        Generate TRACON arrival scenario

        Args:
            num_arrivals: Number of arrival aircraft
            arrival_waypoints: List in format "WAYPOINT.STAR" (e.g., ["HOMRR.EAGUL6", "HYDRR.HYDRR1"])
            spawn_delay_mode: SpawnDelayMode enum (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: delay range/value in minutes
            total_session_minutes: For TOTAL mode: total session length in minutes
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts
            active_runways: List of active runway designators

        Returns:
            List of Aircraft objects
        """
        # Reset tracking for new generation
        self._reset_tracking()

        logger.info(f"Generating TRACON arrival scenario: {num_arrivals} arrivals")

        # Parse waypoint.STAR input
        waypoint_star_pairs = self._parse_waypoint_star_input(arrival_waypoints)
        if not waypoint_star_pairs:
            logger.error("No valid STAR waypoints provided")
            return []

        # Extract unique STAR base names for API call
        star_names = list(set([self._strip_numbers(star) for _, star in waypoint_star_pairs]))
        logger.info(f"Fetching flights for STARs: {star_names}")

        # Single API call to get ALL arrival flights
        all_flights = self.api_client.fetch_arrivals(self.airport_icao, limit=619, stars=star_names)
        if not all_flights:
            logger.error("Failed to fetch arrival flights from API")
            return []

        # Filter valid flights (removes ACTIVE status, missing data, etc.)
        valid_flights = filter_valid_flights(all_flights)
        logger.info(f"Got {len(valid_flights)} valid flights from API")

        # Deduplicate by GUFI
        unique_flights = self._deduplicate_by_gufi(valid_flights)
        logger.info(f"After deduplication: {len(unique_flights)} unique flights")

        # Separate flights by STAR procedure
        flights_by_star = self._group_flights_by_star(unique_flights)

        # Log what we have
        for star, flights in flights_by_star.items():
            logger.info(f"  {star}: {len(flights)} flights")

        # Calculate how many aircraft per STAR
        num_stars = len(waypoint_star_pairs)
        aircraft_per_star = num_arrivals // num_stars
        remainder = num_arrivals % num_stars

        logger.info(f"Will generate {aircraft_per_star} aircraft per STAR (+ {remainder} extra)")

        # Setup difficulty assignment
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        # Generate aircraft for each waypoint.STAR pair
        for idx, (waypoint_name, star_name) in enumerate(waypoint_star_pairs):
            star_base = self._strip_numbers(star_name)

            # Calculate how many for this STAR (distribute remainder to first STARs)
            num_for_this_star = aircraft_per_star + (1 if idx < remainder else 0)

            logger.info(f"Generating {num_for_this_star} aircraft for {waypoint_name}.{star_name}")

            # Get flights for this STAR
            available_flights = flights_by_star.get(star_base.upper(), [])
            if not available_flights:
                logger.warning(f"No flights available for STAR {star_base}")
                continue

            # Get waypoint from CIFP
            waypoint = self.cifp_parser.get_transition_waypoint(waypoint_name, star_name)
            if not waypoint:
                logger.warning(f"Waypoint {waypoint_name} not found in CIFP for {star_name}")
                continue

            # Generate aircraft with retry logic
            created = 0
            attempts = 0
            max_attempts = num_for_this_star * 10

            while created < num_for_this_star and attempts < max_attempts:
                flight_index = attempts % len(available_flights)

                # If we've exhausted the available flights, try to fetch more
                if attempts > 0 and attempts % len(available_flights) == 0:
                    logger.info(f"Flight pool exhausted for STAR {star_base}, fetching more from API...")
                    additional_flights = self.api_client.fetch_arrivals(self.airport_icao, limit=100, stars=[star_base.upper()])
                    if additional_flights:
                        valid_flights = filter_valid_flights(additional_flights)
                        unique_flights = self._deduplicate_by_gufi(valid_flights)
                        if unique_flights:
                            available_flights.extend(unique_flights)
                            flights_by_star[star_base.upper()] = available_flights
                            logger.info(f"Added {len(unique_flights)} more flights for STAR {star_base}")

                if flight_index >= len(available_flights):
                    logger.warning(f"No more flights available for STAR {star_base}")
                    break

                flight_data = available_flights[flight_index]

                aircraft = self._create_arrival_aircraft(
                    flight_data=flight_data,
                    waypoint=waypoint,
                    star_name=star_name,
                    active_runways=active_runways
                )

                if aircraft:
                    difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                    self.aircraft.append(aircraft)
                    created += 1

                attempts += 1

            if created < num_for_this_star:
                logger.warning(f"Only created {created} of {num_for_this_star} requested aircraft for {waypoint_name}.{star_name}")

        # Apply spawn delays
        self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} arrival aircraft (requested {num_arrivals})")
        return self.aircraft

    def _parse_waypoint_star_input(self, arrival_waypoints: List[str]) -> List[tuple]:
        """
        Parse waypoint.STAR input format

        Args:
            arrival_waypoints: List like ["HOMRR.EAGUL6", "HYDRR.HYDRR1"]

        Returns:
            List of (waypoint, star) tuples
        """
        pairs = []
        for item in arrival_waypoints:
            if '.' in item:
                parts = item.split('.')
                if len(parts) == 2:
                    waypoint, star = parts
                    pairs.append((waypoint.strip().upper(), star.strip().upper()))
                else:
                    logger.warning(f"Invalid format: {item} (expected WAYPOINT.STAR)")
            else:
                logger.warning(f"Invalid format: {item} (expected WAYPOINT.STAR)")

        return pairs

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
                unique.append(flight)  # Keep flights without GUFI
        return unique

    def _group_flights_by_star(self, flights: List[Dict]) -> Dict[str, List[Dict]]:
        """Group flights by their arrivalProcedure field"""
        groups = defaultdict(list)
        for flight in flights:
            star = flight.get('arrivalProcedure', 'UNKNOWN').upper()
            groups[star].append(flight)
        return dict(groups)

    def _create_arrival_aircraft(self, flight_data: Dict, waypoint, star_name: str,
                                  active_runways: List[str] = None) -> Aircraft:
        """
        Create arrival aircraft from flight data

        Args:
            flight_data: Flight dictionary from API
            waypoint: Waypoint object from CIFP
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
            starting_conditions_type="FixOrFrd",
            # Procedures
            star=star_name  # Store the STAR name
        )

        return aircraft

    def _get_altitude_from_cifp(self, waypoint, star_name: str) -> int:
        """
        Get altitude from CIFP waypoint data

        Args:
            waypoint: Waypoint object from CIFP
            star_name: STAR name

        Returns:
            Altitude in feet MSL
        """
        # If waypoint has both min and max, use max (aircraft typically enter at top of window)
        if waypoint.max_altitude:
            return waypoint.max_altitude

        # If only min_altitude, use that
        if waypoint.min_altitude:
            return waypoint.min_altitude

        # Default for TRACON arrivals (typically 11,000 ft)
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
        # Try to get from CIFP
        if waypoint.inbound_course:
            return int(waypoint.inbound_course)

        # Try to calculate from previous waypoint
        if star_name and waypoint.sequence_number:
            prev_waypoint = self.cifp_parser.get_previous_waypoint_in_star(star_name, waypoint.sequence_number)
            if prev_waypoint and prev_waypoint.latitude and prev_waypoint.longitude:
                heading = calculate_bearing(
                    prev_waypoint.latitude, prev_waypoint.longitude,
                    waypoint.latitude, waypoint.longitude
                )
                return int(heading)

        # Default
        return 200

    def _get_cruise_speed(self, flight_data: Dict, aircraft_type: str) -> int:
        """Get cruise speed from flight data or calculate default"""
        speed_str = flight_data.get('requestedAirspeed', '')
        if speed_str:
            try:
                return int(float(speed_str))
            except (ValueError, TypeError):
                pass

        # Default based on aircraft type
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
