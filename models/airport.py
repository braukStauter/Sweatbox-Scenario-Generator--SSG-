"""
Airport data models
"""
from dataclasses import dataclass
from typing import List


@dataclass
class ParkingSpot:
    """Represents a parking spot at an airport"""
    name: str
    latitude: float
    longitude: float
    heading: int


@dataclass
class Runway:
    """Represents a runway at an airport"""
    name: str
    coordinates: List[tuple]
    threshold: str = None

    def get_runway_ends(self) -> tuple:
        """Get the two runway designators (e.g., ('7L', '25R'))"""
        parts = self.name.split(" - ")
        return (parts[0].strip(), parts[1].strip())

    def get_threshold_position(self, runway_end: str) -> tuple:
        """Get the threshold position (lat, lon) for a specific runway end"""
        ends = self.get_runway_ends()
        if runway_end == ends[0]:
            lon, lat = self.coordinates[0]
            return (lat, lon)
        elif runway_end == ends[1]:
            lon, lat = self.coordinates[-1]
            return (lat, lon)
        else:
            raise ValueError(f"Runway end {runway_end} not found in runway {self.name}")

    def get_runway_heading(self, runway_end: str) -> float:
        """Get the magnetic heading for a specific runway end based on actual centerline"""
        from utils.geo_utils import calculate_bearing

        ends = self.get_runway_ends()

        if runway_end == ends[0]:
            lon1, lat1 = self.coordinates[0]
            lon2, lat2 = self.coordinates[-1]
        elif runway_end == ends[1]:
            lon1, lat1 = self.coordinates[-1]
            lon2, lat2 = self.coordinates[0]
        else:
            raise ValueError(f"Runway end {runway_end} not found in runway {self.name}")

        bearing = calculate_bearing(lat1, lon1, lat2, lon2)
        return bearing


@dataclass
class Waypoint:
    """Represents a waypoint from CIFP data"""
    name: str
    latitude: float
    longitude: float
    arrival_name: str = None
    min_altitude: int = None
    max_altitude: int = None
