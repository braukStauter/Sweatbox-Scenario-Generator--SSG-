"""
Tower (Departures/Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.flight_data_filter import clean_route_string

logger = logging.getLogger(__name__)


class TowerMixedScenario(BaseScenario):
    """Scenario for Tower position with departures and arrivals"""

    def generate(self, num_departures: int, num_arrivals: int, active_runways: List[str],
                 separation_range: Tuple[int, int] = (3, 6),
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None,
                 enable_cifp_sids: bool = False, manual_sids: List[str] = None) -> List[Aircraft]:
        """
        Generate tower scenario with departures and arrivals

        Args:
            num_departures: Number of departure aircraft
            num_arrivals: Number of arrival aircraft
            active_runways: List of active runway designators
            separation_range: Tuple of (min, max) separation in nautical miles
            spawn_delay_mode: SpawnDelayMode enum (NONE, INCREMENTAL, or TOTAL)
            delay_value: For INCREMENTAL mode: delay range/value in minutes (e.g., "2-5" or "3")
            total_session_minutes: For TOTAL mode: total session length in minutes
            spawn_delay_range: LEGACY parameter - kept for backward compatibility
            difficulty_config: Optional dict with 'easy', 'medium', 'hard' counts for difficulty levels
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
        self._prepare_arrival_flight_pool()

        # Setup difficulty assignment
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        # Handle legacy spawn_delay_range parameter
        if spawn_delay_range and not delay_value:
            logger.warning("Using legacy spawn_delay_range parameter. Consider upgrading to spawn_delay_mode.")
            min_delay, max_delay = self._parse_spawn_delay_range(spawn_delay_range)

        parking_spots = self.geojson_parser.get_parking_spots()
        ga_spots = self.geojson_parser.get_parking_spots(filter_ga=True)

        if num_departures > len(parking_spots):
            raise ValueError(
                f"Cannot create {num_departures} departures - only {len(parking_spots)} parking spots available at {self.airport_icao}. "
                f"Please reduce the number of departures to {len(parking_spots)} or fewer."
            )

        logger.info(f"Generating Tower scenario: {num_departures} departures, {num_arrivals} arrivals")

        # Calculate how many GA aircraft to include (10-20% of departures if GA spots exist)
        num_ga = 0
        if ga_spots:
            num_ga = min(len(ga_spots), max(1, int(num_departures * 0.15)))

        # Generate commercial departures
        num_commercial = num_departures - num_ga
        commercial_spots = [spot for spot in parking_spots if 'GA' not in spot.name.upper()]

        if num_commercial > 0:
            attempts = 0
            max_attempts = len(commercial_spots) * 2
            available_spots = commercial_spots.copy()

            while len(self.aircraft) < num_commercial and attempts < max_attempts and available_spots:
                spot = random.choice(available_spots)
                available_spots.remove(spot)

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

        # Generate GA departures
        if num_ga > 0 and ga_spots:
            attempts = 0
            max_attempts = len(ga_spots) * 2
            available_ga_spots = ga_spots.copy()
            num_ga_created = 0

            while num_ga_created < num_ga and attempts < max_attempts and available_ga_spots:
                spot = random.choice(available_ga_spots)
                available_ga_spots.remove(spot)

                aircraft = self._create_ga_aircraft(spot)
                if aircraft is not None:
                    # Legacy mode: apply random spawn delay
                    if spawn_delay_range and not delay_value:
                        aircraft.spawn_delay = random.randint(min_delay, max_delay)
                        logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
                    difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                    self.aircraft.append(aircraft)
                    num_ga_created += 1

                attempts += 1

        # Generate arrivals with separation
        # With spawn delay system, spacing is controlled by spawn delays
        # When no spawn delay is used (NONE mode), stagger by distance instead
        for i in range(num_arrivals):
            runway_name = active_runways[i % len(active_runways)]

            # If no spawn delay mode, stagger arrivals by distance
            if spawn_delay_mode == SpawnDelayMode.NONE and not spawn_delay_range:
                # Use separation_range for distance spacing
                base_distance = 6
                separation = random.randint(separation_range[0], separation_range[1])
                distance_nm = base_distance + (i // len(active_runways)) * separation
            else:
                # With spawn delays, use fixed 6 NM final approach position
                distance_nm = 6

            aircraft = self._create_arrival_aircraft(runway_name, distance_nm)
            # Legacy mode: apply random spawn delay
            if spawn_delay_range and not delay_value:
                aircraft.spawn_delay = random.randint(min_delay, max_delay)
                logger.info(f"Set spawn_delay={aircraft.spawn_delay}s for {aircraft.callsign} (legacy mode)")
            difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
            self.aircraft.append(aircraft)

        # Apply new spawn delay system
        if not spawn_delay_range:
            self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        logger.info(f"Generated {len(self.aircraft)} total aircraft ({num_ga} GA)")
        return self.aircraft

    def _create_arrival_aircraft(self, runway_name: str, distance_nm: float) -> Aircraft:
        """
        Create an arrival aircraft on final approach using cached flight data

        Args:
            runway_name: Runway designator
            distance_nm: Distance from runway threshold in nautical miles

        Returns:
            Aircraft object
        """
        # Get flight from pool
        flight_data = self._get_next_arrival_flight()

        if not flight_data:
            logger.error("No flight data available for arrival aircraft")
            return None

        # Extract data from API flight
        departure = flight_data.get('departureAirport', self._get_random_destination(exclude=self.airport_icao))
        raw_route = flight_data.get('route', '')
        route = clean_route_string(raw_route)
        api_callsign = flight_data.get('aircraftIdentification', '')
        api_aircraft_type = flight_data.get('aircraftType', 'B738')

        # Calculate cruise altitude from requested altitude or default
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

        # ALWAYS use API callsign to keep data matched - never generate
        if api_callsign and api_callsign.strip():
            callsign = api_callsign
        else:
            logger.warning(f"Arrival from {departure} missing callsign from API, generating one")
            callsign = self._generate_callsign()

        # Ensure callsign is unique
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                # If from API, skip this flight to maintain data integrity
                if api_callsign and api_callsign.strip():
                    logger.warning(f"Duplicate arrival callsign from API: {callsign}, skipping this flight")
                    return None
                # Otherwise generate new callsign (only for fallback)
                while callsign in self.used_callsigns:
                    callsign = self._generate_callsign()
            self.used_callsigns.add(callsign)

        # Ensure equipment suffix (/L for airlines, /G for GA)
        is_ga_type = self._is_ga_aircraft_type(api_aircraft_type)
        aircraft_type = self._add_equipment_suffix(api_aircraft_type, is_ga_type)

        # Calculate appropriate final approach speed based on aircraft type
        ground_speed = self._get_final_approach_speed(aircraft_type)

        # Use vNAS "On Final" starting condition - vNAS automatically positions aircraft
        # We only need to set arrival_runway and arrival_distance_nm
        # vNAS handles altitude, position, and heading based on the runway and distance
        logger.info(f"Creating arrival: {callsign} on final {runway_name}, {distance_nm:.1f} NM out at {ground_speed} knots")

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=0.0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            longitude=0.0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            altitude=0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            heading=0,  # vNAS will calculate from arrival_runway and arrival_distance_nm
            ground_speed=ground_speed,
            departure=departure,
            arrival=self.airport_icao,
            route=route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            flight_rules=flight_data.get('initialFlightRules', 'I')[0] if flight_data.get('initialFlightRules') else 'I',
            engine_type="J",
            arrival_runway=runway_name,
            arrival_distance_nm=distance_nm,
            # Additional API fields
            gufi=flight_data.get('gufi'),
            registration=flight_data.get('registration'),
            operator=flight_data.get('operator'),
            estimated_arrival_time=flight_data.get('estimatedArrivalTime'),
            wake_turbulence=flight_data.get('wakeTurbulence')
        )

        return aircraft

    def _get_final_approach_speed(self, aircraft_type: str) -> int:
        """
        Calculate appropriate final approach speed based on aircraft type

        Args:
            aircraft_type: Aircraft type code (e.g., 'B738', 'C172')

        Returns:
            Ground speed in knots appropriate for final approach
        """
        from utils.constants import COMMON_GA_AIRCRAFT

        # Extract base aircraft type (remove suffix like /L)
        base_type = aircraft_type.split('/')[0]

        # GA aircraft fly slower approach speeds (70-90 knots)
        if base_type in COMMON_GA_AIRCRAFT:
            return random.randint(70, 90)

        # Heavy jets (B744, B77W, B788, etc.) fly faster approaches (145-160 knots)
        heavy_jets = ['B744', 'B77W', 'B788', 'B789', 'A359', 'B763', 'A333', 'A332', 'B772']
        if base_type in heavy_jets:
            return random.randint(145, 160)

        # Standard jets (B738, A320, etc.) fly medium approach speeds (135-150 knots)
        return random.randint(135, 150)
