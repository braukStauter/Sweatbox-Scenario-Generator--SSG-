"""
Base scenario class
"""
import random
import logging
import json
from typing import List, Dict
from abc import ABC, abstractmethod
from pathlib import Path

from models.aircraft import Aircraft
from parsers.geojson_parser import GeoJSONParser
from parsers.cifp_parser import CIFPParser
from utils.api_client import FlightPlanAPIClient
from utils.constants import POPULAR_US_AIRPORTS, LESS_COMMON_AIRPORTS, COMMON_JETS, COMMON_GA_AIRCRAFT

logger = logging.getLogger(__name__)


class BaseScenario(ABC):
    """Base class for all scenario types"""

    def __init__(self, airport_icao: str, geojson_parser: GeoJSONParser,
                 cifp_parser: CIFPParser, api_client: FlightPlanAPIClient):
        """
        Initialize the scenario

        Args:
            airport_icao: ICAO code of the primary airport
            geojson_parser: Parser for airport GeoJSON data
            cifp_parser: Parser for CIFP data
            api_client: API client for flight plans
        """
        self.airport_icao = airport_icao
        self.geojson_parser = geojson_parser
        self.cifp_parser = cifp_parser
        self.api_client = api_client
        self.aircraft: List[Aircraft] = []
        self.used_callsigns: set = set()
        self.used_parking_spots: set = set()
        self.config = self._load_config()

    @abstractmethod
    def generate(self, **kwargs) -> List[Aircraft]:
        """
        Generate aircraft for this scenario

        Returns:
            List of Aircraft objects
        """
        pass

    def _reset_tracking(self):
        """Reset tracking sets for a new generation"""
        self.used_callsigns.clear()
        self.used_parking_spots.clear()
        self.aircraft.clear()
        logger.debug("Reset tracking sets for new generation")

    def _setup_difficulty_assignment(self, difficulty_config):
        """
        Setup difficulty assignment tracking

        Args:
            difficulty_config: Dict with 'easy', 'medium', 'hard' counts, or None

        Returns:
            Tuple of (difficulty_list, difficulty_index) for sequential assignment
        """
        if not difficulty_config:
            return None, 0

        # Create a list of difficulty levels in the order they should be assigned
        difficulty_list = []
        difficulty_list.extend(['Easy'] * difficulty_config['easy'])
        difficulty_list.extend(['Medium'] * difficulty_config['medium'])
        difficulty_list.extend(['Hard'] * difficulty_config['hard'])

        # Shuffle to randomize difficulty assignment
        import random
        random.shuffle(difficulty_list)

        logger.info(f"Difficulty assignment enabled: {difficulty_config['easy']} Easy, {difficulty_config['medium']} Medium, {difficulty_config['hard']} Hard")

        return difficulty_list, 0

    def _assign_difficulty(self, aircraft, difficulty_list, difficulty_index):
        """
        Assign difficulty level to an aircraft

        Args:
            aircraft: Aircraft object to assign difficulty to
            difficulty_list: List of difficulty levels
            difficulty_index: Current index in difficulty list

        Returns:
            Updated difficulty_index
        """
        if difficulty_list and difficulty_index < len(difficulty_list):
            aircraft.difficulty = difficulty_list[difficulty_index]
            logger.debug(f"Assigned difficulty {aircraft.difficulty} to {aircraft.callsign}")
            return difficulty_index + 1
        return difficulty_index

    def _parse_spawn_delay_range(self, spawn_delay_range: str) -> tuple:
        """
        Parse spawn delay range string into min/max values in seconds

        Args:
            spawn_delay_range: String in format "min-max" in MINUTES (e.g., "0-0" or "1-5")

        Returns:
            Tuple of (min_delay, max_delay) in SECONDS
        """
        min_delay_minutes, max_delay_minutes = 0, 0  # defaults - spawn all at once
        if spawn_delay_range:
            try:
                parts = spawn_delay_range.split('-')
                if len(parts) == 2:
                    min_delay_minutes = int(parts[0])
                    max_delay_minutes = int(parts[1])
            except ValueError:
                logger.warning(f"Invalid spawn delay range: {spawn_delay_range}, using default (0-0)")

        # Convert minutes to seconds for vNAS
        min_delay_seconds = min_delay_minutes * 60
        max_delay_seconds = max_delay_minutes * 60

        return min_delay_seconds, max_delay_seconds

    def _load_config(self) -> Dict:
        """
        Load configuration from config.json file

        Returns:
            Configuration dictionary
        """
        config_path = Path("config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded configuration from {config_path}")
                    return config
            except Exception as e:
                logger.warning(f"Error loading config file: {e}. Using default configuration.")
                return {}
        else:
            logger.info("No config.json found. Using default configuration.")
            return {}

    def _get_airline_for_parking(self, parking_name: str) -> str:
        """
        Get a specific airline code for a parking spot based on configuration
        Supports wildcards using # (e.g., "A#" matches "A1", "A2", "A10", etc.)
        """
        parking_airlines = self.config.get('parking_airlines', {})

        if self.airport_icao in parking_airlines:
            airport_config = parking_airlines[self.airport_icao]

            if parking_name in airport_config:
                airlines = airport_config[parking_name]
                if airlines:
                    return random.choice(airlines)

            for pattern, airlines in airport_config.items():
                if '#' in pattern:
                    prefix = pattern.replace('#', '')
                    if parking_name.startswith(prefix):
                        if airlines:
                            return random.choice(airlines)

        return None

    def _get_available_parking_spots(self, all_spots: List, ga_only: bool = None) -> List:
        """Get available parking spots that haven't been used yet"""
        available = []
        for spot in all_spots:
            if spot.name in self.used_parking_spots:
                continue

            is_ga_spot = 'GA' in spot.name.upper()
            if ga_only is True and not is_ga_spot:
                continue
            if ga_only is False and is_ga_spot:
                continue

            available.append(spot)

        return available

    def _generate_callsign(self, number_suffix: str = None, airline: str = None) -> str:
        """Generate a random callsign, ensuring it's unique"""
        airlines = ["AAL", "DAL", "UAL", "SWA", "JBU", "ASA", "SKW", "FFT", "FDX", "UPS"]

        for _ in range(100):
            selected_airline = airline if airline else random.choice(airlines)

            if number_suffix:
                base_number = random.randint(10, 99)
                flight_number = f"{base_number}{number_suffix}"
            else:
                flight_number = str(random.randint(100, 9999))

            callsign = f"{selected_airline}{flight_number}"

            if callsign not in self.used_callsigns:
                return callsign

        logger.warning("Could not generate unique callsign after 100 attempts, using fallback")
        return f"{selected_airline}{flight_number}{len(self.used_callsigns)}"

    def _generate_ga_callsign(self) -> str:
        """Generate a general aviation N-number callsign, ensuring it's unique"""
        letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        digits = "0123456789"

        for _ in range(100):
            n_number = "N"
            n_number += ''.join(random.choices(digits, k=3))
            n_number += ''.join(random.choices(letters, k=2))

            if n_number not in self.used_callsigns:
                return n_number

        logger.warning("Could not generate unique GA callsign after 100 attempts, using fallback")
        return f"N{len(self.used_callsigns):03d}AB"

    def _get_random_destination(self, exclude: str = None, less_common: bool = False) -> str:
        """Get a random US airport"""
        if less_common:
            airports = [apt for apt in LESS_COMMON_AIRPORTS if apt != exclude]
        else:
            airports = [apt for apt in POPULAR_US_AIRPORTS if apt != exclude]
        return random.choice(airports)

    def _get_random_aircraft_type(self, is_ga: bool = False) -> str:
        """Get a random aircraft type"""
        if is_ga:
            return random.choice(COMMON_GA_AIRCRAFT)
        else:
            return random.choice(COMMON_JETS)

    def _create_departure_aircraft(self, parking_spot, destination: str = None,
                                   callsign: str = None, aircraft_type: str = None) -> Aircraft:
        """Create a departure aircraft at a parking spot"""
        if parking_spot.name in self.used_parking_spots:
            logger.warning(f"Parking spot {parking_spot.name} is already in use, skipping")
            return None

        self.used_parking_spots.add(parking_spot.name)
        logger.debug(f"Assigned parking spot: {parking_spot.name}")

        if destination is None:
            destination = self._get_random_destination(exclude=self.airport_icao)

        flight_plan = self.api_client.get_random_flight_plan(self.airport_icao, destination)

        if callsign is None:
            parking_airline = self._get_airline_for_parking(parking_spot.name)
            if parking_airline:
                callsign = self._generate_callsign(airline=parking_airline)
            else:
                callsign = flight_plan.get('callsign') or self._generate_callsign()

        if callsign in self.used_callsigns:
            parking_airline = self._get_airline_for_parking(parking_spot.name)
            callsign = self._generate_callsign(airline=parking_airline)

        self.used_callsigns.add(callsign)

        if aircraft_type is None:
            aircraft_type = flight_plan['aircraft_type']

        ground_altitude = self.geojson_parser.field_elevation

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=parking_spot.latitude,
            longitude=parking_spot.longitude,
            altitude=ground_altitude,
            heading=parking_spot.heading,
            ground_speed=0,
            departure=self.airport_icao,
            arrival=destination,
            route=flight_plan['route'],
            cruise_altitude=flight_plan['altitude'],
            flight_rules="I",
            engine_type="J",
            parking_spot_name=parking_spot.name
        )

        return aircraft

    def _create_ga_aircraft(self, parking_spot, destination: str = None) -> Aircraft:
        """Create a GA (general aviation) aircraft"""
        if parking_spot.name in self.used_parking_spots:
            logger.warning(f"Parking spot {parking_spot.name} is already in use, skipping")
            return None

        self.used_parking_spots.add(parking_spot.name)
        logger.debug(f"Assigned parking spot: {parking_spot.name}")

        callsign = self._generate_ga_callsign()
        self.used_callsigns.add(callsign)

        aircraft_type = self._get_random_aircraft_type(is_ga=True)

        if '/' not in aircraft_type:
            aircraft_type = f"{aircraft_type}/G"

        ground_altitude = self.geojson_parser.field_elevation

        if destination is None:
            destination = self._get_random_destination(exclude=self.airport_icao, less_common=True)

        cruise_altitude = random.randint(3000, 8000)
        route = f"DCT"

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=parking_spot.latitude,
            longitude=parking_spot.longitude,
            altitude=ground_altitude,
            heading=parking_spot.heading,
            ground_speed=0,
            departure=self.airport_icao,
            arrival=destination,
            route=route,
            cruise_altitude=str(cruise_altitude),
            flight_rules="I",
            engine_type="P",
            parking_spot_name=parking_spot.name
        )

        return aircraft

    def get_aircraft(self) -> List[Aircraft]:
        """Get generated aircraft list"""
        return self.aircraft
