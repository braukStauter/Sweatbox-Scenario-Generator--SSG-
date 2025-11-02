"""
Ground (Departures/Arrivals) scenario
"""
import random
import logging
from typing import List

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode

logger = logging.getLogger(__name__)


class GroundMixedScenario(BaseScenario):
    """Scenario with ground departures and arriving aircraft"""

    def generate(self, num_departures: int, num_arrivals: int, active_runways: List[str],
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None) -> List[Aircraft]:
        """
        Generate ground departure and arrival aircraft

        Args:
            num_departures: Number of departure aircraft
            num_arrivals: Number of arrival aircraft
            active_runways: List of active runway designators (e.g., ['7L', '25R'])
            spawn_delay_mode: SpawnDelayMode enum (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: delay range/value in minutes (e.g., "2-5" or "3")
            total_session_minutes: For TOTAL mode: total session length in minutes
            spawn_delay_range: LEGACY parameter - kept for backward compatibility
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts for difficulty levels

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

        parking_spots = self.geojson_parser.get_parking_spots()

        if num_departures > len(parking_spots):
            raise ValueError(
                f"Cannot create {num_departures} aircraft with only {len(parking_spots)} parking spots available"
            )

        logger.info(f"Generating {num_departures} departures and {num_arrivals} arrivals with spawn_delay_mode={spawn_delay_mode.value}")

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
                # Legacy mode: apply random spawn delay
                if spawn_delay_range and not delay_value:
                    aircraft.spawn_delay = random.randint(min_delay, max_delay)
                    logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
                # Assign difficulty level
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                self.aircraft.append(aircraft)

            attempts += 1

        # Generate arrivals
        # With new spawn delay system, spacing is controlled by spawn delays
        # Use fixed 5 NM final approach position for all arrivals
        # (spawn delays handle the timing, so no need for distance-based spacing)
        for i in range(num_arrivals):
            runway_name = active_runways[i % len(active_runways)]
            distance_nm = 5  # Fixed 5 NM final approach position
            aircraft = self._create_arrival_aircraft(runway_name, distance_nm)
            # Legacy mode: apply random spawn delay
            if spawn_delay_range and not delay_value:
                aircraft.spawn_delay = random.randint(min_delay, max_delay)
                logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
            # Assign difficulty level
            difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
            self.aircraft.append(aircraft)

        # Apply new spawn delay system
        if not spawn_delay_range:
            self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} total aircraft")
        return self.aircraft

    def _create_arrival_aircraft(self, runway_name: str, distance_nm: float) -> Aircraft:
        """
        Create an arrival aircraft on final approach

        Args:
            runway_name: Runway designator (e.g., '7L')
            distance_nm: Distance from runway threshold in nautical miles

        Returns:
            Aircraft object
        """
        # Get flight plan from API (includes callsign)
        departure = self._get_random_destination(exclude=self.airport_icao)
        flight_plan = self.api_client.get_random_flight_plan(departure, self.airport_icao)

        # Use callsign from API if available, otherwise generate
        callsign = flight_plan.get('callsign') or self._generate_callsign()

        # Ensure callsign is unique - if it's already used, generate a new one
        if callsign in self.used_callsigns:
            callsign = self._generate_callsign()

        # Add callsign to used set
        self.used_callsigns.add(callsign)

        # Use vNAS "On Final" starting condition - vNAS automatically positions aircraft
        # We only need to set arrival_runway and arrival_distance_nm
        # vNAS handles altitude, position, heading, and speed based on the runway and distance
        logger.info(f"Creating arrival: {callsign} on final {runway_name}, {distance_nm:.1f} NM out")

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=flight_plan['aircraft_type'],
            latitude=0.0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            longitude=0.0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            altitude=0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            heading=0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            ground_speed=0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            departure=departure,
            arrival=self.airport_icao,
            route=flight_plan['route'],
            cruise_altitude=flight_plan['altitude'],
            flight_rules="I",
            engine_type="J",
            arrival_runway=runway_name,
            arrival_distance_nm=distance_nm
        )

        return aircraft
