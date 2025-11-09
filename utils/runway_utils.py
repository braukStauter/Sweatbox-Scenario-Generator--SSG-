"""
Runway utility functions for parallel runway operations and separation calculations.
"""
import logging
import math
from typing import List, Dict, Optional, Tuple
from models.airport import Runway
from utils.geo_utils import calculate_distance_nm, calculate_bearing

logger = logging.getLogger(__name__)


def identify_parallel_runways(runways: List[Runway]) -> Dict[str, List[str]]:
    """
    Identify parallel runway relationships by comparing headings.

    Args:
        runways: List of Runway objects from airport

    Returns:
        Dict mapping each runway end to list of its parallel runway ends
        Example: {'7L': ['7R'], '7R': ['7L'], '25L': ['25R'], '25R': ['25L']}
    """
    parallel_map = {}

    # Get all runway ends with their headings
    runway_ends = []
    for runway in runways:
        ends = runway.get_runway_ends()
        for end in ends:
            heading = runway.get_runway_heading(end)
            if heading is not None:
                runway_ends.append((end, heading, runway))

    logger.debug(f"Analyzing {len(runway_ends)} runway ends for parallel relationships")

    # Compare each pair of runway ends
    for i, (end1, heading1, runway1) in enumerate(runway_ends):
        parallels = []

        for j, (end2, heading2, runway2) in enumerate(runway_ends):
            if i >= j:  # Skip self and already compared pairs
                continue

            # Check if runways are from the same physical runway (reciprocals)
            if runway1 == runway2:
                continue

            # Calculate heading difference
            heading_diff = abs(heading1 - heading2)
            # Normalize to 0-180 range
            if heading_diff > 180:
                heading_diff = 360 - heading_diff

            # Parallel runways have similar headings (within 10°)
            # Exclude reciprocals (around 180°)
            if heading_diff <= 10:
                parallels.append(end2)
                logger.debug(f"Detected parallel: {end1} (hdg {heading1:.0f}°) || {end2} (hdg {heading2:.0f}°), diff={heading_diff:.1f}°")

        if parallels:
            parallel_map[end1] = parallels

    logger.info(f"Identified {len(parallel_map)} runway ends with parallel relationships")
    return parallel_map


def calculate_runway_spacing(runway1: Runway, runway2: Runway, end1: str, end2: str) -> float:
    """
    Calculate perpendicular spacing between two parallel runway centerlines.

    For parallel runways, the perpendicular distance between centerlines
    is approximately equal to the distance between their thresholds.

    Args:
        runway1: First runway object
        runway2: Second runway object
        end1: Runway end designator for runway1 (e.g., '7L')
        end2: Runway end designator for runway2 (e.g., '7R')

    Returns:
        Spacing between centerlines in nautical miles
    """
    threshold1 = runway1.get_threshold_position(end1)
    threshold2 = runway2.get_threshold_position(end2)

    if threshold1 is None or threshold2 is None:
        logger.warning(f"Could not get threshold positions for {end1} or {end2}")
        return 0.0

    # For parallel runways, distance between thresholds approximates centerline spacing
    spacing_nm = calculate_distance_nm(
        threshold1[0], threshold1[1],
        threshold2[0], threshold2[1]
    )

    logger.debug(f"Runway spacing {end1}-{end2}: {spacing_nm:.3f} NM ({spacing_nm * 6076:.0f} ft)")
    return spacing_nm


