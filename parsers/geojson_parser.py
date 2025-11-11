"""
Parser for airport GeoJSON files
"""
import json
import logging
from typing import List, Dict, Optional
from models.airport import ParkingSpot, Runway
from utils.airport_utils import get_airport_elevation
from utils.runway_utils import (
    identify_parallel_runways,
    identify_crossing_converging_runways,
    calculate_runway_spacing,
    get_parallel_separation_requirement
)

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
        self._parallel_runway_info: Optional[Dict] = None  # Cache for parallel runway data
        self._runway_groups: Optional[Dict] = None  # Cache for runway grouping
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

    def get_parallel_runway_info(self) -> Dict:
        """
        Get parallel runway relationships and separation requirements.

        Returns a dictionary mapping each runway end to its parallel runway information:
        {
            '7L': {
                'parallels': ['7R'],
                'spacing_nm': {'7R': 0.133},
                'required_sep_nm': {'7R': 1.0}
            },
            '7R': {
                'parallels': ['7L'],
                'spacing_nm': {'7L': 0.133},
                'required_sep_nm': {'7L': 1.0}
            }
        }

        Returns:
            Dict mapping runway ends to parallel runway data, or empty dict if no parallels
        """
        # Return cached data if available
        if self._parallel_runway_info is not None:
            return self._parallel_runway_info

        # Initialize empty dict
        parallel_info = {}

        # Need at least 2 runways for parallel operations
        if len(self.runways) < 2:
            logger.debug("Airport has fewer than 2 runways, no parallel operations possible")
            self._parallel_runway_info = parallel_info
            return parallel_info

        # Identify parallel runway relationships
        parallel_map = identify_parallel_runways(self.runways)

        if not parallel_map:
            logger.info("No parallel runways detected at this airport")
            self._parallel_runway_info = parallel_info
            return parallel_info

        # For each runway with parallels, calculate spacing and separation requirements
        for runway_end, parallel_ends in parallel_map.items():
            runway = self.get_runway_by_name(runway_end)

            # Calculate spacing to each parallel runway
            for parallel_end in parallel_ends:
                parallel_runway = self.get_runway_by_name(parallel_end)
                spacing_nm = calculate_runway_spacing(runway, parallel_runway, runway_end, parallel_end)
                required_sep = get_parallel_separation_requirement(spacing_nm)

                if required_sep is not None:
                    # Store information for this runway
                    if runway_end not in parallel_info:
                        parallel_info[runway_end] = {
                            'parallels': [],
                            'spacing_nm': {},
                            'required_sep_nm': {}
                        }

                    parallel_info[runway_end]['parallels'].append(parallel_end)
                    parallel_info[runway_end]['spacing_nm'][parallel_end] = spacing_nm
                    parallel_info[runway_end]['required_sep_nm'][parallel_end] = required_sep

                    logger.info(f"Parallel runway pair: {runway_end} || {parallel_end}, "
                               f"spacing={spacing_nm:.3f} NM ({spacing_nm * 6076:.0f} ft), "
                               f"required diagonal separation={required_sep:.1f} NM")
                else:
                    logger.debug(f"Runway pair {runway_end}-{parallel_end} spacing {spacing_nm:.3f} NM "
                               f"outside FAA parallel runway separation standards")

        # Cache the results
        self._parallel_runway_info = parallel_info
        return parallel_info

    def get_runway_groups(self) -> Dict[str, int]:
        """
        Group runways based on parallel and crossing/converging relationships.

        Uses depth-first search (DFS) to find connected components, which means:
        - Runways that are parallel are grouped together
        - Runways that cross/converge are grouped together
        - TRANSITIVE: If runway A is parallel to B, and B crosses C, then A, B, and C
          are ALL in the same group (shares distance counter)

        Example 1 - Parallel only:
            Runways 8, 7L, 7R (all parallel) → Group 0: {8, 7L, 7R}

        Example 2 - Parallel + Crossing:
            Runways 8, 7L, 7R (parallel) and 17 (crosses 8)
            → Group 0: {8, 7L, 7R, 17} (all share distance counter)

        Example 3 - Multiple groups:
            Runways 8, 7L, 7R (parallel) → Group 0
            Runways 26, 25R, 25L (parallel, different from above) → Group 1
            Runway 3 (independent) → Group 2

        Returns:
            Dict mapping runway end to group ID
        """
        # Return cached data if available
        if self._runway_groups is not None:
            return self._runway_groups

        # Get parallel and crossing/converging relationships
        parallel_map = identify_parallel_runways(self.runways)
        crossing_map = identify_crossing_converging_runways(self.runways)

        # Combine relationships into a single adjacency map
        # runway_end -> list of related runway ends
        adjacency = {}

        for runway_end in [end for runway in self.runways for end in runway.get_runway_ends()]:
            related = set()

            # Add parallel runways
            if runway_end in parallel_map:
                related.update(parallel_map[runway_end])

            # Add crossing/converging runways
            if runway_end in crossing_map:
                related.update(crossing_map[runway_end])

            adjacency[runway_end] = list(related)

        # Use Union-Find to group connected runways
        # This properly handles all transitive relationships and bidirectional connections
        parent = {}

        def find(x):
            """Find root of element x with path compression"""
            if x not in parent:
                parent[x] = x
            if parent[x] != x:
                parent[x] = find(parent[x])  # Path compression
            return parent[x]

        def union(x, y):
            """Union two elements into the same set"""
            root_x = find(x)
            root_y = find(y)
            if root_x != root_y:
                parent[root_x] = root_y

        # Initialize all runway ends
        for runway_end in adjacency.keys():
            find(runway_end)

        # Union all connected runways
        for runway_end, related_runways in adjacency.items():
            for related in related_runways:
                union(runway_end, related)

        # Convert Union-Find structure to group IDs
        root_to_group_id = {}
        group_id = 0
        groups = {}

        for runway_end in adjacency.keys():
            root = find(runway_end)
            if root not in root_to_group_id:
                root_to_group_id[root] = group_id
                group_id += 1
            groups[runway_end] = root_to_group_id[root]

        # Log the groups with relationship details
        group_members = {}
        group_relationships = {}

        for runway_end, gid in groups.items():
            if gid not in group_members:
                group_members[gid] = []
                group_relationships[gid] = {'parallel': set(), 'crossing': set()}
            group_members[gid].append(runway_end)

            # Track relationship types within group
            if runway_end in parallel_map:
                group_relationships[gid]['parallel'].update(parallel_map[runway_end])
            if runway_end in crossing_map:
                group_relationships[gid]['crossing'].update(crossing_map[runway_end])

        for gid, members in sorted(group_members.items()):
            relationships = []
            if group_relationships[gid]['parallel']:
                relationships.append("parallel")
            if group_relationships[gid]['crossing']:
                relationships.append("crossing")

            rel_str = "+".join(relationships) if relationships else "independent"
            logger.info(f"Runway group {gid} ({rel_str}): {', '.join(sorted(members))}")

        # Cache and return
        self._runway_groups = groups
        return groups
