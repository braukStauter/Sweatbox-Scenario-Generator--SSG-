"""
Waypoint Database for global waypoint coordinate lookups
Used for enroute scenario positioning and route parsing
"""
import logging
import os
from typing import Dict, Optional, Tuple
from models.airport import Waypoint

logger = logging.getLogger(__name__)


class WaypointDatabase:
    """Global waypoint database for coordinate lookups"""

    def __init__(self, cifp_path: str = None):
        """
        Initialize waypoint database

        Args:
            cifp_path: Path to CIFP file. If None, uses default path.
        """
        self.waypoints: Dict[str, Waypoint] = {}
        self._loaded = False

        # Default CIFP path - check both possible locations
        if cifp_path is None:
            if os.path.exists(os.path.join('airport_data', 'FAACIFP18')):
                cifp_path = os.path.join('airport_data', 'FAACIFP18')
            else:
                cifp_path = os.path.join('cifp_data', 'FAACIFP18')

        self.cifp_path = cifp_path

    def _ensure_loaded(self):
        """Lazy load waypoint data on first access"""
        if not self._loaded:
            self._load_waypoints()
            self._loaded = True

    def _load_waypoints(self):
        """Load all waypoint definitions from CIFP file"""
        if not os.path.exists(self.cifp_path):
            logger.warning(f"CIFP file not found: {self.cifp_path}")
            return

        try:
            with open(self.cifp_path, 'r', encoding='latin-1') as f:
                for line in f:
                    # Parse waypoint definition lines (subsection C)
                    # Format: SUSAE + subsection 'C' or subsection 'A' for airport waypoints
                    if len(line) < 50:
                        continue

                    record_type = line[0:5].strip()

                    # Only parse waypoint definition records
                    if record_type == 'SUSAE':
                        subsection = line[5] if len(line) > 5 else ''
                        if subsection == 'A':  # Enroute waypoints
                            self._parse_waypoint_definition(line)
                    elif record_type in ['SUSAP', 'SUSAD']:
                        # Terminal area waypoints (airport-specific)
                        subsection = line[12] if len(line) > 12 else ''
                        if subsection == 'C':
                            self._parse_waypoint_definition(line)

            logger.info(f"Loaded {len(self.waypoints)} waypoints from CIFP")

        except Exception as e:
            logger.error(f"Error loading waypoint database: {e}")

    def _parse_waypoint_definition(self, line: str):
        """Parse a waypoint definition line from CIFP"""
        try:
            # Waypoint name at position 13-18
            waypoint_name = line[13:18].strip()

            if not waypoint_name:
                return

            # Latitude at position 32-41
            lat_str = line[32:41].strip()
            latitude = self._parse_coordinate(lat_str, is_latitude=True)

            # Longitude at position 41-51
            lon_str = line[41:51].strip()
            longitude = self._parse_coordinate(lon_str, is_latitude=False)

            if latitude is not None and longitude is not None:
                waypoint = Waypoint(
                    name=waypoint_name,
                    latitude=latitude,
                    longitude=longitude
                )

                # Store with full name
                self.waypoints[waypoint_name] = waypoint

                # Also store without common prefixes for better matching
                # Common prefixes: ET, BI, CY, EN, PA, etc.
                if len(waypoint_name) == 5:
                    # Try storing without first 2 chars as prefix
                    suffix = waypoint_name[2:]
                    if len(suffix) == 3:
                        # Only store if we don't already have this shorter name
                        if suffix not in self.waypoints:
                            self.waypoints[suffix] = waypoint
                            logger.debug(f"Also stored waypoint as: {suffix}")

                logger.debug(f"Loaded waypoint: {waypoint_name} at {latitude}, {longitude}")

        except Exception as e:
            logger.debug(f"Error parsing waypoint definition: {e}")

    def _parse_coordinate(self, coord_str: str, is_latitude: bool) -> Optional[float]:
        """
        Parse coordinate from CIFP format

        Format: DDDMMSSSS where DDD=degrees, MM=minutes, SSSS=seconds*100
        First character is direction (N/S for lat, E/W for lon)
        """
        try:
            if not coord_str or len(coord_str) < 8:
                return None

            direction = coord_str[0]
            coord_digits = coord_str[1:]

            if is_latitude:
                degrees = int(coord_digits[0:2])
                minutes = int(coord_digits[2:4])
                seconds = int(coord_digits[4:]) / 100.0
            else:
                degrees = int(coord_digits[0:3])
                minutes = int(coord_digits[3:5])
                seconds = int(coord_digits[5:]) / 100.0

            decimal = degrees + minutes / 60.0 + seconds / 3600.0

            if direction in ['S', 'W']:
                decimal = -decimal

            return decimal

        except Exception as e:
            logger.debug(f"Error parsing coordinate {coord_str}: {e}")
            return None

    def get_waypoint(self, waypoint_name: str) -> Optional[Waypoint]:
        """
        Get waypoint by name

        Args:
            waypoint_name: Waypoint identifier (e.g., "BAYLR", "HOMRR")

        Returns:
            Waypoint object with coordinates, or None if not found
        """
        self._ensure_loaded()
        return self.waypoints.get(waypoint_name.upper())

    def get_coordinates(self, waypoint_name: str) -> Optional[Tuple[float, float]]:
        """
        Get waypoint coordinates

        Args:
            waypoint_name: Waypoint identifier

        Returns:
            Tuple of (latitude, longitude) or None if not found
        """
        waypoint = self.get_waypoint(waypoint_name)
        if waypoint:
            return (waypoint.latitude, waypoint.longitude)
        return None

    def has_waypoint(self, waypoint_name: str) -> bool:
        """
        Check if waypoint exists in database

        Args:
            waypoint_name: Waypoint identifier

        Returns:
            True if waypoint exists, False otherwise
        """
        self._ensure_loaded()
        return waypoint_name.upper() in self.waypoints

    def get_all_waypoints(self) -> Dict[str, Waypoint]:
        """
        Get all waypoints in database

        Returns:
            Dictionary mapping waypoint names to Waypoint objects
        """
        self._ensure_loaded()
        return self.waypoints.copy()


# Global singleton instance
_global_waypoint_db = None


def get_waypoint_database(cifp_path: str = None) -> WaypointDatabase:
    """
    Get global waypoint database instance (singleton pattern)

    Args:
        cifp_path: Optional path to CIFP file

    Returns:
        WaypointDatabase instance
    """
    global _global_waypoint_db

    if _global_waypoint_db is None:
        _global_waypoint_db = WaypointDatabase(cifp_path)

    return _global_waypoint_db
