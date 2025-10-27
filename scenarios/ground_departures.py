"""
Ground (Departures) scenario
"""
import random
import logging
from typing import List

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft

logger = logging.getLogger(__name__)


class GroundDeparturesScenario(BaseScenario):
    """Scenario with ground departure aircraft only"""

    def generate(self, num_departures: int) -> List[Aircraft]:
        """
        Generate ground departure aircraft

        Args:
            num_departures: Number of departure aircraft to generate

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

        logger.info(f"Generating {num_departures} departure aircraft")

        # Generate aircraft, trying more spots if needed
        attempts = 0
        max_attempts = len(parking_spots) * 2  # Allow retries
        available_spots = parking_spots.copy()

        while len(self.aircraft) < num_departures and attempts < max_attempts and available_spots:
            # Pick a random spot from available spots
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

        logger.info(f"Generated {len(self.aircraft)} departure aircraft")
        return self.aircraft
