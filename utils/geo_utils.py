"""
Geographic utilities for coordinate calculations
"""
import math
from typing import List, Optional, Tuple


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


def cumulative_distances(coords: List[Tuple[float, float]]) -> List[float]:
    """Cumulative great-circle NM from coords[0] to each subsequent point.
    Result[0] is always 0.0; result[i] = result[i-1] + leg_i distance."""
    if not coords:
        return []
    out = [0.0]
    for i in range(1, len(coords)):
        lat1, lon1 = coords[i - 1]
        lat2, lon2 = coords[i]
        out.append(out[-1] + calculate_distance_nm(lat1, lon1, lat2, lon2))
    return out


def interpolate_along_path(
    coords: List[Tuple[float, float]], target_distance_nm: float
) -> Optional[Tuple[float, float, int]]:
    """Return (lat, lon, bearing_to_next_vertex) at ``target_distance_nm``
    along the polyline. Returns None if the path is shorter than the target
    or if inputs are invalid. Clamps negative targets to the start.
    """
    if len(coords) < 2 or target_distance_nm < 0:
        return None
    cum = cumulative_distances(coords)
    total = cum[-1]
    if target_distance_nm > total:
        return None
    # Find the segment where cum[i] <= target <= cum[i+1].
    for i in range(len(cum) - 1):
        if cum[i] <= target_distance_nm <= cum[i + 1]:
            seg_start_lat, seg_start_lon = coords[i]
            seg_end_lat, seg_end_lon = coords[i + 1]
            bearing = calculate_bearing(
                seg_start_lat, seg_start_lon, seg_end_lat, seg_end_lon
            )
            remainder = target_distance_nm - cum[i]
            if remainder <= 0:
                return (seg_start_lat, seg_start_lon, bearing)
            lat, lon = calculate_destination(
                seg_start_lat, seg_start_lon, bearing, remainder
            )
            return (lat, lon, bearing)
    return None


def route_remaining_inside_artcc(
    coords: List[Tuple[float, float]],
    start_idx: int,
    artcc_id: str,
    boundaries,
    step_nm: float = 5.0,
) -> float:
    """Walk the polyline forward from ``coords[start_idx]`` and return the
    cumulative NM remaining inside ``artcc_id`` until the first sample falls
    outside the boundary (or the route ends).

    ``boundaries`` is an ARTCCBoundaries instance; we avoid importing it at
    module load to keep this file dependency-free.
    """
    if start_idx < 0 or start_idx >= len(coords) or len(coords) < 2:
        return 0.0
    # Build the remaining segment list, starting at coords[start_idx].
    remaining = coords[start_idx:]
    if len(remaining) < 2:
        return 0.0
    traveled = 0.0
    for i in range(len(remaining) - 1):
        lat1, lon1 = remaining[i]
        lat2, lon2 = remaining[i + 1]
        leg_nm = calculate_distance_nm(lat1, lon1, lat2, lon2)
        if leg_nm <= 0:
            continue
        leg_bearing = calculate_bearing(lat1, lon1, lat2, lon2)
        # Sample every step_nm along this leg. Skip the leg's start sample
        # (already counted) and include the end.
        stepped = step_nm
        while stepped < leg_nm:
            s_lat, s_lon = calculate_destination(lat1, lon1, leg_bearing, stepped)
            if not boundaries.is_point_in_artcc(s_lat, s_lon, artcc_id):
                return traveled + stepped
            stepped += step_nm
        # Check the leg endpoint.
        if not boundaries.is_point_in_artcc(lat2, lon2, artcc_id):
            # Boundary is somewhere between last sample and endpoint. Return
            # the traveled distance up through the last in-ARTCC sample.
            last_inside = stepped - step_nm
            if last_inside < 0:
                last_inside = 0.0
            return traveled + last_inside
        traveled += leg_nm
    return traveled


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