def get_parallel_separation_requirement(spacing_nm: float) -> Optional[float]:
    """
    Determine required diagonal separation based on runway centerline spacing.

    FAA parallel runway separation standards:
    - 2,500-3,600 ft (0.474-0.683 NM): 1 NM diagonal
    - 3,600-8,300 ft (0.683-1.576 NM): 1.5 NM diagonal
    - 8,300-9,000 ft (1.576-1.709 NM): 2 NM diagonal
    - Outside range: No diagonal separation requirement

    Args:
        spacing_nm: Runway centerline spacing in nautical miles

    Returns:
        Required diagonal separation in NM, or None if outside applicable range
    """
    # Convert boundaries from feet to nautical miles
    MIN_SPACING = 2500 / 6076.12  # 0.411 NM
    TIER1_MAX = 3600 / 6076.12    # 0.593 NM
    TIER2_MAX = 8300 / 6076.12    # 1.366 NM
    TIER3_MAX = 9000 / 6076.12    # 1.481 NM

    if spacing_nm < MIN_SPACING:
        logger.debug(f"Spacing {spacing_nm:.3f} NM below minimum {MIN_SPACING:.3f} NM, no diagonal separation")
        return None
    elif spacing_nm <= TIER1_MAX:
        logger.debug(f"Spacing {spacing_nm:.3f} NM in tier 1: require 1 NM diagonal separation")
        return 1.0
    elif spacing_nm <= TIER2_MAX:
        logger.debug(f"Spacing {spacing_nm:.3f} NM in tier 2: require 1.5 NM diagonal separation")
        return 1.5
    elif spacing_nm <= TIER3_MAX:
        logger.debug(f"Spacing {spacing_nm:.3f} NM in tier 3: require 2 NM diagonal separation")
        return 2.0
    else:
        logger.debug(f"Spacing {spacing_nm:.3f} NM exceeds tier 3 maximum, no diagonal separation")
        return None


def identify_crossing_converging_runways(runways: List[Runway], max_centerline_distance_nm: float = 15.0) -> Dict[str, List[str]]:
    """
    Identify crossing and converging runway relationships.

    Runways are related if:
    1. Their actual runway surfaces physically intersect (crossing runways), OR
    2. Their extended centerlines intersect within a reasonable distance (converging finals)

    This groups runways like 8/26 and 3/21 where extended final approach courses cross.

    Args:
        runways: List of Runway objects from airport
        max_centerline_distance_nm: Maximum distance to check for centerline intersection (default 15 NM)

    Returns:
        Dict mapping each runway end to list of crossing/converging runway ends
        Example: {'8': ['3', '21'], '26': ['3', '21'], '3': ['8', '26'], '21': ['8', '26']}
    """
    crossing_map = {}

    # Get all runway ends with their coordinates
    runway_ends = []
    for runway in runways:
        ends = runway.get_runway_ends()
        for end in ends:
            heading = runway.get_runway_heading(end)
            threshold = runway.get_threshold_position(end)
            if heading is not None and runway.coordinates and threshold:
                runway_ends.append((end, runway.coordinates, heading, threshold, runway))

    logger.debug(f"Analyzing {len(runway_ends)} runway ends for crossing/converging relationships")

    # Compare each pair of runway ends
    for i, (end1, coords1, heading1, threshold1, runway1) in enumerate(runway_ends):
        crossings = []

        for j, (end2, coords2, heading2, threshold2, runway2) in enumerate(runway_ends):
            if i >= j:  # Skip self and already compared pairs
                continue

            # Skip if same physical runway (reciprocals like 8/26, 17/35)
            if runway1 == runway2:
                logger.debug(f"Skipping {end1} and {end2} - same physical runway (reciprocals)")
                continue

            # Calculate heading difference
            heading_diff = abs(heading1 - heading2)
            if heading_diff > 180:
                heading_diff = 360 - heading_diff

            # Skip parallel runways (within 10°) - they're handled separately
            if heading_diff <= 10:
                continue

            # Check BOTH conditions:
            # 1. Physical crossing (runway surfaces intersect)
            # 2. Centerline crossing (extended finals cross within distance)

            physical_crossing = _check_actual_runway_crossing(coords1, coords2)
            centerline_crossing = _check_centerline_intersection(
                threshold1, heading1, threshold2, heading2, max_centerline_distance_nm
            )

            if physical_crossing or centerline_crossing:
                crossings.append(end2)
                if physical_crossing and centerline_crossing:
                    logger.debug(f"Detected crossing runways (physical + centerline): {end1} (hdg {heading1:.0f}°) X {end2} (hdg {heading2:.0f}°)")
                elif physical_crossing:
                    logger.debug(f"Detected crossing runways (physical): {end1} (hdg {heading1:.0f}°) X {end2} (hdg {heading2:.0f}°)")
                else:
                    logger.debug(f"Detected converging runways (centerline): {end1} (hdg {heading1:.0f}°) ~ {end2} (hdg {heading2:.0f}°)")

        if crossings:
            crossing_map[end1] = crossings

    logger.info(f"Identified {len(crossing_map)} runway ends with crossing/converging relationships")
    return crossing_map


