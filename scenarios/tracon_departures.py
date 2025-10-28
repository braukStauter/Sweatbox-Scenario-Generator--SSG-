"""
TRACON (Departures) scenario
"""
import random
import logging
from typing import List

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft

logger = logging.getLogger(__name__)


class TraconDeparturesScenario(BaseScenario):
    """Scenario for TRACON with departures only"""

    def generate(self, num_departures: int, active_runways: List[str], spawn_delay_range: str = "0-0", difficulty_config=None) -> List[Aircraft]:
        """
        Generate TRACON departure scenario

        Args:
            num_departures: Number of departure aircraft
            active_runways: List of active runway designators (not used for ground aircraft)
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

        parking_spots = self.geojson_parser.get_parking_spots()

        if num_departures > len(parking_spots):
            raise ValueError(
                f"Cannot create {num_departures} aircraft with only {len(parking_spots)} parking spots available"
            )

        logger.info(f"Generating TRACON departure scenario: {num_departures} departures")

        # Generate aircraft, trying more spots if needed
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
                aircraft.spawn_delay = random.randint(min_delay, max_delay)
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                self.aircraft.append(aircraft)

            attempts += 1

        logger.info(f"Generated {len(self.aircraft)} departure aircraft")
        return self.aircraft
