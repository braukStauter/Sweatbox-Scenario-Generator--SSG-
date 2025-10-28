"""
ARTCC geographic lookup using boundary polygons
"""
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def point_in_polygon(lat: float, lon: float, polygon_coords: list) -> bool:
    """
    Check if a point is inside a polygon using ray casting algorithm

    Args:
        lat: Latitude of the point
        lon: Longitude of the point
        polygon_coords: List of [lon, lat] coordinate pairs defining the polygon

    Returns:
        True if point is inside polygon, False otherwise
    """
    # Ray casting algorithm
    inside = False
    n = len(polygon_coords)

    p1_lon, p1_lat = polygon_coords[0]
    for i in range(1, n + 1):
        p2_lon, p2_lat = polygon_coords[i % n]

        if lat > min(p1_lat, p2_lat):
            if lat <= max(p1_lat, p2_lat):
                if lon <= max(p1_lon, p2_lon):
                    if p1_lat != p2_lat:
                        x_intersect = (lat - p1_lat) * (p2_lon - p1_lon) / (p2_lat - p1_lat) + p1_lon
                    if p1_lon == p2_lon or lon <= x_intersect:
                        inside = not inside

        p1_lon, p1_lat = p2_lon, p2_lat

    return inside


def get_airport_coordinates(airport_icao: str) -> Optional[Tuple[float, float]]:
    """
    Get airport coordinates from FlightRadar24 API

    Args:
        airport_icao: Airport ICAO code (e.g., 'KPHX')

    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    try:
        from flightradar24.api import FlightRadar24API

        fr_api = FlightRadar24API()

        # Remove 'K' prefix if present (FlightRadar24 uses 3-letter codes)
        airport_code = airport_icao
        if airport_icao.startswith('K') and len(airport_icao) == 4:
            airport_code = airport_icao[1:]

        # Fetch airport details
        airport_data = fr_api.get_airport_details(airport_code)

        if (airport_data and
            'airport' in airport_data and
            airport_data['airport'] and
            'pluginData' in airport_data['airport']):

            plugin_data = airport_data['airport']['pluginData']

            if ('details' in plugin_data and
                'position' in plugin_data['details'] and
                'latitude' in plugin_data['details']['position'] and
                'longitude' in plugin_data['details']['position']):

                lat = plugin_data['details']['position']['latitude']
                lon = plugin_data['details']['position']['longitude']

                logger.info(f"Fetched coordinates for {airport_icao}: {lat}, {lon}")
                return (lat, lon)

        logger.warning(f"Could not find coordinates for {airport_icao}")
        return None

    except Exception as e:
        logger.error(f"Error fetching airport coordinates: {e}")
        return None


def get_artcc_for_airport(airport_icao: str) -> str:
    """
    Determine which ARTCC controls an airport based on geographic boundaries

    Args:
        airport_icao: Airport ICAO code (e.g., 'KPHX')

    Returns:
        ARTCC ID (e.g., 'ZAB') or 'ZAB' as default if not found
    """
    try:
        # Get airport coordinates
        coords = get_airport_coordinates(airport_icao)
        if not coords:
            logger.warning(f"No coordinates for {airport_icao}, defaulting to ZAB")
            return "ZAB"

        lat, lon = coords

        # Load ARTCC boundaries
        boundaries_path = Path(__file__).parent / "artcc_boundaries.geojson"
        with open(boundaries_path, 'r') as f:
            boundaries_data = json.load(f)

        # Check each ARTCC boundary
        for feature in boundaries_data.get('features', []):
            artcc_id = feature.get('properties', {}).get('id')
            geometry = feature.get('geometry', {})

            if geometry.get('type') == 'Polygon':
                # Polygon has one ring (exterior boundary)
                coords_ring = geometry.get('coordinates', [[]])[0]

                if point_in_polygon(lat, lon, coords_ring):
                    logger.info(f"Airport {airport_icao} is in ARTCC {artcc_id}")
                    return artcc_id

            elif geometry.get('type') == 'MultiPolygon':
                # MultiPolygon has multiple rings
                for polygon in geometry.get('coordinates', []):
                    coords_ring = polygon[0]  # First ring is exterior boundary

                    if point_in_polygon(lat, lon, coords_ring):
                        logger.info(f"Airport {airport_icao} is in ARTCC {artcc_id}")
                        return artcc_id

        logger.warning(f"Airport {airport_icao} not found in any ARTCC boundary, defaulting to ZAB")
        return "ZAB"

    except Exception as e:
        logger.error(f"Error determining ARTCC for {airport_icao}: {e}", exc_info=True)
        return "ZAB"
