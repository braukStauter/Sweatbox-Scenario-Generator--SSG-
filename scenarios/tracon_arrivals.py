"""
TRACON (Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode

logger = logging.getLogger(__name__)


class TraconArrivalsScenario(BaseScenario):
    """Scenario for TRACON with arrivals only"""

    def generate(self, num_arrivals: int, arrival_waypoints: List[str],
                 altitude_range: Tuple[int, int] = (7000, 18000),
                 delay_range: Tuple[int, int] = (4, 7),
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None, active_runways: List[str] = None) -> List[Aircraft]:
        """
        Generate TRACON arrival scenario

        Args:
            num_arrivals: Number of arrival aircraft
            arrival_waypoints: List of STAR waypoints in format "WAYPOINT.STAR"
                              Can be ANY waypoint along the STAR, not just transitions
                              (e.g., "EAGUL.JESSE3", "PINNG.PINNG1", "HOTTT.PINNG1")
            altitude_range: Tuple of (min, max) altitude in feet (used as fallback only)
            delay_range: DEPRECATED - not used (kept for backward compatibility)
            spawn_delay_mode: SpawnDelayMode enum (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: delay range/value in minutes (e.g., "2-5" or "3")
            total_session_minutes: For TOTAL mode: total session length in minutes
            spawn_delay_range: LEGACY parameter - kept for backward compatibility
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts for difficulty levels
            active_runways: List of active runway designators

        Returns:
            List of Aircraft objects
        """
        # Reset tracking for new generation
        self._reset_tracking()

        # Setup difficulty assignment
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        # Handle legacy spawn_delay_range parameter
        if spawn_delay_range and not delay_value:
            logger.warning("Using legacy spawn_delay_range parameter. Consider upgrading to spawn_delay_mode.")
            min_delay, max_delay = self._parse_spawn_delay_range(spawn_delay_range)

        logger.info(f"Generating TRACON arrival scenario: {num_arrivals} arrivals")
        logger.info(f"Spawn delay mode: {spawn_delay_mode.value}")

        # Parse STAR transitions from input
        star_transitions = self._parse_star_transitions(arrival_waypoints)

        if not star_transitions:
            logger.error("No valid STAR transitions provided")
            return self.aircraft

        # Distribute aircraft across STAR transitions
        for i in range(num_arrivals):
            transition_name, star_name = star_transitions[i % len(star_transitions)]

            # Get waypoint for this transition
            waypoint = self.cifp_parser.get_transition_waypoint(transition_name, star_name)

            if not waypoint:
                logger.warning(f"Transition waypoint {transition_name}.{star_name} not found in CIFP data")
                continue

            # Check if waypoint has valid coordinates
            if waypoint.latitude == 0.0 and waypoint.longitude == 0.0:
                logger.warning(f"Waypoint {waypoint.name} has no coordinate data")
                continue

            aircraft = self._create_arrival_at_waypoint(waypoint, altitude_range, 0, active_runways, star_name)
            # Legacy mode: apply random spawn delay
            if spawn_delay_range and not delay_value:
                aircraft.spawn_delay = random.randint(min_delay, max_delay)
                logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
            difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
            self.aircraft.append(aircraft)

        # Apply new spawn delay system
        if not spawn_delay_range:
            self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} arrival aircraft")
        return self.aircraft

    def _parse_star_transitions(self, arrival_waypoints: List[str]) -> List[Tuple[str, str]]:
        """
        Parse STAR waypoint input format

        Users can specify ANY waypoint along a STAR procedure, not just transition points.

        Args:
            arrival_waypoints: List of strings in format "WAYPOINT.STAR"
                              (e.g., "EAGUL.JESSE3", "PINNG.PINNG1", "HOTTT.PINNG1")

        Returns:
            List of (waypoint_name, star_name) tuples
        """
        star_transitions = []

        for entry in arrival_waypoints:
            entry = entry.strip()

            # Check if it's in WAYPOINT.STAR format
            if '.' in entry:
                parts = entry.split('.')
                if len(parts) == 2:
                    waypoint_name = parts[0].strip()
                    star_name = parts[1].strip()
                    star_transitions.append((waypoint_name, star_name))
                    logger.debug(f"Parsed STAR waypoint: {waypoint_name}.{star_name}")
                else:
                    logger.warning(f"Invalid STAR waypoint format: {entry} (expected WAYPOINT.STAR)")
            else:
                # Legacy support: treat as waypoint name, try to infer STAR
                waypoint = self.cifp_parser.get_waypoint(entry)
                if waypoint and waypoint.arrival_name:
                    star_transitions.append((entry, waypoint.arrival_name))
                    logger.warning(f"Legacy format detected: {entry} - inferred as {entry}.{waypoint.arrival_name}")
                else:
                    logger.warning(f"Cannot parse entry: {entry} (use WAYPOINT.STAR format)")

        return star_transitions

    def _create_arrival_at_waypoint(self, waypoint, altitude_range: Tuple[int, int], delay_seconds: int = 0, active_runways: List[str] = None, star_name: str = None) -> Aircraft:
        """
        Create an arrival aircraft at a waypoint

        Args:
            waypoint: Waypoint object
            altitude_range: Tuple of (min, max) altitude (used as fallback only)
            delay_seconds: Spawn delay in seconds
            active_runways: List of active runway designators
            star_name: STAR name for looking up next waypoint

        Returns:
            Aircraft object
        """
        # Get random departure airport and flight plan
        departure = self._get_random_destination(exclude=self.airport_icao)
        flight_plan = self.api_client.get_random_flight_plan(departure, self.airport_icao)

        # Use callsign from API if available, otherwise generate
        callsign = flight_plan.get('callsign') or self._generate_callsign()

        # Ensure callsign is unique - if it's already used, generate a new one
        if callsign in self.used_callsigns:
            callsign = self._generate_callsign()

        # Add callsign to used set
        self.used_callsigns.add(callsign)

        # Determine altitude - STRICTLY ENFORCE CIFP CONSTRAINTS
        altitude = self._get_altitude_from_cifp(waypoint, altitude_range)

        # Use inbound course from CIFP if available, otherwise calculate bearing to next fix
        if waypoint.inbound_course:
            heading = waypoint.inbound_course
            logger.debug(f"Using CIFP inbound course {heading}° for {waypoint.name}")
        else:
            # Fallback: calculate heading to next waypoint in STAR sequence
            # Note: TF (Track to Fix) and IF (Initial Fix) legs don't have explicit courses in CIFP
            from utils.geo_utils import calculate_bearing

            next_waypoint = None
            if star_name and waypoint.sequence_number:
                # Get next waypoint in sequence
                next_waypoint = self.cifp_parser.get_next_waypoint_in_star(star_name, waypoint.sequence_number)

            if next_waypoint and next_waypoint.latitude != 0.0 and next_waypoint.longitude != 0.0:
                heading = calculate_bearing(waypoint.latitude, waypoint.longitude, next_waypoint.latitude, next_waypoint.longitude)
                logger.debug(f"{waypoint.name} -> {next_waypoint.name}: calculated bearing {heading}°")
            else:
                # Final fallback: use bearing to airport
                airport_lat, airport_lon = self.geojson_parser.get_airport_center()
                heading = calculate_bearing(waypoint.latitude, waypoint.longitude, airport_lat, airport_lon)
                leg_type = waypoint.leg_type if hasattr(waypoint, 'leg_type') and waypoint.leg_type else "unknown"
                logger.debug(f"{waypoint.name} has no next waypoint, using bearing to airport: {heading}°")

        # Ground speed - STRICTLY ENFORCE CIFP SPEED RESTRICTIONS
        ground_speed = self._get_speed_from_cifp(waypoint, altitude)

        # Build route from waypoint and STAR
        # Format: "WAYPOINT ARRIVAL.RUNWAY"
        route = waypoint.name
        if waypoint.arrival_name:
            # Get available runways for this arrival, filtered by active runways
            available_runways = self._get_runways_for_arrival(waypoint.arrival_name, active_runways)
            if available_runways:
                # Pick a random runway from those available for this STAR
                runway = random.choice(available_runways)
                route = f"{waypoint.name} {waypoint.arrival_name}.{runway}"
                logger.debug(f"Set route for {callsign}: {route}")
            else:
                # No runways found, just use waypoint and STAR
                route = f"{waypoint.name} {waypoint.arrival_name}"
                logger.warning(f"No runways found for arrival {waypoint.arrival_name}, using STAR only")
        else:
            logger.warning(f"Waypoint {waypoint.name} has no arrival procedure associated")

        # Calculate actual spawn position 10NM BEFORE the waypoint
        # This fixes the position bug - aircraft now spawn on approach TO the waypoint
        from utils.geo_utils import calculate_destination, get_reciprocal_heading

        reciprocal_heading = get_reciprocal_heading(heading)
        spawn_distance = 10  # nautical miles
        spawn_lat, spawn_lon = calculate_destination(
            waypoint.latitude,
            waypoint.longitude,
            reciprocal_heading,
            spawn_distance
        )

        logger.debug(f"Spawn position: 10NM from {waypoint.name} on {reciprocal_heading}° radial")
        logger.debug(f"  Waypoint: {waypoint.latitude:.6f}, {waypoint.longitude:.6f}")
        logger.debug(f"  Spawn: {spawn_lat:.6f}, {spawn_lon:.6f}")

        # Set Fix/Radial/Distance navigation path
        # Format: FIXNAME + RADIAL (reciprocal + 180) + DISTANCE (10NM)
        # Example: PINNG112010 means "10NM from PINNG on the 112 radial"
        navigation_path = f"{waypoint.name}{reciprocal_heading:03d}{spawn_distance:03d}"

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=flight_plan['aircraft_type'],
            latitude=spawn_lat,      # Use calculated spawn position
            longitude=spawn_lon,      # Use calculated spawn position
            altitude=altitude,
            heading=heading,
            ground_speed=ground_speed,
            departure=departure,
            arrival=self.airport_icao,
            route=route,
            cruise_altitude=flight_plan['altitude'],
            flight_rules="I",
            engine_type="J",
            navigation_path=navigation_path  # Set Fix/Radial/Distance
        )

        logger.debug(f"Set navigation path for {callsign}: {navigation_path}")

        return aircraft

    def _get_altitude_from_cifp(self, waypoint, altitude_range: Tuple[int, int]) -> int:
        """
        Get altitude based on CIFP constraints, strictly enforcing altitude descriptors

        Args:
            waypoint: Waypoint object with CIFP data
            altitude_range: Fallback altitude range (min, max)

        Returns:
            Altitude in feet
        """
        # Check altitude descriptor for constraint type
        if waypoint.altitude_descriptor:
            descriptor = waypoint.altitude_descriptor

            if descriptor == '@':
                # AT altitude - mandatory, use exact altitude
                if waypoint.min_altitude:
                    logger.debug(f"CIFP: CROSS {waypoint.name} AT {waypoint.min_altitude} ft")
                    return waypoint.min_altitude
                elif waypoint.max_altitude:
                    return waypoint.max_altitude

            elif descriptor == '+':
                # AT or ABOVE altitude
                if waypoint.min_altitude:
                    logger.debug(f"CIFP: CROSS {waypoint.name} AT OR ABOVE {waypoint.min_altitude} ft")
                    # Spawn at the minimum or slightly above
                    return waypoint.min_altitude + random.randint(0, 1000)

            elif descriptor == '-':
                # AT or BELOW altitude
                if waypoint.max_altitude:
                    logger.debug(f"CIFP: CROSS {waypoint.name} AT OR BELOW {waypoint.max_altitude} ft")
                    # Spawn at the maximum or slightly below
                    return waypoint.max_altitude - random.randint(0, 1000)

            elif descriptor == 'B':
                # BETWEEN altitudes
                if waypoint.min_altitude and waypoint.max_altitude:
                    logger.debug(f"CIFP: CROSS {waypoint.name} BETWEEN {waypoint.min_altitude} and {waypoint.max_altitude} ft")
                    return random.randint(waypoint.min_altitude, waypoint.max_altitude)

        # Legacy handling - if no descriptor but altitudes exist
        if waypoint.min_altitude and waypoint.max_altitude:
            # If they're the same, it's a mandatory crossing altitude
            if waypoint.min_altitude == waypoint.max_altitude:
                logger.debug(f"CIFP: CROSS {waypoint.name} AT {waypoint.min_altitude} ft (inferred from equal min/max)")
                return waypoint.min_altitude
            # Otherwise, range
            logger.debug(f"CIFP: CROSS {waypoint.name} BETWEEN {waypoint.min_altitude}-{waypoint.max_altitude} ft")
            return random.randint(waypoint.min_altitude, waypoint.max_altitude)
        elif waypoint.min_altitude:
            logger.debug(f"CIFP: CROSS {waypoint.name} AT OR ABOVE {waypoint.min_altitude} ft")
            return waypoint.min_altitude + random.randint(0, 1000)
        elif waypoint.max_altitude:
            logger.debug(f"CIFP: CROSS {waypoint.name} AT OR BELOW {waypoint.max_altitude} ft")
            return waypoint.max_altitude - random.randint(0, 1000)

        # No CIFP data - use fallback range
        logger.warning(f"No CIFP altitude constraint for {waypoint.name}, using fallback range {altitude_range[0]}-{altitude_range[1]} ft")
        return random.randint(altitude_range[0], altitude_range[1])

    def _get_speed_from_cifp(self, waypoint, altitude: int) -> int:
        """
        Get ground speed based on CIFP speed restrictions, strictly enforcing them

        Args:
            waypoint: Waypoint object with CIFP data
            altitude: Aircraft altitude in feet

        Returns:
            Ground speed in knots
        """
        # Check for CIFP speed restriction
        if waypoint.speed_limit:
            logger.debug(f"CIFP: SPEED RESTRICTION at {waypoint.name}: {waypoint.speed_limit} knots")
            # Add slight variation (±5 knots) for realism but stay within restriction
            variation = random.randint(-5, 5)
            return max(180, min(waypoint.speed_limit + variation, waypoint.speed_limit))

        # No speed restriction from CIFP - use altitude-based logic
        if altitude > 10000:
            speed = random.randint(280, 320)
            logger.debug(f"No CIFP speed restriction for {waypoint.name}, using high-altitude speed: {speed} knots")
        else:
            # Below 10,000 ft, generally 250 knots max
            speed = random.randint(220, 250)
            logger.debug(f"No CIFP speed restriction for {waypoint.name}, using low-altitude speed: {speed} knots")

        return speed