def _check_actual_runway_crossing(coords1: List[List[float]], coords2: List[List[float]]) -> bool:
    """
    Check if two runway surfaces actually intersect.

    Uses line segment intersection to determine if the physical runway surfaces cross.

    Args:
        coords1: List of [lon, lat] coordinates for first runway (GeoJSON format)
        coords2: List of [lon, lat] coordinates for second runway (GeoJSON format)

    Returns:
        True if the runway line segments intersect (physical crossing)
    """
    if not coords1 or not coords2 or len(coords1) < 2 or len(coords2) < 2:
        return False

    # For simplicity, treat each runway as a line segment from first to last coordinate
    # (The coordinates define the runway centerline from one end to the other)

    # Get endpoints of each runway
    # coords format: [[lon1, lat1], [lon2, lat2], ...]
    runway1_start = coords1[0]   # [lon, lat]
    runway1_end = coords1[-1]
    runway2_start = coords2[0]
    runway2_end = coords2[-1]

    # Check if these two line segments intersect
    if _line_segments_intersect(
        runway1_start[1], runway1_start[0],  # lat1, lon1
        runway1_end[1], runway1_end[0],      # lat2, lon2
        runway2_start[1], runway2_start[0],  # lat3, lon3
        runway2_end[1], runway2_end[0]       # lat4, lon4
    ):
        logger.debug(f"Runway surfaces intersect (actual crossing detected)")
        return True

    return False


def _line_segments_intersect(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    lat3: float, lon3: float,
    lat4: float, lon4: float
) -> bool:
    """
    Check if two line segments intersect.

    Segment 1: (lat1, lon1) to (lat2, lon2)
    Segment 2: (lat3, lon3) to (lat4, lon4)

    Returns:
        True if segments intersect
    """
    # Using the orientation method for line segment intersection

    def orientation(p1_lat, p1_lon, p2_lat, p2_lon, p3_lat, p3_lon):
        """Find orientation of ordered triplet (p1, p2, p3).
        Returns:
        0: Colinear
        1: Clockwise
        2: Counterclockwise
        """
        val = (p2_lon - p1_lon) * (p3_lat - p2_lat) - (p2_lat - p1_lat) * (p3_lon - p2_lon)
        if abs(val) < 1e-10:
            return 0
        return 1 if val > 0 else 2

    def on_segment(p1_lat, p1_lon, p2_lat, p2_lon, p3_lat, p3_lon):
        """Check if point p2 lies on segment p1-p3"""
        if (min(p1_lat, p3_lat) <= p2_lat <= max(p1_lat, p3_lat) and
            min(p1_lon, p3_lon) <= p2_lon <= max(p1_lon, p3_lon)):
            return True
        return False

    o1 = orientation(lat1, lon1, lat2, lon2, lat3, lon3)
    o2 = orientation(lat1, lon1, lat2, lon2, lat4, lon4)
    o3 = orientation(lat3, lon3, lat4, lon4, lat1, lon1)
    o4 = orientation(lat3, lon3, lat4, lon4, lat2, lon2)

    # General case: segments intersect if orientations differ
    if o1 != o2 and o3 != o4:
        return True

    # Special cases: colinear points
    if o1 == 0 and on_segment(lat1, lon1, lat3, lon3, lat2, lon2):
        return True
    if o2 == 0 and on_segment(lat1, lon1, lat4, lon4, lat2, lon2):
        return True
    if o3 == 0 and on_segment(lat3, lon3, lat1, lon1, lat4, lon4):
        return True
    if o4 == 0 and on_segment(lat3, lon3, lat2, lon2, lat4, lon4):
        return True

    return False


