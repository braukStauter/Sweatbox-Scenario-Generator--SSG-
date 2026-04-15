"""
ARTCC Boundary Utilities for Enroute Scenarios
Provides functions for working with ARTCC geographic boundaries
"""
import json
import logging
import sys
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from utils.artcc_lookup import point_in_polygon

logger = logging.getLogger(__name__)


def _resolve_boundaries_path() -> Path:
    """Locate artcc_boundaries.geojson across install, frozen, and dev layouts.

    Lookup order:
      1. <install>/resources/artcc_boundaries.geojson  (user-editable)
      2. _MEIPASS/utils/artcc_boundaries.geojson       (PyInstaller baked-in)
      3. <repo>/utils/artcc_boundaries.geojson         (dev)
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir.parent / 'artcc_boundaries.geojson')
    candidates.append(Path(__file__).resolve().parent / 'artcc_boundaries.geojson')
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


class ARTCCBoundaries:
    """ARTCC boundary data manager"""

    def __init__(self):
        """Initialize ARTCC boundary manager"""
        self.boundaries_data: Optional[Dict] = None
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy load ARTCC boundary data on first access"""
        if not self._loaded:
            self._load_boundaries()
            self._loaded = True

    def _load_boundaries(self):
        """Load ARTCC boundaries from GeoJSON file"""
        try:
            boundaries_path = _resolve_boundaries_path()
            with open(boundaries_path, 'r') as f:
                self.boundaries_data = json.load(f)

            logger.info(f"Loaded {len(self.boundaries_data.get('features', []))} ARTCC boundaries")

        except Exception as e:
            logger.error(f"Error loading ARTCC boundaries: {e}")
            self.boundaries_data = {"type": "FeatureCollection", "features": []}

    def get_artcc_polygon(self, artcc_id: str) -> Optional[List[Tuple[float, float]]]:
        """
        Get polygon coordinates for a specific ARTCC

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB", "ZLA")

        Returns:
            List of (longitude, latitude) tuples, or None if not found
        """
        self._ensure_loaded()

        for feature in self.boundaries_data.get('features', []):
            if feature.get('properties', {}).get('id') == artcc_id.upper():
                geometry = feature.get('geometry', {})

                if geometry.get('type') == 'Polygon':
                    # Return first ring (exterior boundary)
                    coords = geometry.get('coordinates', [[]])[0]
                    return [(lon, lat) for lon, lat in coords]

                elif geometry.get('type') == 'MultiPolygon':
                    # Return first polygon's exterior boundary
                    coords = geometry.get('coordinates', [[[]]]) [0][0]
                    return [(lon, lat) for lon, lat in coords]

        logger.warning(f"ARTCC {artcc_id} not found in boundaries data")
        return None

    def is_point_in_artcc(self, lat: float, lon: float, artcc_id: str) -> bool:
        """
        Check if a point is within a specific ARTCC boundary

        Args:
            lat: Latitude
            lon: Longitude
            artcc_id: ARTCC identifier (e.g., "ZAB")

        Returns:
            True if point is within ARTCC, False otherwise
        """
        self._ensure_loaded()

        for feature in self.boundaries_data.get('features', []):
            if feature.get('properties', {}).get('id') == artcc_id.upper():
                geometry = feature.get('geometry', {})

                if geometry.get('type') == 'Polygon':
                    coords_ring = geometry.get('coordinates', [[]])[0]
                    return point_in_polygon(lat, lon, coords_ring)

                elif geometry.get('type') == 'MultiPolygon':
                    for polygon in geometry.get('coordinates', []):
                        coords_ring = polygon[0]
                        if point_in_polygon(lat, lon, coords_ring):
                            return True
                    return False

        logger.warning(f"ARTCC {artcc_id} not found for point check")
        return False

    def get_all_artcc_ids(self) -> List[str]:
        """
        Get list of all available ARTCC identifiers

        Returns:
            List of ARTCC IDs (e.g., ["ZAB", "ZLA", ...])
        """
        self._ensure_loaded()

        artcc_ids = []
        for feature in self.boundaries_data.get('features', []):
            artcc_id = feature.get('properties', {}).get('id')
            if artcc_id:
                artcc_ids.append(artcc_id)

        return sorted(artcc_ids)

    def get_artcc_bbox(self, artcc_id: str) -> Optional[Tuple[float, float, float, float]]:
        """
        Get bounding box for a specific ARTCC

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB")

        Returns:
            Tuple of (min_lon, min_lat, max_lon, max_lat) or None if not found
        """
        self._ensure_loaded()

        for feature in self.boundaries_data.get('features', []):
            if feature.get('properties', {}).get('id') == artcc_id.upper():
                bbox = feature.get('bbox')
                if bbox and len(bbox) == 4:
                    # GeoJSON bbox format: [min_lon, min_lat, max_lon, max_lat]
                    return tuple(bbox)

                # If no bbox, calculate from coordinates
                geometry = feature.get('geometry', {})
                coords = []

                if geometry.get('type') == 'Polygon':
                    coords = geometry.get('coordinates', [[]])[0]
                elif geometry.get('type') == 'MultiPolygon':
                    for polygon in geometry.get('coordinates', []):
                        coords.extend(polygon[0])

                if coords:
                    lons = [c[0] for c in coords]
                    lats = [c[1] for c in coords]
                    return (min(lons), min(lats), max(lons), max(lats))

        logger.warning(f"ARTCC {artcc_id} not found for bbox calculation")
        return None

    def get_artcc_center(self, artcc_id: str) -> Optional[Tuple[float, float]]:
        """
        Get approximate center point of ARTCC

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB")

        Returns:
            Tuple of (latitude, longitude) or None if not found
        """
        bbox = self.get_artcc_bbox(artcc_id)
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            center_lat = (min_lat + max_lat) / 2
            center_lon = (min_lon + max_lon) / 2
            return (center_lat, center_lon)

        return None


