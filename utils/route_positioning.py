"""
Route Positioning Logic for Enroute Scenarios
Parses flight routes and calculates spawn positions within ARTCC boundaries
"""
import logging
import random
import re
import math
from typing import Optional, List, Tuple, Dict
from utils.waypoint_database import get_waypoint_database
from utils.artcc_utils import get_artcc_boundaries

logger = logging.getLogger(__name__)


class RouteParser:
    """Parses IFR route strings and calculates positioning"""

    def __init__(self):
        """Initialize route parser"""
        self.waypoint_db = get_waypoint_database()
        self.artcc_boundaries = get_artcc_boundaries()

    def parse_route_string(self, route: str) -> List[str]:
        """
        Parse route string into list of waypoint names

        Args:
            route: Route string (e.g., "KPHX.BAYLR6 BAYLR J2 TFD J58 GBN.KORD/0123")

        Returns:
            List of waypoint names
        """
        if not route:
            return []

        # Remove common procedure suffixes and clean the route
        route = route.upper().strip()

        # Remove any trailing /#### (e.g., /0324)
        if '/' in route:
            route = route.split('/')[0]

        # Replace dots with spaces for consistent parsing
        route = route.replace('.', ' ').replace('  ', ' ')

        # Split by spaces
        parts = route.split()

        waypoints = []
        for part in parts:
            # Skip empty parts
            if not part:
                continue

            # Skip airways (J-routes, Q-routes, T-routes, V-routes)
            if re.match(r'^[JQTV]\d+$', part):
                continue

            # Skip airport codes (start with K, C, or M and 4 chars)
            if re.match(r'^[KCM][A-Z]{3}$', part):
                continue

            # Skip SID/STAR identifiers (ends with a digit, typically 1-9)
            # But include the waypoint name if it's part of the SID/STAR
            # Example: "BAYLR6" -> extract "BAYLR"
            match = re.match(r'^([A-Z]{3,5})\d+$', part)
            if match:
                waypoint_name = match.group(1)
                waypoints.append(waypoint_name)
            elif re.match(r'^[A-Z]{3,5}$', part):
                # Plain waypoint name (3-5 letters)
                waypoints.append(part)

        return waypoints

    def get_route_waypoint_coordinates(self, waypoints: List[str]) -> List[Tuple[str, float, float]]:
        """
        Get coordinates for waypoints in route

        Args:
            waypoints: List of waypoint names

        Returns:
            List of tuples: (waypoint_name, latitude, longitude)
        """
        coords = []
        for waypoint_name in waypoints:
            coord = self.waypoint_db.get_coordinates(waypoint_name)
            if coord:
                lat, lon = coord
                coords.append((waypoint_name, lat, lon))
            else:
                logger.debug(f"Waypoint {waypoint_name} not found in database")

        return coords

    def find_segments_in_artcc(self, route_coords: List[Tuple[str, float, float]], artcc_id: str) -> List[Tuple[int, str, str]]:
        """
        Find route segments that pass through ARTCC

        Args:
            route_coords: List of (waypoint_name, lat, lon) tuples
            artcc_id: ARTCC identifier

        Returns:
            List of tuples: (segment_index, waypoint1_name, waypoint2_name)
        """
        if len(route_coords) < 2:
            return []

        segments_in_artcc = []

        for i in range(len(route_coords) - 1):
            wp1_name, lat1, lon1 = route_coords[i]
            wp2_name, lat2, lon2 = route_coords[i + 1]

            # Check if either endpoint is in ARTCC
            wp1_in_artcc = self.artcc_boundaries.is_point_in_artcc(lat1, lon1, artcc_id)
            wp2_in_artcc = self.artcc_boundaries.is_point_in_artcc(lat2, lon2, artcc_id)

            # If either endpoint is in ARTCC, include this segment
            if wp1_in_artcc or wp2_in_artcc:
                segments_in_artcc.append((i, wp1_name, wp2_name))

            # TODO: Could also check midpoint for segments that cross ARTCC
            # For now, this simple check should work for most cases

        return segments_in_artcc

    def calculate_position_on_segment(self, lat1: float, lon1: float, lat2: float, lon2: float, fraction: float = 0.5) -> Tuple[float, float]:
        """
        Calculate position along route segment

        Args:
            lat1, lon1: Start point coordinates
            lat2, lon2: End point coordinates
            fraction: Position along segment (0.0 = start, 1.0 = end)

        Returns:
            Tuple of (latitude, longitude)
        """
        # Simple linear interpolation
        # For more accuracy, could use great circle calculations
        lat = lat1 + (lat2 - lat1) * fraction
        lon = lon1 + (lon2 - lon1) * fraction

        return (lat, lon)

    def calculate_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate bearing from point 1 to point 2

        Args:
            lat1, lon1: Start point
            lat2, lon2: End point

        Returns:
            Bearing in degrees (0-359)
        """
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        lon1_rad = math.radians(lon1)
        lon2_rad = math.radians(lon2)

        # Calculate bearing
        dlon = lon2_rad - lon1_rad

        y = math.sin(dlon) * math.cos(lat2_rad)
        x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)

        bearing_rad = math.atan2(y, x)
        bearing_deg = math.degrees(bearing_rad)

        # Normalize to 0-359
        bearing_deg = (bearing_deg + 360) % 360

        return bearing_deg

    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate great circle distance between two points in nautical miles

        Args:
            lat1, lon1: Start point
            lat2, lon2: End point

        Returns:
            Distance in nautical miles
        """
        # Haversine formula
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)

        a = math.sin(dLat/2) * math.sin(dLat/2) + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * \
            math.sin(dLon/2) * math.sin(dLon/2)

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        # Earth radius in nautical miles
        R = 3440.065

        distance = R * c

        return distance

    def find_nearest_waypoint_to_position(self, lat: float, lon: float, waypoints: List[Tuple[str, float, float]]) -> Optional[Tuple[str, float, float]]:
        """
        Find nearest waypoint to a position

        Args:
            lat, lon: Target position
            waypoints: List of (name, lat, lon) tuples

        Returns:
            Nearest waypoint tuple or None
        """
        if not waypoints:
            return None

        min_distance = float('inf')
        nearest_waypoint = None

        for wp_name, wp_lat, wp_lon in waypoints:
            distance = self.calculate_distance(lat, lon, wp_lat, wp_lon)
            if distance < min_distance:
                min_distance = distance
                nearest_waypoint = (wp_name, wp_lat, wp_lon)

        return nearest_waypoint

    def generate_frd_position(self, lat: float, lon: float, route_coords: List[Tuple[str, float, float]]) -> str:
        """
        Generate FRD format position string (waypoint + radial + distance)

        Args:
            lat, lon: Target position
            route_coords: Route waypoint coordinates for finding nearest fix

        Returns:
            FRD string (e.g., "BAYLR35010" = BAYLR, 350 radial, 10nm)
        """
        # Find nearest waypoint
        nearest_wp = self.find_nearest_waypoint_to_position(lat, lon, route_coords)

        if not nearest_wp:
            logger.warning("No waypoints available for FRD generation")
            return ""

        wp_name, wp_lat, wp_lon = nearest_wp

        # Calculate radial FROM waypoint TO position
        radial = self.calculate_bearing(wp_lat, wp_lon, lat, lon)

        # Calculate distance
        distance = self.calculate_distance(wp_lat, wp_lon, lat, lon)

        # Format: WAYPOINT + radial (3 digits) + distance (2 digits)
        # Round radial to nearest degree
        radial_int = int(round(radial)) % 360

        # Round distance to nearest nautical mile
        distance_int = int(round(distance))

        # Pad to ensure proper format
        frd_string = f"{wp_name}{radial_int:03d}{distance_int:02d}"

        logger.debug(f"Generated FRD: {frd_string} (from {wp_name} at {radial_int}° for {distance_int}nm)")

        return frd_string

    def generate_spawn_position_from_route(self, route: str, artcc_id: str) -> Optional[Dict]:
        """
        Generate spawn position along route within ARTCC

        Args:
            route: Route string
            artcc_id: ARTCC identifier

        Returns:
            Dict with spawn position info or None if unable to generate
        """
        # Parse route
        waypoints = self.parse_route_string(route)

        if not waypoints:
            logger.debug(f"No waypoints parsed from route: {route}")
            return None

        # Get coordinates
        route_coords = self.get_route_waypoint_coordinates(waypoints)

        if len(route_coords) < 2:
            logger.debug(f"Insufficient waypoint coordinates found: {len(route_coords)}")
            return None

        # Find segments in ARTCC
        segments = self.find_segments_in_artcc(route_coords, artcc_id)

        if not segments:
            logger.debug(f"No route segments found within ARTCC {artcc_id}")
            return None

        # Select random segment
        segment_idx, wp1_name, wp2_name = random.choice(segments)

        # Get segment coordinates
        wp1_lat, wp1_lon = None, None
        wp2_lat, wp2_lon = None, None

        for name, lat, lon in route_coords:
            if name == wp1_name:
                wp1_lat, wp1_lon = lat, lon
            if name == wp2_name:
                wp2_lat, wp2_lon = lat, lon

        if wp1_lat is None or wp2_lat is None:
            logger.warning(f"Could not find coordinates for segment waypoints")
            return None

        # Generate random position along segment
        fraction = random.uniform(0.2, 0.8)  # Avoid exact waypoint positions
        spawn_lat, spawn_lon = self.calculate_position_on_segment(
            wp1_lat, wp1_lon, wp2_lat, wp2_lon, fraction
        )

        # Verify position is within ARTCC
        if not self.artcc_boundaries.is_point_in_artcc(spawn_lat, spawn_lon, artcc_id):
            logger.debug(f"Generated position not in ARTCC, using waypoint instead")
            # Fallback to waypoint that's in ARTCC
            if self.artcc_boundaries.is_point_in_artcc(wp1_lat, wp1_lon, artcc_id):
                spawn_lat, spawn_lon = wp1_lat, wp1_lon
            else:
                spawn_lat, spawn_lon = wp2_lat, wp2_lon

        # Generate FRD string
        frd_string = self.generate_frd_position(spawn_lat, spawn_lon, route_coords)

        # Calculate heading (bearing from wp1 to wp2)
        heading = self.calculate_bearing(wp1_lat, wp1_lon, wp2_lat, wp2_lon)

        return {
            'frd': frd_string,
            'latitude': spawn_lat,
            'longitude': spawn_lon,
            'heading': heading,
            'segment': f"{wp1_name} to {wp2_name}",
            'route_waypoints': waypoints
        }


