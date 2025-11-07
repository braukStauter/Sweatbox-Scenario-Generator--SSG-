"""
Flight data filtering utilities for validating and categorizing API flight data
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
import re

logger = logging.getLogger(__name__)


def is_valid_flight(flight: Dict[str, Any]) -> bool:
    """
    Check if a flight has all required data

    Args:
        flight: Flight dictionary from API

    Returns:
        True if flight is valid, False otherwise
    """
    # Must have aircraft identification
    if not flight.get('aircraftIdentification'):
        logger.debug(f"Flight missing aircraftIdentification: {flight.get('gufi')}")
        return False

    # Must have complete route
    route = flight.get('route', '')
    if not route or route.strip() == '':
        logger.debug(f"Flight {flight.get('aircraftIdentification')} missing route")
        return False

    # Exclude ACTIVE flights
    if flight.get('flightStatus') == 'ACTIVE':
        logger.debug(f"Flight {flight.get('aircraftIdentification')} has ACTIVE status")
        return False

    # Must have aircraft type
    if not flight.get('aircraftType'):
        logger.debug(f"Flight {flight.get('aircraftIdentification')} missing aircraftType")
        return False

    return True


def filter_valid_flights(flights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter a list of flights to only include those with complete data

    Args:
        flights: List of flight dictionaries from API

    Returns:
        Filtered list of valid flights
    """
    valid_flights = [f for f in flights if is_valid_flight(f)]

    if len(valid_flights) < len(flights):
        logger.info(f"Filtered {len(flights) - len(valid_flights)} invalid flights, {len(valid_flights)} remain")

    return valid_flights


def is_ga_aircraft(flight: Dict[str, Any]) -> bool:
    """
    Check if a flight is a GA (General Aviation) aircraft based on callsign format

    Args:
        flight: Flight dictionary from API

    Returns:
        True if GA aircraft (N-number format), False if airline
    """
    callsign = flight.get('aircraftIdentification', '')

    # GA aircraft have N-number format (e.g., N12345, N123AB)
    # Pattern: starts with 'N' followed by 1-5 alphanumeric characters
    ga_pattern = re.compile(r'^N[A-Z0-9]{1,5}$', re.IGNORECASE)

    return bool(ga_pattern.match(callsign))


