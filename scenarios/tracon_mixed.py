"""
TRACON (Departures/Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from utils.geo_utils import calculate_bearing

logger = logging.getLogger(__name__)


class TraconMixedScenario(BaseScenario):
    """Scenario for TRACON with both departures and arrivals"""

    def generate(self, num_departures: int, num_arrivals: int, arrival_waypoints: List[str],
                 altitude_range: Tuple[int, int] = (7000, 18000),
                 delay_range: Tuple[int, int] = (4, 7)) -> List[Aircraft]:
        """
        Generate TRACON mixed scenario

        Args:
            num_departures: Number of departure aircraft
            num_arrivals: Number of arrival aircraft
            arrival_waypoints: List of arrival waypoint names
            altitude_range: Tuple of (min, max) altitude in feet for arrivals
            delay_range: Tuple of (min, max) spawn delay in minutes between aircraft

        Returns:
            List of Aircraft objects
        """
        # Reset tracking for new generation
        self._reset_tracking()

        parking_spots = self.geojson_parser.get_parking_spots()

        if num_departures > len(parking_spots):
            raise ValueError(
                f"Cannot create {num_departures} aircraft with only {len(parking_spots)} parking spots available"
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
                aircraft = self._create_departure_aircraft(spot)

            if aircraft is not None:
                self.aircraft.append(aircraft)

            attempts += 1

        # Calculate spawn delay in seconds (random within range, then applied cumulatively)
        delay_seconds = random.randint(delay_range[0] * 60, delay_range[1] * 60)

        # Generate arrivals at waypoints
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
            self.aircraft.append(aircraft)

        logger.info(f"Generated {len(self.aircraft)} total aircraft")
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
        if waypoint.min_altitude and waypoint.max_altitude:
            altitude = random.randint(waypoint.min_altitude, waypoint.max_altitude)
        elif waypoint.min_altitude:
            altitude = waypoint.min_altitude
        elif waypoint.max_altitude:
            altitude = waypoint.max_altitude
        else:
            altitude = random.randint(altitude_range[0], altitude_range[1])

        # Calculate heading towards airport center
        airport_lat, airport_lon = self.geojson_parser.get_airport_center()

        heading = calculate_bearing(waypoint.latitude, waypoint.longitude, airport_lat, airport_lon)

        # Ground speed based on altitude
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
