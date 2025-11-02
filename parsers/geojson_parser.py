"""
Parser for airport GeoJSON files
"""
import json
import logging
from typing import List, Dict
from models.airport import ParkingSpot, Runway
from utils.airport_utils import get_airport_elevation

logger = logging.getLogger(__name__)


class GeoJSONParser:
    """Parser for airport GeoJSON files containing parking and runway data"""

    def __init__(self, geojson_path: str, airport_icao: str = None):
        """Initialize the parser"""
        self.geojson_path = geojson_path
        self.airport_icao = airport_icao
        self.parking_spots: List[ParkingSpot] = []
        self.runways: List[Runway] = []
        self.field_elevation: int = 1000
        self._load_data()

        if airport_icao:
            elevation = get_airport_elevation(airport_icao)
            if elevation:
                self.field_elevation = elevation
            else:
                logger.warning(f"Could not fetch elevation for {airport_icao}, using default: {self.field_elevation} ft MSL")
            logger.info(f"Field elevation for {airport_icao}: {self.field_elevation} ft MSL")

    def _load_data(self):
        """Load and parse the GeoJSON file"""
        try:
            with open(self.geojson_path, 'r') as f:
                data = json.load(f)

            features = data.get('features', [])

            for feature in features:
                properties = feature.get('properties', {})
                geometry = feature.get('geometry', {})
                feature_type = properties.get('type', '')

                if feature_type == 'parking':
                    self._parse_parking(properties, geometry)
                elif feature_type == 'runway':
                    self._parse_runway(properties, geometry)

            logger.info(f"Loaded {len(self.parking_spots)} parking spots and {len(self.runways)} runways")

        except Exception as e:
            logger.error(f"Error loading GeoJSON: {e}")
            raise

    def _parse_parking(self, properties: Dict, geometry: Dict):
        """Parse a parking spot from GeoJSON"""
        try:
            name = properties.get('name')
            heading = properties.get('heading', 0)
            coords = geometry.get('coordinates', [])

            if coords and len(coords) >= 2:
                lon, lat = coords[0], coords[1]
                parking = ParkingSpot(
                    name=name,
                    latitude=lat,
                    longitude=lon,
                    heading=heading
                )
                self.parking_spots.append(parking)

        except Exception as e:
            logger.warning(f"Error parsing parking spot: {e}")

    def _parse_runway(self, properties: Dict, geometry: Dict):
        """Parse a runway from GeoJSON"""
        try:
            name = properties.get('name')
            threshold = properties.get('threshold')
            coords = geometry.get('coordinates', [])

            if coords and len(coords) > 0:
                runway = Runway(
                    name=name,
                    coordinates=coords,
                    threshold=threshold
                )
                self.runways.append(runway)

        except Exception as e:
            logger.warning(f"Error parsing runway: {e}")

    def get_parking_spots(self, filter_ga: bool = False) -> List[ParkingSpot]:
        """Get parking spots, optionally filtered for GA"""
        if filter_ga:
            return [spot for spot in self.parking_spots if 'GA' in spot.name.upper()]
        return self.parking_spots

    def get_runways(self) -> List[Runway]:
        """Get all runways"""
        return self.runways

    def get_airport_center(self) -> tuple:
        """Calculate airport center coordinates from runway data"""
        if self.runways:
            all_lats = []
            all_lons = []

            for runway in self.runways:
                for coord in runway.coordinates:
                    all_lons.append(coord[0])
                    all_lats.append(coord[1])

            if all_lats and all_lons:
                center_lat = sum(all_lats) / len(all_lats)
                center_lon = sum(all_lons) / len(all_lons)
                return (center_lat, center_lon)

        if self.parking_spots:
            all_lats = [spot.latitude for spot in self.parking_spots]
            all_lons = [spot.longitude for spot in self.parking_spots]
            center_lat = sum(all_lats) / len(all_lats)
            center_lon = sum(all_lons) / len(all_lons)
            return (center_lat, center_lon)

        return (0.0, 0.0)

    def get_runway_by_name(self, runway_name: str) -> Runway:
        """Get a specific runway by its end designator"""
        for runway in self.runways:
            ends = runway.get_runway_ends()
            if runway_name in ends:
                return runway

        raise ValueError(f"Runway {runway_name} not found")
