"""
Parser for FAA CIFP (Coded Instrument Flight Procedures) files
Based on ARINC 424 specification
"""
import logging
import re
from typing import List, Dict, Optional
from models.airport import Waypoint

logger = logging.getLogger(__name__)

# ARINC 424 Leg Type (Path Terminator) Lookup
LEG_TYPES = {
    'AF': 'Arc to a Fix',
    'CA': 'Course to an Altitude',
    'CD': 'Course to a DME Distance',
    'CF': 'Course to a Fix',
    'CI': 'Course to an Intercept',
    'CR': 'Course to a Radial',
    'DF': 'Direct to a Fix',
    'FA': 'Fix to an Altitude',
    'FC': 'Track from a Fix to a Course/Track',
    'FD': 'Fix to a DME Distance',
    'FM': 'Fix to a Manual Termination',
    'HA': 'Hold to an Altitude',
    'HF': 'Hold to a Fix',
    'HM': 'Hold to a Manual Termination',
    'IF': 'Initial Fix',
    'PI': 'Procedure Turn',
    'RF': 'Constant Radius Arc',
    'TF': 'Track to a Fix',
    'VA': 'Heading to an Altitude',
    'VD': 'Heading to a DME Distance',
    'VI': 'Heading to an Intercept',
    'VM': 'Heading to a Manual Termination',
    'VR': 'Heading to a Radial'
}

# Altitude Descriptor Meanings
ALTITUDE_DESCRIPTORS = {
    '@': 'At altitude',
    '+': 'At or above altitude',
    '-': 'At or below altitude',
    'B': 'Between altitudes',
    ' ': 'No altitude constraint'
}

# Turn Direction
TURN_DIRECTIONS = {
    'L': 'Left',
    'R': 'Right',
    'E': 'Either',
    ' ': 'Not specified'
}


