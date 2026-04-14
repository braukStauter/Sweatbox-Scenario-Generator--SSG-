"""
Waypoint Database for global waypoint coordinate lookups
Used for enroute scenario positioning and route parsing
"""
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple
from models.airport import Waypoint

logger = logging.getLogger(__name__)


def _default_cifp_path() -> str:
    """Resolve the bundled FAACIFP18 path regardless of cwd.

    Mirrors ssg_bridge.resource_path lookup order:
      1. User-editable <install>/resources/airport_data/ (next to frozen exe).
      2. PyInstaller _MEIPASS/airport_data/ (baked-in fallback).
      3. Repo-root airport_data/ in dev.
      4. Legacy cifp_data/ as last resort.
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        # <install>/resources/bridge/ssg_bridge.exe -> <install>/resources/
        candidates.append(exe_dir.parent / 'airport_data' / 'FAACIFP18')
        mei = getattr(sys, '_MEIPASS', None)
        if mei:
            candidates.append(Path(mei) / 'airport_data' / 'FAACIFP18')
    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root / 'airport_data' / 'FAACIFP18')
    candidates.append(repo_root / 'cifp_data' / 'FAACIFP18')
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[-1])


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

        if cifp_path is None:
            cifp_path = _default_cifp_path()

        self.cifp_path = cifp_path

    def _ensure_loaded(self):
        """Lazy load waypoint data on first access"""
        if not self._loaded:
            self._load_waypoints()
            self._loaded = True

    def _load_waypoints(self):
        """Load all waypoint definitions from CIFP file.

        ARINC 424 record layout (relevant sections):
          * ``SUSAE A`` — enroute fixes (5-letter names like BAYLR, HOMRR).
          * ``SUSAD`` subsection ' ' — VHF navaids (VOR, VORTAC, VOR/DME,
            TACAN, DME-only). 3-letter idents like GUP, JCT, ABQ.
          * ``SUSAD`` subsection 'B' — NDBs.
          * ``SUSAP`` byte-12 'C' — airport terminal waypoints.

        We collect all of these into a single name-keyed dict. Enroute fixes
        are loaded FIRST so that if a navaid shares an identifier with a
        5-letter fix (rare but possible), the fix wins — the navaid can
        still be referenced by its exact 3/4-letter ident without overwrite.
        """
        if not os.path.exists(self.cifp_path):
            logger.warning(f"CIFP file not found: {self.cifp_path}")
            return

        try:
            # Two-pass load: enroute + terminal waypoints first, then navaids.
            # Keeps the explicit-fix records authoritative when a collision
            # would occur; navaids only populate idents that aren't already
            # covered by a true waypoint record.
            navaid_lines = []
            with open(self.cifp_path, 'r', encoding='latin-1') as f:
                for line in f:
                    if len(line) < 50:
                        continue

                    record_type = line[0:5]
                    if record_type == 'SUSAE':
                        subsection = line[5] if len(line) > 5 else ''
                        if subsection == 'A':
                            self._parse_waypoint_definition(line)
                    elif record_type == 'SUSAP':
                        # Terminal-area waypoints: byte 12 == 'C'.
                        if len(line) > 12 and line[12] == 'C':
                            self._parse_waypoint_definition(line)
                    elif record_type == 'SUSAD':
                        # Deferred: parse after enroute/terminal fixes so a
                        # rare ident collision resolves to the fix record.
                        navaid_lines.append(line)

            for line in navaid_lines:
                subsection = line[5] if len(line) > 5 else ''
                # ' ' = VHF navaid (VOR/VORTAC/TACAN/DME).
                # 'B' = NDB.
                if subsection in (' ', 'B'):
                    self._parse_navaid_definition(line)

            logger.info(f"Loaded {len(self.waypoints)} waypoints from CIFP")

        except Exception as e:
            logger.error(f"Error loading waypoint database: {e}")

    def _parse_waypoint_definition(self, line: str):
        """Parse an enroute/terminal waypoint record from CIFP."""
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
                # Store only by the exact ident. The previous loader aliased
                # the last 3 chars of every 5-letter fix (meant for
                # international ICAO-prefixed names like "ET*"), but on
                # FAACIFP18 (USA) this created massive false matches — e.g.
                # "COGUP" in Arkansas being aliased as "GUP" and masking the
                # real Gallup VOR. Route resolution relied on that alias to
                # "find" navaids the loader never actually parsed, which is
                # how unrelated 5-letter fixes in other states leaked into
                # filed-route geometry.
                self.waypoints[waypoint_name] = waypoint

        except Exception as e:
            logger.debug(f"Error parsing waypoint definition: {e}")

    def _parse_navaid_definition(self, line: str):
        """Parse a VHF navaid (VOR/VORTAC/TACAN/DME) or NDB record from CIFP.

        Format (ARINC 424 section D): ident at bytes 13-17 (3- or 4-letter),
        position latitude at 32-41, longitude at 41-51. Only loads idents
        not already covered by an enroute/terminal waypoint record so the
        explicit fix form always wins on the rare name collision."""
        try:
            ident = line[13:17].strip()
            if not ident:
                return
            if ident in self.waypoints:
                # Already loaded as a fix; keep the fix record authoritative.
                return
            lat_str = line[32:41].strip()
            lon_str = line[41:51].strip()
            latitude = self._parse_coordinate(lat_str, is_latitude=True)
            longitude = self._parse_coordinate(lon_str, is_latitude=False)
            if latitude is None or longitude is None:
                return
            self.waypoints[ident] = Waypoint(
                name=ident,
                latitude=latitude,
                longitude=longitude,
            )
        except Exception as e:
            logger.debug(f"Error parsing navaid definition: {e}")

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
