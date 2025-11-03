"""
Generator for creating human-readable backup scenario text files with vNAS fields
"""
import logging
from typing import List
from models.aircraft import Aircraft
from datetime import datetime

logger = logging.getLogger(__name__)


class BackupScenarioGenerator:
    """Generator for creating backup scenario text files with vNAS format details"""

    def __init__(self, output_path: str):
        """
        Initialize the backup scenario generator

        Args:
            output_path: Path where the backup text file will be written
        """
        self.output_path = output_path
        self.aircraft = []
        logger.info(f"Initialized backup scenario generator with output: {output_path}")

    def add_aircraft(self, aircraft: Aircraft):
        """
        Add a single aircraft to the scenario

        Args:
            aircraft: Aircraft object to add
        """
        self.aircraft.append(aircraft)
        logger.debug(f"Added aircraft: {aircraft.callsign}")

    def add_aircraft_list(self, aircraft_list: List[Aircraft]):
        """
        Add multiple aircraft to the scenario

        Args:
            aircraft_list: List of Aircraft objects to add
        """
        self.aircraft.extend(aircraft_list)
        logger.info(f"Added {len(aircraft_list)} aircraft to backup scenario")

    def _format_aircraft_entry(self, aircraft: Aircraft, index: int) -> str:
        """
        Format a single aircraft entry with all vNAS fields

        Args:
            aircraft: Aircraft object to format
            index: Aircraft number (1-indexed)

        Returns:
            Formatted string with all aircraft details
        """
        lines = []
        lines.append(f"{'='*80}")
        lines.append(f"AIRCRAFT #{index}: {aircraft.callsign}")
        lines.append(f"{'='*80}")
        lines.append("")

        # Basic Aircraft Information
        lines.append("BASIC INFORMATION:")
        lines.append(f"  Callsign:        {aircraft.callsign}")
        lines.append(f"  Aircraft Type:   {aircraft.aircraft_type}")
        lines.append(f"  Engine Type:     {aircraft.engine_type}")
        lines.append("")

        # Flight Plan
        lines.append("FLIGHT PLAN:")
        lines.append(f"  Rules:           {aircraft.flight_rules}")
        lines.append(f"  Departure:       {aircraft.departure or 'N/A'}")
        lines.append(f"  Arrival:         {aircraft.arrival or 'N/A'}")
        lines.append(f"  Route:           {aircraft.route or 'N/A'}")
        lines.append(f"  Cruise Altitude: {aircraft.cruise_altitude or 'N/A'}")
        lines.append(f"  Cruise Speed:    {aircraft.cruise_speed or 'N/A'} knots")
        lines.append(f"  Remarks:         {aircraft.remarks or 'N/A'}")
        lines.append("")

        # Position & State
        lines.append("POSITION & STATE:")
        lines.append(f"  Latitude:        {aircraft.latitude:.6f}")
        lines.append(f"  Longitude:       {aircraft.longitude:.6f}")
        lines.append(f"  Altitude:        {aircraft.altitude} ft")
        lines.append(f"  Heading:         {aircraft.heading}°")
        lines.append(f"  Ground Speed:    {aircraft.ground_speed} knots")
        if aircraft.mach is not None:
            lines.append(f"  Mach:            {aircraft.mach}")
        lines.append("")

        # Transponder
        lines.append("TRANSPONDER:")
        transponder_mode = "Standby" if aircraft.squawk_mode == "S" else "Mode C"
        lines.append(f"  Mode:            {transponder_mode}")
        lines.append("")

        # Starting Conditions
        lines.append("STARTING CONDITIONS:")
        if aircraft.parking_spot_name:
            lines.append(f"  Type:            Parking")
            lines.append(f"  Parking Spot:    {aircraft.parking_spot_name}")
        elif aircraft.arrival_runway and aircraft.arrival_distance_nm is not None:
            lines.append(f"  Type:            On Final")
            lines.append(f"  Runway:          {aircraft.arrival_runway}")
            lines.append(f"  Distance:        {aircraft.arrival_distance_nm} NM")
            if aircraft.final_approach_course_offset is not None:
                lines.append(f"  Course Offset:   {aircraft.final_approach_course_offset}°")
        elif aircraft.navigation_path:
            lines.append(f"  Type:            Fix or FRD")
            lines.append(f"  Fix/FRD:         {aircraft.navigation_path}")
            if aircraft.route:
                lines.append(f"  Nav Path:        {aircraft.route}")
        else:
            lines.append(f"  Type:            Fix or FRD")
            lines.append(f"  Position:        {aircraft.latitude:.6f}, {aircraft.longitude:.6f}")

        lines.append("")

        # Advanced vNAS Features
        has_advanced = False
        advanced_lines = []

        if aircraft.spawn_delay is not None and aircraft.spawn_delay > 0:
            advanced_lines.append(f"  Spawn Delay:     {aircraft.spawn_delay} seconds")
            has_advanced = True

        if aircraft.expected_approach:
            advanced_lines.append(f"  Expected Approach: {aircraft.expected_approach}")
            has_advanced = True

        if aircraft.difficulty != "Easy":
            advanced_lines.append(f"  Difficulty:      {aircraft.difficulty}")
            has_advanced = True

        if aircraft.primary_airport:
            advanced_lines.append(f"  Primary Airport: {aircraft.primary_airport}")
            has_advanced = True

        if aircraft.preset_commands:
            advanced_lines.append(f"  Preset Commands:")
            for cmd in aircraft.preset_commands:
                advanced_lines.append(f"    - {cmd}")
            has_advanced = True

        if aircraft.auto_track_position_id:
            advanced_lines.append(f"  Auto Track:")
            advanced_lines.append(f"    Position ID:   {aircraft.auto_track_position_id}")
            if aircraft.auto_track_handoff_delay is not None:
                advanced_lines.append(f"    Handoff Delay: {aircraft.auto_track_handoff_delay} seconds")
            if aircraft.auto_track_scratchpad:
                advanced_lines.append(f"    Scratchpad:    {aircraft.auto_track_scratchpad}")
            if aircraft.auto_track_interim_altitude:
                advanced_lines.append(f"    Interim Alt:   {aircraft.auto_track_interim_altitude}")
            if aircraft.auto_track_cleared_altitude:
                advanced_lines.append(f"    Cleared Alt:   {aircraft.auto_track_cleared_altitude}")
            has_advanced = True

        if has_advanced:
            lines.append("ADVANCED vNAS FEATURES:")
            lines.extend(advanced_lines)
            lines.append("")

        return "\n".join(lines)

    def generate(self):
        """
        Generate the backup scenario text file

        Raises:
            IOError: If file cannot be written
        """
        try:
            with open(self.output_path, 'w', encoding='utf-8') as f:
                # Write header
                f.write("=" * 80 + "\n")
                f.write("vNAS SCENARIO BACKUP - HUMAN READABLE FORMAT\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Aircraft: {len(self.aircraft)}\n")
                f.write("=" * 80 + "\n\n")

                # Categorize aircraft
                arrivals = [ac for ac in self.aircraft if ac.arrival and not ac.parking_spot_name]
                departures = [ac for ac in self.aircraft if ac.departure and ac.parking_spot_name]
                other = [ac for ac in self.aircraft if ac not in arrivals and ac not in departures]

                # Write summary
                f.write("SCENARIO SUMMARY:\n")
                f.write(f"  Arrivals:   {len(arrivals)}\n")
                f.write(f"  Departures: {len(departures)}\n")
                if other:
                    f.write(f"  Other:      {len(other)}\n")
                f.write("\n\n")

                # Write arrivals section
                if arrivals:
                    f.write("+" * 80 + "\n")
                    f.write("ARRIVALS\n")
                    f.write("+" * 80 + "\n\n")
                    for idx, aircraft in enumerate(arrivals, 1):
                        f.write(self._format_aircraft_entry(aircraft, idx))
                        f.write("\n")

                # Write departures section
                if departures:
                    f.write("+" * 80 + "\n")
                    f.write("DEPARTURES\n")
                    f.write("+" * 80 + "\n\n")
                    for idx, aircraft in enumerate(departures, 1):
                        f.write(self._format_aircraft_entry(aircraft, idx))
                        f.write("\n")

                # Write other aircraft section
                if other:
                    f.write("+" * 80 + "\n")
                    f.write("OTHER AIRCRAFT\n")
                    f.write("+" * 80 + "\n\n")
                    for idx, aircraft in enumerate(other, 1):
                        f.write(self._format_aircraft_entry(aircraft, idx))
                        f.write("\n")

                # Write footer
                f.write("=" * 80 + "\n")
                f.write("END OF SCENARIO BACKUP\n")
                f.write("=" * 80 + "\n")

            logger.info(f"Successfully generated backup scenario with {len(self.aircraft)} aircraft: {self.output_path}")

        except IOError as e:
            logger.error(f"Failed to write backup scenario file: {e}")
            raise

    def clear(self):
        """Clear all aircraft from the generator"""
        self.aircraft = []
        logger.debug("Cleared aircraft list from backup scenario generator")