class CIFPParser:
    """Parser for FAA CIFP files"""

    def __init__(self, cifp_path: str, airport_icao: str):
        """Initialize the parser"""
        self.cifp_path = cifp_path
        self.airport_icao = airport_icao
        self.waypoints: Dict[str, Waypoint] = {}
        self.arrivals: Dict[str, List[str]] = {}
        self.arrival_runways: Dict[str, List[str]] = {}  # Maps STAR name to runways it feeds
        # Store waypoint data per STAR to preserve procedure-specific constraints
        self.star_waypoints: Dict[str, Dict[str, Waypoint]] = {}  # {STAR_name: {waypoint_name: Waypoint}}
        self._load_data()

    def _parse_leg_type(self, line: str) -> Optional[str]:
        """Parse leg type (path terminator) from position 47-48"""
        try:
            if len(line) >= 48:
                leg_type = line[47:49].strip()
                if leg_type in LEG_TYPES:
                    return leg_type
        except Exception as e:
            logger.debug(f"Error parsing leg type: {e}")
        return None

    def _parse_sequence_number(self, line: str) -> Optional[int]:
        """Parse sequence number from position 26-29"""
        try:
            if len(line) >= 29:
                seq_str = line[26:29].strip()
                if seq_str and seq_str.isdigit():
                    return int(seq_str)
        except Exception as e:
            logger.debug(f"Error parsing sequence number: {e}")
        return None

    def _parse_altitude_descriptor(self, line: str) -> Optional[str]:
        """Parse altitude descriptor from position 82 (@, +, -, B) per ARINC 424"""
        try:
            if len(line) >= 83:
                descriptor = line[82]
                if descriptor in ALTITUDE_DESCRIPTORS and descriptor != ' ':
                    return descriptor
        except Exception as e:
            logger.debug(f"Error parsing altitude descriptor: {e}")
        return None

    def _parse_speed_limit(self, line: str) -> Optional[int]:
        """Parse speed limit from position 99-102 per ARINC 424"""
        try:
            if len(line) >= 102:
                speed_str = line[99:102].strip()
                if speed_str and speed_str.isdigit():
                    return int(speed_str)
        except Exception as e:
            logger.debug(f"Error parsing speed limit: {e}")
        return None

    def _parse_turn_direction(self, line: str) -> Optional[str]:
        """Parse turn direction from position 43 (L, R, E)"""
        try:
            if len(line) >= 44:
                turn = line[43]
                if turn in TURN_DIRECTIONS and turn != ' ':
                    return turn
        except Exception as e:
            logger.debug(f"Error parsing turn direction: {e}")
        return None

    def _parse_transition_identifier(self, line: str) -> Optional[str]:
        """Parse transition identifier from position 20-25"""
        try:
            if len(line) >= 25:
                transition = line[20:25].strip()
                if transition:
                    return transition
        except Exception as e:
            logger.debug(f"Error parsing transition identifier: {e}")
        return None

    def _parse_magnetic_variation(self, line: str) -> Optional[float]:
        """Parse magnetic variation from position 90-94"""
        try:
            if len(line) >= 94:
                mag_var_str = line[90:94].strip()
                if mag_var_str and len(mag_var_str) >= 4:
                    direction = mag_var_str[0]  # E or W
                    magnitude = mag_var_str[1:].strip()
                    if magnitude:
                        value = float(magnitude) / 10.0  # Stored as tenths
                        if direction == 'W':
                            value = -value
                        return value
        except Exception as e:
            logger.debug(f"Error parsing magnetic variation: {e}")
        return None

    def _parse_distance_time(self, line: str) -> Optional[float]:
        """Parse distance or time from position 109-112"""
        try:
            if len(line) >= 112:
                dist_time_str = line[109:112].strip()
                if dist_time_str:
                    # Could be distance in nautical miles or time in minutes
                    # Usually stored as tenths
                    return float(dist_time_str) / 10.0
        except Exception as e:
            logger.debug(f"Error parsing distance/time: {e}")
        return None

    def _parse_recommended_navaid(self, line: str) -> Optional[str]:
        """Parse recommended NAVAID from position 50-54"""
        try:
            if len(line) >= 54:
                navaid = line[50:54].strip()
                if navaid:
                    return navaid
        except Exception as e:
            logger.debug(f"Error parsing recommended NAVAID: {e}")
        return None

    def _parse_route_type(self, line: str, section_code: str) -> Optional[str]:
        """Parse and classify route type based on section and context"""
        try:
            if len(line) >= 20:
                route_char = line[19] if len(line) > 19 else ''

                # Classification depends on section code
                if section_code == 'D':  # SID
                    route_types = {
                        '0': 'Engine Out SID',
                        '1': 'SID Runway Transition',
                        '2': 'SID/SID Common Route',
                        '3': 'SID Enroute Transition',
                        '4': 'RNAV SID Runway Transition',
                        '5': 'RNAV SID/SID Common Route',
                        '6': 'RNAV SID Enroute Transition'
                    }
                elif section_code == 'E':  # STAR
                    route_types = {
                        '1': 'STAR Enroute Transition',
                        '2': 'STAR/STAR Common Route',
                        '3': 'STAR Runway Transition',
                        '4': 'RNAV STAR Enroute Transition',
                        '5': 'RNAV STAR/STAR Common Route',
                        '6': 'RNAV STAR Runway Transition'
                    }
                elif section_code == 'F':  # Approach
                    route_types = {
                        'A': 'Approach Transition',
                        'D': 'Approach or Missed Approach',
                        'F': 'Final Approach Course',
                        'M': 'Missed Approach',
                        'S': 'Approach Transition'
                    }
                else:
                    return None

                return route_types.get(route_char, None)
        except Exception as e:
            logger.debug(f"Error parsing route type: {e}")
        return None

    def _load_data(self):
        """Load and parse the CIFP file"""
        try:
            with open(self.cifp_path, 'r', encoding='latin-1') as f:
                for line in f:
                    if (self.airport_icao in line or
                        line.startswith('SUSAE') or
                        (len(line) > 12 and line.startswith('SUSAP') and line[12] == 'C') or
                        (len(line) > 12 and line.startswith('SUSAD') and line[12] == 'C')):
                        self._parse_line(line)

            # After loading all data, map arrivals to their runways
            self._map_arrivals_to_runways()

            logger.info(f"Loaded {len(self.waypoints)} waypoints for {self.airport_icao}")
            logger.info(f"Found {len(self.arrivals)} arrival procedures")
            logger.info(f"Mapped {len(self.arrival_runways)} STARs to runways")

        except Exception as e:
            logger.error(f"Error loading CIFP: {e}")
            raise

    def _parse_line(self, line: str):
        """Parse a single line from the CIFP file"""
        try:
            if len(line) < 50:
                return

            record_type = line[0:5].strip()

            if record_type not in ['SUSAP', 'SUSAD', 'SUSAE']:
                return

            if record_type == 'SUSAE':
                subsection = line[5] if len(line) > 5 else ''
            else:
                subsection = line[12] if len(line) > 12 else ''

            is_waypoint_definition = subsection == 'C' or (record_type == 'SUSAE' and subsection == 'A')

            if not is_waypoint_definition:
                if record_type in ['SUSAP', 'SUSAD']:
                    airport = line[6:10].strip()
                    if airport != self.airport_icao:
                        return

            if is_waypoint_definition:
                self._parse_waypoint_definition(line)
            elif subsection == 'E':
                self._parse_arrival_waypoint(line)
            elif subsection == 'D':
                self._parse_departure_waypoint(line)
            elif subsection == 'A' and record_type != 'SUSAE':
                self._parse_airport_waypoint(line)

        except Exception as e:
            logger.debug(f"Error parsing line: {e}")

    def _parse_waypoint_definition(self, line: str):
        """Parse a waypoint definition line (subsection C)"""
        try:
            waypoint_name = line[13:18].strip()

            if not waypoint_name or len(waypoint_name) == 0:
                return

            lat_str = line[32:41].strip()
            latitude = self._parse_coordinate(lat_str, is_latitude=True)

            lon_str = line[41:51].strip()
            longitude = self._parse_coordinate(lon_str, is_latitude=False)

            if latitude is not None and longitude is not None:
                waypoint = Waypoint(
                    name=waypoint_name,
                    latitude=latitude,
                    longitude=longitude
                )
                self.waypoints[waypoint_name] = waypoint
                logger.debug(f"Parsed waypoint: {waypoint_name} at {latitude}, {longitude}")

        except Exception as e:
            logger.debug(f"Error parsing waypoint definition: {e}")

    def _parse_arrival_waypoint(self, line: str):
        """Parse an arrival (STAR) waypoint line"""
        try:
            arrival_name_raw = line[13:19].strip()

            match = re.match(r'([A-Z]+\d?)', arrival_name_raw)
            if match:
                arrival_name = match.group(1)
            else:
                arrival_name = arrival_name_raw

            waypoint_name = line[29:34].strip()

            # Extract inbound course (magnetic track) to this waypoint
            # Parse leg type first to determine how to extract course
            leg_type = self._parse_leg_type(line)

            inbound_course = None

            # Extract inbound course from position 70-74 (ARINC 424 standard)
            # This is the magnetic course TO the waypoint for all leg types
            # Course may have "T" suffix for True heading (vs Magnetic)
            course_str = line[70:74].strip()
            if course_str:
                try:
                    # Check if it ends with 'T' for True heading
                    if course_str.endswith('T'):
                        # True heading - remove T and convert
                        inbound_course = int(course_str[:-1])
                        logger.debug(f"Extracted TRUE course {inbound_course}° for {waypoint_name} (leg type: {leg_type})")
                    elif course_str.isdigit():
                        # Magnetic heading
                        inbound_course = int(course_str)
                        logger.debug(f"Extracted MAGNETIC course {inbound_course}° for {waypoint_name} (leg type: {leg_type})")
                except (ValueError, IndexError):
                    pass

            # Extract altitude constraints from multiple positions
            # Primary altitude is at position 84-89 (Altitude 1)
            # Secondary altitude is at position 89-94 (Altitude 2)
            altitude_section = line[66:94] if len(line) >= 94 else line[66:]

            min_alt = None
            max_alt = None

            # Try to extract from position 84-89 (primary altitude)
            if len(line) >= 89:
                alt1_str = line[84:89].strip()
                if alt1_str and alt1_str.isdigit():
                    if len(alt1_str) == 3:
                        min_alt = int(alt1_str) * 100
                    else:
                        min_alt = int(alt1_str)
                    max_alt = min_alt  # Default max to min

            # Try to extract from position 89-94 (secondary altitude for ranges)
            if len(line) >= 94:
                alt2_str = line[89:94].strip()
                if alt2_str and alt2_str.isdigit():
                    if len(alt2_str) == 3:
                        alt2_val = int(alt2_str) * 100
                    else:
                        alt2_val = int(alt2_str)

                    if min_alt:
                        # We have both altitudes - it's a range
                        max_alt = max(min_alt, alt2_val)
                        min_alt = min(min_alt, alt2_val)
                    else:
                        # Only secondary altitude found
                        min_alt = alt2_val
                        max_alt = alt2_val

            # Fallback: try legacy regex pattern on full altitude section
            if min_alt is None and max_alt is None:
                alt_match = re.search(r'(FL)?(\d{3,5})(FL)?(\d{3,5})?', altitude_section)
                if alt_match:
                    alt1 = alt_match.group(2)
                    alt2 = alt_match.group(4)

                    if alt1:
                        if len(alt1) == 3:
                            alt1_feet = int(alt1) * 100
                        else:
                            alt1_feet = int(alt1)

                        if alt2:
                            if len(alt2) == 3:
                                alt2_feet = int(alt2) * 100
                            else:
                                alt2_feet = int(alt2)

                            min_alt = min(alt1_feet, alt2_feet)
                            max_alt = max(alt1_feet, alt2_feet)
                        else:
                            min_alt = alt1_feet
                            max_alt = alt1_feet

            if min_alt or max_alt:
                logger.debug(f"Parsed altitude for {waypoint_name}: min={min_alt}, max={max_alt}")

            # Parse enhanced ARINC 424 fields (leg_type already parsed above for inbound course)
            sequence_number = self._parse_sequence_number(line)
            # leg_type already parsed above - don't parse again
            altitude_descriptor = self._parse_altitude_descriptor(line)
            speed_limit = self._parse_speed_limit(line)
            turn_direction = self._parse_turn_direction(line)
            transition_name = self._parse_transition_identifier(line)
            magnetic_variation = self._parse_magnetic_variation(line)
            distance_time = self._parse_distance_time(line)
            recommended_navaid = self._parse_recommended_navaid(line)
            route_type = self._parse_route_type(line, 'E')

            # Create waypoint object for this specific STAR
            waypoint = Waypoint(
                name=waypoint_name,
                latitude=0.0,
                longitude=0.0,
                arrival_name=arrival_name,
                min_altitude=min_alt,
                max_altitude=max_alt,
                inbound_course=inbound_course,
                sequence_number=sequence_number,
                leg_type=leg_type,
                altitude_descriptor=altitude_descriptor,
                speed_limit=speed_limit,
                turn_direction=turn_direction,
                transition_name=transition_name,
                magnetic_variation=magnetic_variation,
                distance_time=distance_time,
                recommended_navaid=recommended_navaid,
                route_type=route_type
            )

            # Store in STAR-specific dictionary to preserve procedure-specific constraints
            if arrival_name not in self.star_waypoints:
                self.star_waypoints[arrival_name] = {}
            self.star_waypoints[arrival_name][waypoint_name] = waypoint

            # Also store in global waypoints dict (may get overwritten, but kept for backward compatibility)
            if waypoint_name not in self.waypoints:
                self.waypoints[waypoint_name] = waypoint
            else:
                # Update existing global waypoint with latest data
                if waypoint_name in self.waypoints:
                    self.waypoints[waypoint_name].arrival_name = arrival_name
                    if min_alt:
                        self.waypoints[waypoint_name].min_altitude = min_alt
                    if max_alt:
                        self.waypoints[waypoint_name].max_altitude = max_alt
                    if inbound_course:
                        self.waypoints[waypoint_name].inbound_course = inbound_course
                    if sequence_number:
                        self.waypoints[waypoint_name].sequence_number = sequence_number
                    if leg_type:
                        self.waypoints[waypoint_name].leg_type = leg_type
                    if altitude_descriptor:
                        self.waypoints[waypoint_name].altitude_descriptor = altitude_descriptor
                    if speed_limit:
                        self.waypoints[waypoint_name].speed_limit = speed_limit
                    if turn_direction:
                        self.waypoints[waypoint_name].turn_direction = turn_direction
                    if transition_name:
                        self.waypoints[waypoint_name].transition_name = transition_name
                    if magnetic_variation:
                        self.waypoints[waypoint_name].magnetic_variation = magnetic_variation
                    if distance_time:
                        self.waypoints[waypoint_name].distance_time = distance_time
                    if recommended_navaid:
                        self.waypoints[waypoint_name].recommended_navaid = recommended_navaid
                    if route_type:
                        self.waypoints[waypoint_name].route_type = route_type

            if arrival_name:
                if arrival_name not in self.arrivals:
                    self.arrivals[arrival_name] = []
                if waypoint_name and waypoint_name not in self.arrivals[arrival_name]:
                    self.arrivals[arrival_name].append(waypoint_name)

        except Exception as e:
            logger.debug(f"Error parsing arrival waypoint: {e}")

    def _parse_departure_waypoint(self, line: str):
        """Parse a departure (SID) waypoint line"""
        try:
            departure_name = line[15:21].strip()

            waypoint_name = line[29:34].strip()

            altitude_section = line[66:84]

            min_alt = None
            max_alt = None

            alt_match = re.search(r'(FL)?(\d{3,5})(FL)?(\d{3,5})?', altitude_section)
            if alt_match:
                alt1 = alt_match.group(2)
                alt2 = alt_match.group(4)

                if alt1:
                    if len(alt1) == 3:
                        alt1_feet = int(alt1) * 100
                    else:
                        alt1_feet = int(alt1)

                    if alt2:
                        if len(alt2) == 3:
                            alt2_feet = int(alt2) * 100
                        else:
                            alt2_feet = int(alt2)

                        min_alt = min(alt1_feet, alt2_feet)
                        max_alt = max(alt1_feet, alt2_feet)
                    else:
                        min_alt = alt1_feet
                        max_alt = alt1_feet

            # Parse enhanced ARINC 424 fields
            sequence_number = self._parse_sequence_number(line)
            leg_type = self._parse_leg_type(line)
            altitude_descriptor = self._parse_altitude_descriptor(line)
            speed_limit = self._parse_speed_limit(line)
            turn_direction = self._parse_turn_direction(line)
            transition_name = self._parse_transition_identifier(line)
            magnetic_variation = self._parse_magnetic_variation(line)
            distance_time = self._parse_distance_time(line)
            recommended_navaid = self._parse_recommended_navaid(line)
            route_type = self._parse_route_type(line, 'D')

            if waypoint_name and waypoint_name not in self.waypoints:
                waypoint = Waypoint(
                    name=waypoint_name,
                    latitude=0.0,
                    longitude=0.0,
                    min_altitude=min_alt,
                    max_altitude=max_alt,
                    sequence_number=sequence_number,
                    leg_type=leg_type,
                    altitude_descriptor=altitude_descriptor,
                    speed_limit=speed_limit,
                    turn_direction=turn_direction,
                    transition_name=transition_name,
                    magnetic_variation=magnetic_variation,
                    distance_time=distance_time,
                    recommended_navaid=recommended_navaid,
                    route_type=route_type
                )
                self.waypoints[waypoint_name] = waypoint
            else:
                if waypoint_name in self.waypoints:
                    if min_alt:
                        self.waypoints[waypoint_name].min_altitude = min_alt
                    if max_alt:
                        self.waypoints[waypoint_name].max_altitude = max_alt
                    if sequence_number:
                        self.waypoints[waypoint_name].sequence_number = sequence_number
                    if leg_type:
                        self.waypoints[waypoint_name].leg_type = leg_type
                    if altitude_descriptor:
                        self.waypoints[waypoint_name].altitude_descriptor = altitude_descriptor
                    if speed_limit:
                        self.waypoints[waypoint_name].speed_limit = speed_limit
                    if turn_direction:
                        self.waypoints[waypoint_name].turn_direction = turn_direction
                    if transition_name:
                        self.waypoints[waypoint_name].transition_name = transition_name
                    if magnetic_variation:
                        self.waypoints[waypoint_name].magnetic_variation = magnetic_variation
                    if distance_time:
                        self.waypoints[waypoint_name].distance_time = distance_time
                    if recommended_navaid:
                        self.waypoints[waypoint_name].recommended_navaid = recommended_navaid
                    if route_type:
                        self.waypoints[waypoint_name].route_type = route_type

        except Exception as e:
            logger.debug(f"Error parsing departure waypoint: {e}")

    def _parse_airport_waypoint(self, line: str):
        """Parse airport reference point or terminal area waypoint"""
        try:
            waypoint_name = line[13:18].strip()

            if not waypoint_name or len(waypoint_name) == 0:
                return

            lat_str = line[32:41].strip()
            lon_str = line[41:51].strip()

            latitude = self._parse_coordinate(lat_str, is_latitude=True)
            longitude = self._parse_coordinate(lon_str, is_latitude=False)

            if latitude is not None and longitude is not None and waypoint_name:
                if waypoint_name not in self.waypoints:
                    waypoint = Waypoint(
                        name=waypoint_name,
                        latitude=latitude,
                        longitude=longitude
                    )
                    self.waypoints[waypoint_name] = waypoint
                else:
                    if self.waypoints[waypoint_name].latitude == 0.0:
                        self.waypoints[waypoint_name].latitude = latitude
                    if self.waypoints[waypoint_name].longitude == 0.0:
                        self.waypoints[waypoint_name].longitude = longitude

        except Exception as e:
            logger.debug(f"Error parsing airport waypoint: {e}")

    def _parse_coordinate(self, coord_str: str, is_latitude: bool) -> Optional[float]:
        """Parse a coordinate from CIFP format"""
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
        """Get a waypoint by name"""
        return self.waypoints.get(waypoint_name)

    def get_arrival_waypoints(self, arrival_name: str) -> List[str]:
        """Get all waypoints for an arrival procedure"""
        return self.arrivals.get(arrival_name, [])

    def get_all_waypoints(self) -> List[Waypoint]:
        """Get all waypoints"""
        return list(self.waypoints.values())

    def _map_arrivals_to_runways(self):
        """Map each STAR to the runways it can feed based on runway-specific transitions"""
        import re

        # Extract runways from STAR waypoint data
        # STARs often have runway-specific transitions like "BRRTO16RW03", "BRRTO16RW08", etc.
        for arrival_name, waypoint_names in self.arrivals.items():
            runways_for_this_star = set()

            # Check if any waypoints in star_waypoints have runway-specific suffixes
            if arrival_name in self.star_waypoints:
                for waypoint_name, waypoint in self.star_waypoints[arrival_name].items():
                    # Check transition_name field for runway patterns (e.g., "RW03", "RW08")
                    if waypoint.transition_name:
                        rwy_match = re.search(r'RW(\d{2}[LCR]?)', waypoint.transition_name)
                        if rwy_match:
                            runway = rwy_match.group(1)
                            runways_for_this_star.add(runway)

            # Also check the arrivals dictionary keys themselves for runway patterns
            # Some CIFP data encodes runways in the arrival name (e.g., "BRRTO16RW03")
            for key in self.arrivals.keys():
                if key.startswith(arrival_name):
                    rwy_match = re.search(r'RW(\d{2}[LCR]?)', key)
                    if rwy_match:
                        runway = rwy_match.group(1)
                        runways_for_this_star.add(runway)

            if runways_for_this_star:
                self.arrival_runways[arrival_name] = sorted(list(runways_for_this_star))
                logger.debug(f"Mapped STAR {arrival_name} to runways: {', '.join(sorted(runways_for_this_star))}")
            else:
                logger.warning(f"No runways found for STAR {arrival_name}")

    def get_runways_for_arrival(self, arrival_name: str) -> List[str]:
        """
        Get the runways that a specific STAR/arrival can feed

        Args:
            arrival_name: Name of the STAR (e.g., "HYDRR1", "EAGUL6")

        Returns:
            List of runway designators (e.g., ['25L', '25R'])
        """
        return self.arrival_runways.get(arrival_name, [])

    def get_transition_waypoint(self, waypoint_name: str, star_name: str) -> Optional[Waypoint]:
        """
        Get a waypoint by name and STAR name with STAR-specific constraints

        This method allows users to specify ANY waypoint along a STAR procedure,
        not just entry/transition points. It retrieves the waypoint with the
        specific altitude/speed constraints for that STAR.

        Args:
            waypoint_name: Waypoint identifier (e.g., "EAGUL", "PINNG", "CHILY")
            star_name: STAR name (e.g., "JESSE3", "PINNG1")

        Returns:
            Waypoint object if found, None otherwise
        """
        # First, try to get waypoint from STAR-specific dictionary
        # This preserves procedure-specific altitude/speed constraints
        if star_name in self.star_waypoints:
            if waypoint_name in self.star_waypoints[star_name]:
                waypoint = self.star_waypoints[star_name][waypoint_name]
                # Need to get coordinates from global waypoints dict (if available)
                if waypoint_name in self.waypoints:
                    if waypoint.latitude == 0.0 and waypoint.longitude == 0.0:
                        waypoint.latitude = self.waypoints[waypoint_name].latitude
                        waypoint.longitude = self.waypoints[waypoint_name].longitude
                logger.debug(f"Found waypoint {waypoint_name} on STAR {star_name} with procedure-specific constraints")
                logger.debug(f"  Altitude: {waypoint.altitude_descriptor} {waypoint.min_altitude}-{waypoint.max_altitude}")
                logger.debug(f"  Speed: {waypoint.speed_limit} knots" if waypoint.speed_limit else "  Speed: No restriction")
                logger.debug(f"  Inbound course: {waypoint.inbound_course}°" if waypoint.inbound_course else "  Inbound course: Not specified")
                return waypoint

        # Fallback: try direct waypoint name lookup (legacy behavior)
        if waypoint_name in self.waypoints:
            waypoint = self.waypoints[waypoint_name]
            # Verify it's associated with the specified STAR
            if waypoint.arrival_name == star_name:
                logger.warning(f"Using global waypoint data for {waypoint_name} on STAR {star_name} (STAR-specific data not found)")
                return waypoint

        # If not found with exact match, search through all waypoints in the STAR
        arrival_waypoints = self.get_arrival_waypoints(star_name)
        if waypoint_name in arrival_waypoints:
            waypoint = self.waypoints.get(waypoint_name)
            if waypoint:
                logger.warning(f"Found waypoint {waypoint_name} in STAR {star_name} waypoint list, but using global data")
                return waypoint

        # Also try matching by transition_name field (legacy support)
        for wp_name, waypoint in self.waypoints.items():
            if waypoint.arrival_name == star_name and waypoint.transition_name == waypoint_name:
                logger.debug(f"Found waypoint via transition_name: {wp_name} (transition={waypoint_name}, STAR={star_name})")
                return waypoint

        logger.warning(f"Waypoint {waypoint_name} not found on STAR {star_name}")
        logger.debug(f"Available waypoints for {star_name}: {', '.join(arrival_waypoints[:10])}")
        return None

    def get_next_waypoint_in_star(self, star_name: str, current_sequence: int) -> Optional[Waypoint]:
        """
        Get the next waypoint in a STAR sequence

        Args:
            star_name: STAR name (e.g., "BRRTO1")
            current_sequence: Current waypoint sequence number

        Returns:
            Next Waypoint object if found, None otherwise
        """
        if star_name not in self.star_waypoints:
            return None

        # Find waypoint with next sequence number
        next_sequence = current_sequence + 10  # CIFP sequences typically increment by 10
        for waypoint_name, waypoint in self.star_waypoints[star_name].items():
            if waypoint.sequence_number == next_sequence:
                # Get coordinates from global waypoints if needed
                if waypoint.latitude == 0.0 and waypoint.longitude == 0.0:
                    if waypoint_name in self.waypoints:
                        waypoint.latitude = self.waypoints[waypoint_name].latitude
                        waypoint.longitude = self.waypoints[waypoint_name].longitude
                return waypoint

        # If exact sequence not found, find the next higher sequence number
        next_waypoints = []
        for waypoint_name, waypoint in self.star_waypoints[star_name].items():
            if waypoint.sequence_number and waypoint.sequence_number > current_sequence:
                next_waypoints.append((waypoint.sequence_number, waypoint_name, waypoint))

        if next_waypoints:
            # Sort by sequence number and get the first one
            next_waypoints.sort(key=lambda x: x[0])
            _, waypoint_name, waypoint = next_waypoints[0]

            # Get coordinates from global waypoints if needed
            if waypoint.latitude == 0.0 and waypoint.longitude == 0.0:
                if waypoint_name in self.waypoints:
                    waypoint.latitude = self.waypoints[waypoint_name].latitude
                    waypoint.longitude = self.waypoints[waypoint_name].longitude

            return waypoint

        return None

    def get_available_transitions(self, star_name: str) -> List[str]:
        """
        Get list of available transitions for a STAR

        Args:
            star_name: STAR name (e.g., "JESSE3")

        Returns:
            List of transition waypoint names
        """
        transitions = set()

        for waypoint_name, waypoint in self.waypoints.items():
            if waypoint.arrival_name == star_name:
                # If there's a transition_name field, use it
                if waypoint.transition_name:
                    transitions.add(waypoint.transition_name)
                # Otherwise, the waypoint name itself might be the transition
                else:
                    # Check if this looks like a transition waypoint (typically at start of STAR)
                    # For now, add all waypoints in the STAR
                    transitions.add(waypoint_name)

        return sorted(list(transitions))

    def get_available_stars(self) -> List[str]:
        """
        Get list of all available STAR names

        Returns:
            List of STAR names
        """
        return sorted(list(self.arrivals.keys()))
