"""
TRACON (Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.flight_data_filter import clean_route_string

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

        # Prepare arrival flight pool filtered by waypoints if specified
        if arrival_waypoints:
            # Use first waypoint for filtering (could be enhanced to support multiple)
            waypoint_parts = arrival_waypoints[0].split('.')
            waypoint_name = waypoint_parts[0] if waypoint_parts else None
            star_name = waypoint_parts[1] if len(waypoint_parts) > 1 else None
            logger.info(f"Preparing arrival flight pool filtered by waypoint: {waypoint_name}.{star_name}")
            self._prepare_arrival_flight_pool(waypoint_name, star_name)
        else:
            self._prepare_arrival_flight_pool()

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
        # Get flight from pool
        flight_data = self._get_next_arrival_flight()

        if not flight_data:
            logger.error("No flight data available for arrival aircraft at waypoint")
            # Fallback to minimal aircraft data
            flight_data = {
                'departureAirport': self._get_random_destination(exclude=self.airport_icao),
                'aircraftIdentification': self._generate_callsign(),
                'aircraftType': 'B738',
                'route': '',
                'requestedAltitude': str(altitude_range[1]),
                'requestedAirspeed': '250'
            }

        # Extract data from API flight
        departure = flight_data.get('departureAirport', self._get_random_destination(exclude=self.airport_icao))
        api_callsign = flight_data.get('aircraftIdentification', '')
        api_aircraft_type = flight_data.get('aircraftType', 'B738')
        api_route = flight_data.get('route', '')

        # Calculate cruise altitude
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

        # Use callsign from API if available, otherwise generate
        callsign = api_callsign if api_callsign and api_callsign.strip() else self._generate_callsign()

        # Ensure callsign is unique
        with self.callsign_lock:
            while callsign in self.used_callsigns:
                callsign = self._generate_callsign()
            self.used_callsigns.add(callsign)

        # Determine altitude - STRICTLY ENFORCE CIFP CONSTRAINTS
        altitude = self._get_altitude_from_cifp(waypoint, altitude_range)

        # Determine inbound course to the waypoint
        from utils.geo_utils import calculate_bearing

        inbound_course = None
        prev_waypoint = None

        # Try to get inbound course from CIFP first
        if waypoint.inbound_course:
            inbound_course = waypoint.inbound_course
            logger.debug(f"Using CIFP inbound course {inbound_course}° for {waypoint.name}")
        else:
            # Calculate from previous waypoint in STAR sequence
            # Note: TF (Track to Fix) and IF (Initial Fix) legs don't have explicit courses in CIFP
            if star_name and waypoint.sequence_number:
                prev_waypoint = self.cifp_parser.get_previous_waypoint_in_star(star_name, waypoint.sequence_number)

            if prev_waypoint and prev_waypoint.latitude != 0.0 and prev_waypoint.longitude != 0.0:
                inbound_course = calculate_bearing(prev_waypoint.latitude, prev_waypoint.longitude, waypoint.latitude, waypoint.longitude)
                logger.debug(f"{prev_waypoint.name} -> {waypoint.name}: calculated inbound course {inbound_course}°")
            else:
                # No previous waypoint - use next waypoint to determine lateral course
                next_waypoint = None
                if star_name and waypoint.sequence_number:
                    next_waypoint = self.cifp_parser.get_next_waypoint_in_star(star_name, waypoint.sequence_number)

                if next_waypoint and next_waypoint.latitude != 0.0 and next_waypoint.longitude != 0.0:
                    # Calculate the outbound course and use its reciprocal as inbound
                    outbound_course = calculate_bearing(waypoint.latitude, waypoint.longitude, next_waypoint.latitude, next_waypoint.longitude)
                    from utils.geo_utils import get_reciprocal_heading
                    inbound_course = get_reciprocal_heading(outbound_course)
                    logger.debug(f"{waypoint.name} is first waypoint, using reciprocal of outbound course to {next_waypoint.name}: {inbound_course}°")
                else:
                    # Final fallback: use bearing to airport
                    airport_lat, airport_lon = self.geojson_parser.get_airport_center()
                    inbound_course = calculate_bearing(waypoint.latitude, waypoint.longitude, airport_lat, airport_lon)
                    logger.debug(f"{waypoint.name} has no previous/next waypoint, using bearing to airport: {inbound_course}°")

        # Set heading (direction aircraft is flying) to the inbound course
        heading = inbound_course

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

        # Calculate actual spawn position 2NM BEFORE the waypoint along the inbound course
        # Aircraft spawn on approach TO the specified waypoint
        from utils.geo_utils import calculate_destination, get_reciprocal_heading

        reciprocal_heading = get_reciprocal_heading(heading)
        spawn_distance = 2  # nautical miles
        spawn_lat, spawn_lon = calculate_destination(
            waypoint.latitude,
            waypoint.longitude,
            reciprocal_heading,
            spawn_distance
        )

        logger.debug(f"Spawn position: {spawn_distance}NM from {waypoint.name} on {reciprocal_heading}° radial (inbound course: {heading}°)")
        logger.debug(f"  Waypoint: {waypoint.latitude:.6f}, {waypoint.longitude:.6f}")
        logger.debug(f"  Spawn: {spawn_lat:.6f}, {spawn_lon:.6f}")

        # Set Fix/Radial/Distance navigation path
        # Format: FIXNAME + RADIAL (reciprocal of inbound course) + DISTANCE (2NM)
        # Example: XMRKS232002 means "2NM from XMRKS on the 232 radial"
        navigation_path = f"{waypoint.name}{reciprocal_heading:03d}{int(spawn_distance):03d}"

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=api_aircraft_type,
            latitude=spawn_lat,      # Use calculated spawn position
            longitude=spawn_lon,      # Use calculated spawn position
            altitude=altitude,
            heading=heading,
            ground_speed=ground_speed,
            departure=departure,
            arrival=self.airport_icao,
            route=route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            flight_rules=flight_data.get('initialFlightRules', 'I')[0] if flight_data.get('initialFlightRules') else 'I',
            engine_type="J",
            navigation_path=navigation_path,  # Set Fix/Radial/Distance
            # Additional API fields
            gufi=flight_data.get('gufi'),
            registration=flight_data.get('registration'),
            operator=flight_data.get('operator'),
            estimated_arrival_time=flight_data.get('estimatedArrivalTime'),
            wake_turbulence=flight_data.get('wakeTurbulence')
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
