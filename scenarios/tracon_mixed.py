"""
TRACON (Departures/Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.geo_utils import calculate_bearing

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

        # Prepare flight pools from cached data
        logger.info("Preparing flight pools...")
        self._prepare_departure_flight_pool(active_runways, enable_cifp_sids, manual_sids)
        self._prepare_ga_flight_pool()

        # Parse STAR transitions and prepare filtered arrival pool (pass active_runways for random selection)
        star_transitions = self._parse_star_transitions(arrival_waypoints, active_runways)
        if star_transitions:
            logger.info(f"Preparing arrival flight pool filtered by {len(star_transitions)} STAR transitions")
            self._prepare_arrival_flight_pool(star_transitions=star_transitions)
        else:
            logger.info("No STAR transitions specified, using all arrivals")
            self._prepare_arrival_flight_pool()

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

        # Parse STAR waypoints from input
        star_transitions = self._parse_star_transitions(arrival_waypoints)

        if not star_transitions:
            logger.error("No valid STAR waypoints provided for arrivals")
            return self.aircraft

        # Generate arrivals at waypoints
        # Keep trying until we have enough arrivals or we've tried too many times
        arrivals_created = len([a for a in self.aircraft if a.arrival == self.airport_icao])
        attempts = 0
        max_attempts = num_arrivals * 3  # Allow 3x attempts to handle duplicates/skips

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

            aircraft = self._create_arrival_at_waypoint(waypoint, 0, active_runways, star_name)
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
            logger.warning(f"Could only generate {arrivals_created}/{num_arrivals} arrivals after {attempts} attempts (likely due to duplicate callsigns or limited API data)")

        # Apply new spawn delay system
        if not spawn_delay_range:
            self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} total aircraft")
        return self.aircraft

    def _create_arrival_at_waypoint(self, waypoint, delay_seconds: int = 0, active_runways: List[str] = None, star_name: str = None) -> Aircraft:
        """
        Create an arrival aircraft at a waypoint

        Args:
            waypoint: Waypoint object
            delay_seconds: Spawn delay in seconds
            active_runways: List of active runway designators
            star_name: STAR name for looking up next waypoint and altitude interpolation

        Returns:
            Aircraft object
        """
        # Import here to avoid circular dependency
        from scenarios.tracon_arrivals import TraconArrivalsScenario

        # Create a temporary TraconArrivalsScenario to use its enhanced methods
        temp_scenario = TraconArrivalsScenario(
            self.airport_icao,
            self.geojson_parser,
            self.cifp_parser,
            self.api_client
        )

        # Copy over the used callsigns to maintain uniqueness
        temp_scenario.used_callsigns = self.used_callsigns

        # Use the enhanced arrival creation from TraconArrivalsScenario
        aircraft = temp_scenario._create_arrival_at_waypoint(waypoint, delay_seconds, active_runways, star_name)

        # Update our used callsigns with any new ones
        self.used_callsigns.update(temp_scenario.used_callsigns)

        return aircraft

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