def generate_spawn_position(route: str, artcc_id: str, fallback_frd: Optional[str] = None) -> Optional[Dict]:
    """
    Generate spawn position for aircraft with automatic fallback

    Args:
        route: Route string
        artcc_id: ARTCC identifier
        fallback_frd: Fallback FRD string if route parsing fails

    Returns:
        Dict with spawn position info or None
    """
    parser = RouteParser()

    # Try intelligent route positioning first
    position = parser.generate_spawn_position_from_route(route, artcc_id)

    if position:
        logger.info(f"Generated spawn position via route parsing: {position['frd']}")
        return position

    # Fallback to manual FRD if provided
    if fallback_frd:
        logger.info(f"Using fallback FRD position: {fallback_frd}")
        # Parse FRD string to extract position
        frd_position = parse_frd_string(fallback_frd)
        if frd_position:
            return frd_position

    logger.warning(f"Unable to generate spawn position for route: {route}")
    return None


def parse_frd_string(frd: str) -> Optional[Dict]:
    """
    Parse FRD format string into position data

    Args:
        frd: FRD string (e.g., "BAYLR35010")

    Returns:
        Dict with position info or None
    """
    # FRD format: WAYPOINT + radial (3 digits) + distance (2 digits)
    # Example: BAYLR35010 = BAYLR, 350°, 10nm
    match = re.match(r'^([A-Z]{3,5})(\d{3})(\d{2})$', frd.upper())

    if not match:
        logger.warning(f"Invalid FRD format: {frd}")
        return None

    waypoint_name = match.group(1)
    radial = int(match.group(2))
    distance = int(match.group(3))

    # Get waypoint coordinates
    waypoint_db = get_waypoint_database()
    coords = waypoint_db.get_coordinates(waypoint_name)

    if not coords:
        logger.warning(f"Waypoint {waypoint_name} not found for FRD {frd}")
        return None

    wp_lat, wp_lon = coords

    # Calculate position at radial/distance from waypoint
    lat, lon = calculate_position_from_frd(wp_lat, wp_lon, radial, distance)

    return {
        'frd': frd,
        'latitude': lat,
        'longitude': lon,
        'heading': radial,  # Use radial as initial heading
        'waypoint': waypoint_name,
        'radial': radial,
        'distance': distance
    }


def calculate_position_from_frd(lat: float, lon: float, bearing: float, distance_nm: float) -> Tuple[float, float]:
    """
    Calculate position from a point given bearing and distance

    Args:
        lat, lon: Starting position
        bearing: Bearing in degrees
        distance_nm: Distance in nautical miles

    Returns:
        Tuple of (latitude, longitude)
    """
    # Earth radius in nautical miles
    R = 3440.065

    # Convert to radians
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing)

    # Calculate new position
    lat2_rad = math.asin(
        math.sin(lat_rad) * math.cos(distance_nm / R) +
        math.cos(lat_rad) * math.sin(distance_nm / R) * math.cos(bearing_rad)
    )

    lon2_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(distance_nm / R) * math.cos(lat_rad),
        math.cos(distance_nm / R) - math.sin(lat_rad) * math.sin(lat2_rad)
    )

    # Convert back to degrees
    lat2 = math.degrees(lat2_rad)
    lon2 = math.degrees(lon2_rad)

    return (lat2, lon2)