def _check_centerline_intersection(
    threshold1: Tuple[float, float],
    heading1: float,
    threshold2: Tuple[float, float],
    heading2: float,
    max_distance_nm: float
) -> bool:
    """
    Check if two runway centerlines intersect within a given distance.

    Uses parametric line intersection to find where extended centerlines meet.
    This detects converging runways (centerlines meet ahead of thresholds).

    Args:
        threshold1: (lat, lon) of first runway threshold
        heading1: Heading of first runway in degrees
        threshold2: (lat, lon) of second runway threshold
        heading2: Heading of second runway in degrees
        max_distance_nm: Maximum distance from either threshold to check

    Returns:
        True if centerlines intersect within max_distance_nm of either threshold
    """
    import math

    lat1, lon1 = threshold1
    lat2, lon2 = threshold2

    # Convert headings to radians
    h1_rad = math.radians(heading1)
    h2_rad = math.radians(heading2)

    # Direction vectors (using small angle approximation for local coordinates)
    # dx/dy in degrees (approximate, but sufficient for intersection detection)
    dx1 = math.sin(h1_rad)
    dy1 = math.cos(h1_rad)
    dx2 = math.sin(h2_rad)
    dy2 = math.cos(h2_rad)

    # Parametric lines: P1 + t1 * D1 and P2 + t2 * D2
    # Solve for intersection: lat1 + t1*dy1 = lat2 + t2*dy2
    #                        lon1 + t1*dx1 = lon2 + t2*dx2

    # Using determinant method
    det = dx1 * dy2 - dx2 * dy1

    # If determinant is zero, lines are parallel (shouldn't happen after parallel check)
    if abs(det) < 1e-10:
        return False

    # Solve for t1 and t2
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    t1 = (dlon * dy2 - dlat * dx2) / det
    t2 = (dlon * dy1 - dlat * dx1) / det

    # Convert t1 and t2 to distances (approximate)
    # Each unit of t is roughly 1 degree, convert to NM
    # 1 degree latitude ≈ 60 NM
    dist1_nm = abs(t1) * 60
    dist2_nm = abs(t2) * 60

    # Check if intersection is within max_distance_nm from either threshold
    # and in the forward direction (t > 0) - this detects converging runways
    if t1 > 0 and t2 > 0 and dist1_nm <= max_distance_nm and dist2_nm <= max_distance_nm:
        logger.debug(f"Centerline intersection at {dist1_nm:.1f} NM from threshold 1, {dist2_nm:.1f} NM from threshold 2")
        return True

    return False


def calculate_diagonal_separation(
    runway1_distance: float,
    runway2_distance: float,
    centerline_spacing: float
) -> float:
    """
    Calculate diagonal separation between two aircraft on parallel final approaches.

    Uses Pythagorean theorem to calculate the diagonal distance between aircraft
    at different distances from their respective thresholds.

    Args:
        runway1_distance: Distance of aircraft 1 from its threshold (NM)
        runway2_distance: Distance of aircraft 2 from its threshold (NM)
        centerline_spacing: Perpendicular spacing between runway centerlines (NM)

    Returns:
        Diagonal separation in nautical miles
    """
    # Along-track separation (difference in distances from threshold)
    along_track = abs(runway1_distance - runway2_distance)

    # Perpendicular separation (runway centerline spacing)
    perpendicular = centerline_spacing

    # Diagonal separation (hypotenuse)
    diagonal = math.sqrt(along_track**2 + perpendicular**2)

    return diagonal
