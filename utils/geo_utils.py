"""
Geographic utilities for coordinate calculations
"""
import math
from typing import Tuple


def nm_to_degrees(nm: float) -> float:
    """
    Convert nautical miles to degrees of latitude/longitude

    Args:
        nm: Distance in nautical miles

    Returns:
        Distance in degrees
    """
    return nm / 60.0


def calculate_destination(lat: float, lon: float, heading: int, distance_nm: float) -> Tuple[float, float]:
    """
    Calculate destination coordinates given start point, heading, and distance

    Args:
        lat: Starting latitude in degrees
        lon: Starting longitude in degrees
        heading: Heading in degrees (0-360)
        distance_nm: Distance in nautical miles

    Returns:
        (latitude, longitude) tuple
    """
    # Convert to radians
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    heading_rad = math.radians(heading)

    # Earth's radius in nautical miles
    R = 3440.065

    # Calculate destination
    lat2_rad = math.asin(
        math.sin(lat_rad) * math.cos(distance_nm / R) +
        math.cos(lat_rad) * math.sin(distance_nm / R) * math.cos(heading_rad)
    )

    lon2_rad = lon_rad + math.atan2(
        math.sin(heading_rad) * math.sin(distance_nm / R) * math.cos(lat_rad),
        math.cos(distance_nm / R) - math.sin(lat_rad) * math.sin(lat2_rad)
    )

    # Convert back to degrees
    lat2 = math.degrees(lat2_rad)
    lon2 = math.degrees(lon2_rad)

    return (lat2, lon2)


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """
    Calculate bearing between two points

    Args:
        lat1: Starting latitude in degrees
        lon1: Starting longitude in degrees
        lat2: Ending latitude in degrees
        lon2: Ending longitude in degrees

    Returns:
        Bearing in degrees (0-360)
    """
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    lon_diff = math.radians(lon2 - lon1)

    # Calculate bearing
    y = math.sin(lon_diff) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - \
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lon_diff)

    bearing_rad = math.atan2(y, x)
    bearing = (math.degrees(bearing_rad) + 360) % 360

    return int(bearing)


def calculate_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points using Haversine formula

    Args:
        lat1: Starting latitude in degrees
        lon1: Starting longitude in degrees
        lat2: Ending latitude in degrees
        lon2: Ending longitude in degrees

    Returns:
        Distance in nautical miles
    """
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    # Haversine formula
    a = math.sin(dlat / 2) ** 2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    # Earth's radius in nautical miles
    R = 3440.065

    return R * c


def get_reciprocal_heading(heading: int) -> int:
    """
    Get the reciprocal (opposite) heading

    Args:
        heading: Original heading (0-360)

    Returns:
        Reciprocal heading (0-360)
    """
    reciprocal = (heading + 180) % 360
    return reciprocal
