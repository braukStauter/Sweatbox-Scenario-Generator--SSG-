"""
TRACON (Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft

logger = logging.getLogger(__name__)


class TraconArrivalsScenario(BaseScenario):
    """Scenario for TRACON with arrivals only"""

    def generate(self, num_arrivals: int, arrival_waypoints: List[str],
                 altitude_range: Tuple[int, int] = (7000, 18000),
                 delay_range: Tuple[int, int] = (4, 7),
                 spawn_delay_range: str = "0-0", difficulty_config=None) -> List[Aircraft]:
        """
        Generate TRACON arrival scenario

        Args:
            num_arrivals: Number of arrival aircraft
            arrival_waypoints: List of arrival waypoint names
            altitude_range: Tuple of (min, max) altitude in feet
            delay_range: Tuple of (min, max) spawn delay in minutes between aircraft
            spawn_delay_range: Spawn delay range in minutes (format: "min-max", e.g., "0-0" or "1-5")
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts for difficulty levels

        Returns:
            List of Aircraft objects
        """
        # Reset tracking for new generation
        self._reset_tracking()

        # Setup difficulty assignment
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        # Parse spawn delay range
        min_delay, max_delay = self._parse_spawn_delay_range(spawn_delay_range)

        logger.info(f"Generating TRACON arrival scenario: {num_arrivals} arrivals")

        # Calculate spawn delay in seconds (random within range, then applied cumulatively)
        delay_seconds = random.randint(delay_range[0] * 60, delay_range[1] * 60)

        # Distribute aircraft across waypoints
        for i in range(num_arrivals):
            waypoint_name = arrival_waypoints[i % len(arrival_waypoints)]

            # Get waypoint data
            waypoint = self.cifp_parser.get_waypoint(waypoint_name)

            if not waypoint:
                logger.warning(f"Waypoint {waypoint_name} not found in CIFP data")
                continue

            # Check if waypoint has valid coordinates
            if waypoint.latitude == 0.0 and waypoint.longitude == 0.0:
                logger.warning(f"Waypoint {waypoint_name} has no coordinate data")
                continue

            # Calculate cumulative delay for this aircraft
            # First aircraft has 0 delay, subsequent aircraft increment
            cumulative_delay = i * delay_seconds

            aircraft = self._create_arrival_at_waypoint(waypoint, altitude_range, cumulative_delay)
            aircraft.spawn_delay = random.randint(min_delay, max_delay)
            difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
            self.aircraft.append(aircraft)

        logger.info(f"Generated {len(self.aircraft)} arrival aircraft")
        return self.aircraft

    def _create_arrival_at_waypoint(self, waypoint, altitude_range: Tuple[int, int], delay_seconds: int = 0) -> Aircraft:
        """
        Create an arrival aircraft at a waypoint

        Args:
            waypoint: Waypoint object
            altitude_range: Tuple of (min, max) altitude
            delay_seconds: Spawn delay in seconds

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

        # Determine altitude
        # If waypoint has restrictions, use those; otherwise use random within range
        if waypoint.min_altitude and waypoint.max_altitude:
            # Respect waypoint restrictions
            altitude = random.randint(waypoint.min_altitude, waypoint.max_altitude)
        elif waypoint.min_altitude:
            altitude = waypoint.min_altitude
        elif waypoint.max_altitude:
            altitude = waypoint.max_altitude
        else:
            # Use provided range
            altitude = random.randint(altitude_range[0], altitude_range[1])

        # Calculate heading towards airport center
        from utils.geo_utils import calculate_bearing

        airport_lat, airport_lon = self.geojson_parser.get_airport_center()

        heading = calculate_bearing(waypoint.latitude, waypoint.longitude, airport_lat, airport_lon)

        # Ground speed based on altitude (higher = faster)
        if altitude > 10000:
            ground_speed = random.randint(280, 320)
        else:
            ground_speed = random.randint(220, 260)

        # Use the route from the flight plan
        # Note: The route from the API typically already includes a STAR
        # We don't append the waypoint's arrival_name to avoid duplicates
        route = flight_plan['route']

        # Create delay remark if delay is greater than 0
        remarks = f"DELAY THIS A/C BY {delay_seconds} SECONDS" if delay_seconds > 0 else ""

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=flight_plan['aircraft_type'],
            latitude=waypoint.latitude,
            longitude=waypoint.longitude,
            altitude=altitude,
            heading=heading,
            ground_speed=ground_speed,
            departure=departure,
            arrival=self.airport_icao,
            route=route,
            cruise_altitude=flight_plan['altitude'],
            flight_rules="I",
            engine_type="J",
            remarks=remarks
        )

        return aircraft
