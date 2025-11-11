"""
Ground (Departures) scenario
"""
import random
import logging
from typing import List

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode

logger = logging.getLogger(__name__)


class GroundDeparturesScenario(BaseScenario):
    """Scenario with ground departure aircraft only"""

    def generate(self, num_departures: int, spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None,
                 active_runways: List[str] = None, enable_cifp_sids: bool = False,
                 manual_sids: List[str] = None) -> List[Aircraft]:
        """
        Generate ground departure aircraft

        Args:
            num_departures: Number of departure aircraft to generate
            spawn_delay_mode: SpawnDelayMode enum (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: delay range/value in minutes (e.g., "2-5" or "3")
            total_session_minutes: For TOTAL mode: total session length in minutes
            spawn_delay_range: LEGACY parameter - kept for backward compatibility
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts for difficulty levels
            active_runways: List of active runway designators (e.g., ['08', '26'])
            enable_cifp_sids: Whether to use CIFP SID procedures
            manual_sids: Optional list of specific SIDs to use

        Returns:
            List of Aircraft objects
        """
        self._reset_tracking()

        logger.info("Preparing departure flight pool...")
        self._prepare_departure_flight_pool(active_runways, enable_cifp_sids, manual_sids)
        self._prepare_ga_flight_pool()

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

        logger.info(f"Generating {num_departures} departure aircraft with spawn_delay_mode={spawn_delay_mode.value}")

        random.shuffle(parking_spots)

        # Generate aircraft sequentially (no need for threading since we're not making API calls per aircraft)
        for i, spot in enumerate(parking_spots):
            if len(self.aircraft) >= num_departures:
                break

            try:
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
                    logger.debug(f"Created aircraft {len(self.aircraft)}/{num_departures}: {aircraft.callsign}")

            except Exception as e:
                logger.error(f"Error creating aircraft for parking spot {spot.name}: {e}")

        if not spawn_delay_range:
            self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} departure aircraft")
        return self.aircraft