class CustomBoundary:
    """Drop-in replacement for :class:`ARTCCBoundaries` that answers with a
    user-defined polygon instead of the facility's ARTCC polygon.

    The public surface mirrors the methods the enroute scenario actually
    calls — ``is_point_in_artcc``, ``get_artcc_polygon``, ``get_artcc_bbox``
    — so swapping one for the other requires no call-site changes. The
    ``artcc_id`` parameter is ignored on every method; the polygon is
    single-feature and scoped to this instance.

    Expects ``polygon_coords`` as a list of ``(lon, lat)`` tuples in the
    order the user entered the waypoints. The last vertex is auto-closed
    to the first if the caller didn't already close the ring.
    """

    def __init__(self, polygon_coords: List[Tuple[float, float]]):
        self._polygon: List[Tuple[float, float]] = [
            (float(lon), float(lat)) for lon, lat in polygon_coords
        ]
        if (
            len(self._polygon) >= 3
            and self._polygon[0] != self._polygon[-1]
        ):
            self._polygon.append(self._polygon[0])

    def is_point_in_artcc(self, lat: float, lon: float,
                            artcc_id: Optional[str] = None) -> bool:
        if len(self._polygon) < 4:
            # Degenerate polygon (needs at least 3 unique vertices + close).
            return False
        return point_in_polygon(lat, lon, self._polygon)

    def get_artcc_polygon(
        self, artcc_id: Optional[str] = None,
    ) -> Optional[List[Tuple[float, float]]]:
        return list(self._polygon) if self._polygon else None

    def get_artcc_bbox(
        self, artcc_id: Optional[str] = None,
    ) -> Optional[Tuple[float, float, float, float]]:
        if not self._polygon:
            return None
        lons = [p[0] for p in self._polygon]
        lats = [p[1] for p in self._polygon]
        return (min(lons), min(lats), max(lons), max(lats))

    def get_artcc_center(
        self, artcc_id: Optional[str] = None,
    ) -> Optional[Tuple[float, float]]:
        bbox = self.get_artcc_bbox()
        if not bbox:
            return None
        min_lon, min_lat, max_lon, max_lat = bbox
        return ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)


# Global singleton instance
_global_artcc_boundaries = None


def get_artcc_boundaries() -> ARTCCBoundaries:
    """
    Get global ARTCC boundaries instance (singleton pattern)

    Returns:
        ARTCCBoundaries instance
    """
    global _global_artcc_boundaries

    if _global_artcc_boundaries is None:
        _global_artcc_boundaries = ARTCCBoundaries()

    return _global_artcc_boundaries
