"""
Tower (Departures/Arrivals) scenario
"""
import random
import logging
from typing import List, Tuple

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.geo_utils import calculate_destination, get_reciprocal_heading

logger = logging.getLogger(__name__)


class TowerMixedScenario(BaseScenario):
    """Scenario for Tower position with departures and arrivals"""

    def generate(self, num_departures: int, num_arrivals: int, active_runways: List[str],
                 separation_range: Tuple[int, int] = (3, 6),
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None, total_session_minutes: int = None,
                 spawn_delay_range: str = None, difficulty_config=None) -> List[Aircraft]:
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
        ga_spots = self.geojson_parser.get_parking_spots(filter_ga=True)

        if num_departures > len(parking_spots):
            raise ValueError(
                f"Cannot create {num_departures} aircraft with only {len(parking_spots)} parking spots available"
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

                aircraft = self._create_departure_aircraft(spot)
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

        # Generate arrivals with random separation
        # If spawn delay > 2 minutes, all aircraft spawn at 5 NM (no spacing needed since they spawn sequentially)
        # Otherwise, use progressive spacing since they all spawn at once
        use_fixed_distance = max_delay > 120  # 2 minutes in seconds

        for i in range(num_arrivals):
            runway_name = active_runways[i % len(active_runways)]

            if use_fixed_distance:
                distance_nm = 5  # Fixed 5 NM final approach position
            else:
                # Random separation within specified range
                base_distance = 6
                separation = random.randint(separation_range[0], separation_range[1])
                # Calculate cumulative distance
                distance_nm = base_distance + (i // len(active_runways)) * separation

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
        Create an arrival aircraft on final approach

        Args:
            runway_name: Runway designator
            distance_nm: Distance from runway threshold in nautical miles

        Returns:
            Aircraft object
        """
        # Get runway data
        runway = self.geojson_parser.get_runway_by_name(runway_name)
        threshold_lat, threshold_lon = runway.get_threshold_position(runway_name)

        # Get actual runway centerline heading (calculated from coordinates)
        runway_heading = runway.get_runway_heading(runway_name)
        logger.debug(f"Runway {runway_name} centerline heading: {runway_heading:.1f}°")

        # Calculate position on final approach (use reciprocal for inbound heading)
        approach_heading = get_reciprocal_heading(runway_heading)
        lat, lon = calculate_destination(threshold_lat, threshold_lon, approach_heading, distance_nm)

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

        # Calculate altitude based on FAF altitude + 1000 ft, with 3-degree glideslope
        field_elevation = self.geojson_parser.field_elevation

        # Try to get FAF altitude from CIFP data
        faf_altitude = None
        if self.cifp_parser:
            faf_altitude = self.cifp_parser.get_faf_altitude(runway_name)

        if faf_altitude:
            # Use FAF altitude + 1000 ft as the baseline starting altitude
            baseline_altitude = faf_altitude + 1000

            # FAF is typically around 5 NM from threshold
            # If aircraft is beyond FAF distance, use baseline altitude
            # If within FAF distance, descend on glideslope toward field elevation
            faf_distance_nm = 5.0  # Typical FAF distance

            if distance_nm >= faf_distance_nm:
                # Beyond FAF - use baseline altitude
                altitude = baseline_altitude
            else:
                # Within FAF - descend on 3-degree glideslope
                # Calculate altitude on glideslope from field elevation
                glideslope_altitude = field_elevation + int(distance_nm * 300)
                # Use the higher of glideslope or a reasonable minimum
                altitude = max(glideslope_altitude, baseline_altitude - int((faf_distance_nm - distance_nm) * 200))

            logger.debug(f"Runway {runway_name}: FAF alt {faf_altitude}, baseline {baseline_altitude}, final {altitude} ft at {distance_nm:.1f} NM")
        else:
            # No FAF data - fall back to glideslope from field elevation
            altitude_agl = int(distance_nm * 300)
            altitude = field_elevation + altitude_agl

            # Ensure minimum altitude for aircraft beyond 8 NM
            if distance_nm > 8:
                min_altitude = field_elevation + 2400  # 8 NM * 300 ft/NM
                altitude = max(altitude, min_altitude)

            logger.debug(f"Final approach (no FAF data): {distance_nm:.1f} NM out, altitude: {altitude} ft")

        # Ground speed on approach
        ground_speed = 140

        logger.info(f"Creating arrival: {callsign} at {distance_nm:.1f} NM, alt {altitude} ft, hdg {int(runway_heading)}°, spd {ground_speed} kts")

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=flight_plan['aircraft_type'],
            latitude=lat,
            longitude=lon,
            altitude=altitude,
            heading=int(runway_heading),
            ground_speed=ground_speed,
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