def categorize_flights(flights: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Separate flights into GA and airline categories

    Args:
        flights: List of flight dictionaries from API

    Returns:
        Tuple of (ga_flights, airline_flights)
    """
    ga_flights = []
    airline_flights = []

    for flight in flights:
        if is_ga_aircraft(flight):
            ga_flights.append(flight)
        else:
            airline_flights.append(flight)

    logger.debug(f"Categorized {len(flights)} flights: {len(ga_flights)} GA, {len(airline_flights)} airline")

    return ga_flights, airline_flights


def extract_sid_from_route(route: str) -> Optional[str]:
    """
    Extract SID name from a route string

    Args:
        route: Route string (e.g., "KABQ.MNZNO3.TXO..TURKI.JFRYE5.KDAL/0433")

    Returns:
        SID name or None if not found
    """
    # Route format: AIRPORT.SID.WAYPOINT or AIRPORT..WAYPOINT (no SID)
    parts = route.split('.')

    if len(parts) < 2:
        return None

    # SID is typically the second element after the airport
    # Skip if it's empty (indicating DCT route like "KABQ..CNX")
    potential_sid = parts[1]

    if not potential_sid or potential_sid == '':
        return None

    # SID names are typically alphanumeric with numbers at the end (e.g., MNZNO3, JFRYE5)
    # Exclude waypoint-looking names (all uppercase, 5 chars, no numbers)
    sid_pattern = re.compile(r'^[A-Z0-9]{4,7}\d$')

    if sid_pattern.match(potential_sid):
        return potential_sid

    return None


def extract_star_from_route(route: str) -> Optional[str]:
    """
    Extract STAR name from a route string

    Args:
        route: Route string (e.g., "KABQ.MNZNO3.TXO..TURKI.JFRYE5.KDAL/0433")

    Returns:
        STAR name or None if not found
    """
    # STAR is typically near the end of the route, before the arrival airport
    # Look for pattern similar to SID
    parts = route.split('.')

    if len(parts) < 3:
        return None

    # Check last few parts before the airport (which may include /time)
    for i in range(len(parts) - 2, max(0, len(parts) - 5), -1):
        part = parts[i].split('/')[0]  # Remove time suffix if present

        # STAR names are similar to SID names
        star_pattern = re.compile(r'^[A-Z0-9]{4,7}\d$')

        if star_pattern.match(part):
            return part

    return None


def route_contains_waypoint(route: str, waypoint: str) -> bool:
    """
    Check if a route contains a specific waypoint

    Args:
        route: Route string
        waypoint: Waypoint name to search for

    Returns:
        True if waypoint is in route, False otherwise
    """
    # Normalize route and waypoint
    route_upper = route.upper()
    waypoint_upper = waypoint.upper()

    # Split by common route delimiters
    route_elements = re.split(r'[.\s/]', route_upper)

    return waypoint_upper in route_elements


def filter_departures_by_sid(
    flights: List[Dict[str, Any]],
    available_sids: List[str],
    runways: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Filter departure flights by valid SIDs for active runways

    Args:
        flights: List of departure flight dictionaries
        available_sids: List of valid SID names for the airport
        runways: Optional list of active runway names for additional filtering

    Returns:
        Filtered list of flights with valid SIDs
    """
    if not available_sids:
        # If no SIDs available, allow all flights (DCT routes)
        logger.debug("No SIDs specified, allowing all departures")
        return flights

    valid_flights = []

    for flight in flights:
        route = flight.get('route', '')
        sid = extract_sid_from_route(route)

        # Allow flights without SID (DCT routes) or with valid SID
        if sid is None or sid in available_sids:
            valid_flights.append(flight)
        else:
            logger.debug(f"Flight {flight.get('aircraftIdentification')} SID '{sid}' not in available SIDs")

    logger.info(f"Filtered departures by SID: {len(valid_flights)}/{len(flights)} valid")

    return valid_flights


def filter_arrivals_by_waypoint(
    flights: List[Dict[str, Any]],
    waypoint: str,
    star_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Filter arrival flights by route containing a specific waypoint

    Args:
        flights: List of arrival flight dictionaries
        waypoint: Waypoint name that must be in the route
        star_name: Optional STAR name for additional filtering

    Returns:
        Filtered list of flights with routes containing the waypoint
    """
    valid_flights = []

    for flight in flights:
        route = flight.get('route', '')

        # Check if route contains the waypoint
        if not route_contains_waypoint(route, waypoint):
            continue

        # If STAR specified, check for it too
        if star_name:
            route_star = extract_star_from_route(route)
            if route_star and route_star != star_name:
                logger.debug(f"Flight {flight.get('aircraftIdentification')} has STAR '{route_star}', expected '{star_name}'")
                continue

        valid_flights.append(flight)

    logger.info(f"Filtered arrivals by waypoint '{waypoint}': {len(valid_flights)}/{len(flights)} valid")

    return valid_flights


def filter_arrivals_by_stars(
    flights: List[Dict[str, Any]],
    star_transitions: List[Tuple[str, str]],
    allow_waypoint_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Filter arrival flights by multiple STAR transitions or waypoints

    Args:
        flights: List of arrival flight dictionaries
        star_transitions: List of (waypoint, STAR) tuples to filter by
                         e.g., [('EAGUL', 'EAGUL6'), ('HOTTT', 'EAGUL6')]
                         If STAR is None, filters by waypoint only
        allow_waypoint_only: If True, allows filtering by waypoint when STAR not specified

    Returns:
        Filtered list of flights matching any of the specified STARs or waypoints
    """
    if not star_transitions:
        return flights

    # Separate transitions into those with STARs and waypoint-only
    star_names = set()
    waypoint_only = set()

    for waypoint, star_name in star_transitions:
        if star_name:
            star_names.add(star_name)
        elif allow_waypoint_only:
            waypoint_only.add(waypoint)

    valid_flights = []

    for flight in flights:
        route = flight.get('route', '')
        route_star = extract_star_from_route(route)

        matched = False

        # Check if flight's STAR matches any of the configured STARs
        if star_names and route_star and route_star in star_names:
            matched = True
            logger.debug(f"Flight {flight.get('aircraftIdentification')} matched by STAR: {route_star}")

        # Check if route contains any of the waypoint-only filters
        elif waypoint_only:
            for waypoint in waypoint_only:
                if route_contains_waypoint(route, waypoint):
                    # Verify it has a STAR (not a DCT route)
                    if route_star:
                        matched = True
                        logger.debug(
                            f"Flight {flight.get('aircraftIdentification')} matched by waypoint '{waypoint}' "
                            f"with STAR '{route_star}'"
                        )
                        break

        if matched:
            valid_flights.append(flight)
        else:
            logger.debug(
                f"Flight {flight.get('aircraftIdentification')} with STAR '{route_star}' "
                f"did not match filters"
            )

    filter_desc = []
    if star_names:
        filter_desc.append(f"STARs: {star_names}")
    if waypoint_only:
        filter_desc.append(f"Waypoints: {waypoint_only}")

    logger.info(f"Filtered arrivals by {', '.join(filter_desc)}: {len(valid_flights)}/{len(flights)} valid")

    return valid_flights


def filter_by_parking_airline(
    flights: List[Dict[str, Any]],
    preferred_airlines: List[str]
) -> List[Dict[str, Any]]:
    """
    Prioritize flights from specific airlines for parking spot assignment

    Args:
        flights: List of flight dictionaries
        preferred_airlines: List of preferred airline ICAO codes

    Returns:
        List with preferred airlines first, then others
    """
    if not preferred_airlines:
        return flights

    # Separate preferred and other flights
    preferred = []
    others = []

    for flight in flights:
        operator = flight.get('operator', '')

        if operator in preferred_airlines:
            preferred.append(flight)
        else:
            others.append(flight)

    # Return preferred first, then others
    result = preferred + others

    logger.debug(f"Prioritized {len(preferred)} flights from preferred airlines {preferred_airlines}")

    return result


def get_airline_from_callsign(callsign: str) -> Optional[str]:
    """
    Extract airline ICAO code from a callsign

    Args:
        callsign: Full callsign (e.g., "SWA1156", "N642PC")

    Returns:
        Airline ICAO code or None if GA aircraft
    """
    if is_ga_aircraft({'aircraftIdentification': callsign}):
        return None

    # Airline callsigns typically have 3-letter prefix followed by numbers
    # Extract the alphabetic prefix
    match = re.match(r'^([A-Z]{2,3})', callsign.upper())

    if match:
        return match.group(1)

    return None


def clean_route_string(route: str) -> str:
    """
    Clean a route string from API format to vNAS format

    Converts:
        KDFW.HRPER3.HULZE..HNKER..TCC..ABQ.J78.ZUN.EAGUL6.KPHX/0220
    To:
        HRPER3 HULZE HNKER TCC ABQ J78 ZUN EAGUL6

    Rules:
    - Remove departure airport (4-letter ICAO at start)
    - Remove arrival airport (4-letter ICAO at end, before /)
    - Remove time suffix (e.g., /0220)
    - Replace dots with spaces
    - Remove double-dots (direct routes)
    - Trim extra whitespace

    Args:
        route: Raw route string from API

    Returns:
        Cleaned route string suitable for vNAS
    """
    if not route or not route.strip():
        return ''

    # Remove time suffix (e.g., /0220)
    route = re.sub(r'/\d{4}$', '', route)

    # Split by dots
    parts = route.split('.')

    # Filter out empty parts (from double dots)
    parts = [p for p in parts if p.strip()]

    if not parts:
        return ''

    # Remove departure airport (first element if it's a 4-letter ICAO code starting with K, P, C, etc.)
    if parts and len(parts[0]) == 4 and parts[0][0] in 'KPCMTYNZWSVR':
        parts = parts[1:]

    # Remove arrival airport (last element if it's a 4-letter ICAO code)
    if parts and len(parts[-1]) == 4 and parts[-1][0] in 'KPCMTYNZWSVR':
        parts = parts[:-1]

    # Join with spaces and clean up
    cleaned = ' '.join(parts)

    # Remove any extra whitespace
    cleaned = ' '.join(cleaned.split())

    logger.debug(f"Cleaned route: '{route}' -> '{cleaned}'")

    return cleaned
