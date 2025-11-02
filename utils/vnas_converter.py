"""
Converter utility for transforming Aircraft objects to vNAS format
"""
import time
import logging
from typing import List, Dict, Optional
from models.aircraft import Aircraft

try:
    from ulid import ULID
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-ulid'])
    from ulid import ULID

logger = logging.getLogger(__name__)


def generate_ulid() -> str:
    """Generate a ULID string"""
    return str(ULID.from_timestamp(time.time()))


class VNASConverter:
    """Converter for vNAS scenario format"""

    def __init__(self, airport_icao: str, scenario_name: str = None, artcc_id: str = None):
        """
        Initialize the converter

        Args:
            airport_icao: Airport ICAO code (e.g., "KPHX")
            scenario_name: Optional custom scenario name
            artcc_id: Optional ARTCC ID (auto-detected if not provided)
        """
        self.airport_icao = airport_icao
        self.scenario_name = scenario_name or f"Generated Scenario - {airport_icao}"

        # Auto-detect ARTCC if not provided
        if artcc_id:
            self.artcc_id = artcc_id
        else:
            from utils.artcc_lookup import get_artcc_for_airport
            self.artcc_id = get_artcc_for_airport(airport_icao)
            logger.info(f"Auto-detected ARTCC: {self.artcc_id} for airport {airport_icao}")

    def convert_aircraft_to_vnas(self, aircraft: Aircraft) -> Dict:
        """
        Convert a single Aircraft object to vNAS format

        Args:
            aircraft: Aircraft object to convert
        """
        vnas_aircraft = {
            "id": generate_ulid(),
            "aircraftId": aircraft.callsign,
            "aircraftType": aircraft.aircraft_type,
            "transponderMode": "Standby" if aircraft.squawk_mode == "S" else "C",
            "startingConditions": self._get_starting_conditions(aircraft),
            "onAltitudeProfile": aircraft.ground_speed > 0,
            "presetCommands": self._get_preset_commands(aircraft),
            "difficulty": aircraft.difficulty
        }

        # Optional spawn delay
        if aircraft.spawn_delay is not None:
            vnas_aircraft["spawnDelay"] = aircraft.spawn_delay
            logger.info(f"Adding spawnDelay={aircraft.spawn_delay}s to vNAS aircraft {aircraft.callsign}")

        # Optional primary airport override
        if aircraft.primary_airport:
            vnas_aircraft["airportId"] = aircraft.primary_airport
        elif aircraft.arrival and aircraft.arrival == self.airport_icao:
            vnas_aircraft["airportId"] = self.airport_icao

        # Optional expected approach
        if aircraft.expected_approach:
            vnas_aircraft["expectedApproach"] = aircraft.expected_approach

        # Flight plan
        if aircraft.departure or aircraft.arrival:
            flight_rules_map = {
                "I": "IFR",
                "V": "VFR"
            }

            # Remove runway from route for flight plan display
            # Route format is typically "WAYPOINT ARRIVAL.RUNWAY" but flight plan should show "WAYPOINT ARRIVAL"
            route = aircraft.route or ""
            if route:
                import re
                # Remove .RUNWAY suffix (e.g., ".25L", ".07R")
                # Match a period followed by runway designator (1-2 digits + optional L/C/R)
                route = re.sub(r'\.\d{1,2}[LCR]?$', '', route)

            flightplan = {
                "rules": flight_rules_map.get(aircraft.flight_rules, "IFR"),
                "departure": aircraft.departure or "",
                "destination": aircraft.arrival or "",
                "cruiseAltitude": int(aircraft.cruise_altitude) if aircraft.cruise_altitude and aircraft.cruise_altitude.isdigit() else 0,
                "cruiseSpeed": aircraft.cruise_speed if aircraft.cruise_speed else 0,
                "route": route,
                "remarks": aircraft.remarks or "/V/",
                "aircraftType": aircraft.aircraft_type.replace("/L", "").replace("/G", "").replace("/A", "")
            }
            vnas_aircraft["flightplan"] = flightplan

        # Auto track configuration
        if aircraft.auto_track_position_id:
            vnas_aircraft["autoTrackConditions"] = self._get_auto_track_config(aircraft)

        return vnas_aircraft

    def _get_preset_commands(self, aircraft: Aircraft) -> list:
        """
        Convert preset commands to vNAS format

        Args:
            aircraft: Aircraft object

        Returns:
            List of command objects
        """
        commands = []
        for command_str in aircraft.preset_commands:
            commands.append({
                "command": command_str
            })
        return commands

    def _get_auto_track_config(self, aircraft: Aircraft) -> Dict:
        """
        Build auto track configuration

        Args:
            aircraft: Aircraft object

        Returns:
            Auto track configuration dict
        """
        config = {
            "positionId": aircraft.auto_track_position_id
        }

        if aircraft.auto_track_handoff_delay is not None:
            config["handoffDelay"] = aircraft.auto_track_handoff_delay

        if aircraft.auto_track_scratchpad:
            config["scratchPad"] = aircraft.auto_track_scratchpad

        if aircraft.auto_track_interim_altitude:
            config["interimAltitude"] = aircraft.auto_track_interim_altitude

        if aircraft.auto_track_cleared_altitude:
            config["clearedAltitude"] = aircraft.auto_track_cleared_altitude

        return config

    def _get_starting_conditions(self, aircraft: Aircraft) -> Dict:
        """
        Determine the starting conditions based on aircraft state

        Args:
            aircraft: Aircraft object
        """
        # Parking
        if aircraft.parking_spot_name:
            return {
                "type": "Parking",
                "parking": aircraft.parking_spot_name
            }

        # On Final with enhanced parameters
        if aircraft.arrival_runway and aircraft.arrival_distance_nm is not None:
            conditions = {
                "type": "OnFinal",
                "runway": aircraft.arrival_runway,
                "distanceFromRunway": int(aircraft.arrival_distance_nm),
                "speed": aircraft.ground_speed
            }

            # Optional final approach course offset
            if aircraft.final_approach_course_offset is not None:
                conditions["finalApproachCourseOffset"] = aircraft.final_approach_course_offset

            return conditions

        # Fix or FRD with enhanced parameters
        # The navigation_path contains the FRD format representing where the aircraft IS spawning
        # Example: PINNG112010 means "10NM from PINNG on the 112 radial" - that's the spawn point
        fix_or_frd = "UNKNOWN"
        if aircraft.navigation_path:
            # Use the full FRD format as the spawn position
            fix_or_frd = aircraft.navigation_path

        conditions = {
            "type": "FixOrFrd",
            "fix": fix_or_frd,
            "altitude": aircraft.altitude,
            "speed": aircraft.ground_speed
        }

        # Set initial path to the route (the actual routing to fly)
        if aircraft.route:
            conditions["navigationPath"] = aircraft.route

        # Optional heading
        if aircraft.heading:
            conditions["heading"] = aircraft.heading

        # Optional mach
        if aircraft.mach is not None:
            conditions["mach"] = aircraft.mach

        return conditions

    def _extract_runway_from_route(self, aircraft: Aircraft) -> Optional[str]:
        """Try to extract runway from aircraft route/remarks"""
        if aircraft.route:
            parts = aircraft.route.split()
            for part in parts:
                if part.isdigit() or (len(part) <= 3 and part[0].isdigit()):
                    return part
        return None

    def _calculate_distance_from_airport(self, aircraft: Aircraft) -> int:
        """
        Calculate approximate distance from airport in nautical miles
        This is a simplified calculation based on altitude
        """
        from utils.geo_utils import haversine_distance

        field_elevation = 1000
        altitude_agl = aircraft.altitude - field_elevation

        distance_nm = max(1, int(altitude_agl / 300))
        return distance_nm

    def create_vnas_scenario(self, aircraft_list: List[Aircraft]) -> Dict:
        """
        Create a complete vNAS scenario JSON from a list of Aircraft

        Args:
            aircraft_list: List of Aircraft objects to convert
        """
        vnas_aircraft = []

        for aircraft in aircraft_list:
            vnas_ac = self.convert_aircraft_to_vnas(aircraft)
            vnas_aircraft.append(vnas_ac)

        # Use 3-letter airport code for primaryAirportId (remove K prefix if present)
        airport_code = self.airport_icao
        if airport_code.startswith('K') and len(airport_code) == 4:
            airport_code = airport_code[1:]

        scenario = {
            "name": self.scenario_name,
            "artccId": self.artcc_id,
            "initializationTriggers": [],
            "aircraftGenerators": [],
            "aircraft": vnas_aircraft,
            "atc": [],
            "primaryAirportId": airport_code,
            "autoDeleteMode": "None",
            "flightStripConfigurations": []
        }

        logger.info(f"Created vNAS scenario with {len(vnas_aircraft)} aircraft")
        return scenario
