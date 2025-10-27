"""
Parser for FAA CIFP (Coded Instrument Flight Procedures) files
"""
import logging
import re
from typing import List, Dict, Optional
from models.airport import Waypoint

logger = logging.getLogger(__name__)


class CIFPParser:
    """Parser for FAA CIFP files"""

    def __init__(self, cifp_path: str, airport_icao: str):
        """Initialize the parser"""
        self.cifp_path = cifp_path
        self.airport_icao = airport_icao
        self.waypoints: Dict[str, Waypoint] = {}
        self.arrivals: Dict[str, List[str]] = {}
        self.approach_faf_altitudes: Dict[str, int] = {}
        self._load_data()

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

            logger.info(f"Loaded {len(self.waypoints)} waypoints for {self.airport_icao}")
            logger.info(f"Found {len(self.arrivals)} arrival procedures")
            logger.info(f"Found {len(self.approach_faf_altitudes)} approach FAF altitudes")

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
            elif subsection == 'F':
                self._parse_approach_procedure(line)
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

            if waypoint_name and waypoint_name not in self.waypoints:
                waypoint = Waypoint(
                    name=waypoint_name,
                    latitude=0.0,
                    longitude=0.0,
                    arrival_name=arrival_name,
                    min_altitude=min_alt,
                    max_altitude=max_alt
                )
                self.waypoints[waypoint_name] = waypoint
            else:
                if waypoint_name in self.waypoints:
                    self.waypoints[waypoint_name].arrival_name = arrival_name
                    if min_alt:
                        self.waypoints[waypoint_name].min_altitude = min_alt
                    if max_alt:
                        self.waypoints[waypoint_name].max_altitude = max_alt

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

            if waypoint_name and waypoint_name not in self.waypoints:
                waypoint = Waypoint(
                    name=waypoint_name,
                    latitude=0.0,
                    longitude=0.0,
                    min_altitude=min_alt,
                    max_altitude=max_alt
                )
                self.waypoints[waypoint_name] = waypoint
            else:
                if waypoint_name in self.waypoints:
                    if min_alt:
                        self.waypoints[waypoint_name].min_altitude = min_alt
                    if max_alt:
                        self.waypoints[waypoint_name].max_altitude = max_alt

        except Exception as e:
            logger.debug(f"Error parsing departure waypoint: {e}")

    def _parse_approach_procedure(self, line: str):
        """Parse approach procedure line (subsection F) to extract FAF altitudes"""
        try:
            if len(line) < 90:
                return

            runway_raw = line[20:25].strip()

            runway = runway_raw.replace('RW', '').strip()

            if not runway:
                return

            waypoint_desc = line[39:41].strip() if len(line) > 40 else ''

            is_faf = 'F' in waypoint_desc or waypoint_desc in ['AF', 'CF', 'DF', 'IF']

            if is_faf:
                altitude_str = line[84:89].strip() if len(line) > 88 else ''

                if altitude_str:
                    try:
                        if altitude_str.startswith('FL'):
                            altitude = int(altitude_str[2:]) * 100
                        else:
                            altitude = int(altitude_str)

                        if runway not in self.approach_faf_altitudes or altitude > self.approach_faf_altitudes[runway]:
                            self.approach_faf_altitudes[runway] = altitude
                            logger.debug(f"FAF altitude for runway {runway}: {altitude} ft MSL")

                    except ValueError:
                        pass

        except Exception as e:
            logger.debug(f"Error parsing approach procedure: {e}")

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

    def get_faf_altitude(self, runway_name: str) -> Optional[int]:
        """Get the Final Approach Fix altitude for a runway"""
        return self.approach_faf_altitudes.get(runway_name)
