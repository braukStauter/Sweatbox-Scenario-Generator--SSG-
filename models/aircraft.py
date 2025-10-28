"""
Aircraft data model
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Aircraft:
    """Represents an aircraft in the simulation"""
    callsign: str
    aircraft_type: str
    latitude: float
    longitude: float
    altitude: int
    heading: int
    ground_speed: int

    # Flight plan
    departure: Optional[str] = None
    arrival: Optional[str] = None
    route: Optional[str] = None
    cruise_altitude: Optional[str] = None
    cruise_speed: Optional[int] = None
    remarks: Optional[str] = None
    flight_rules: str = "I"

    # Legacy .air file format
    engine_type: str = "J"
    squawk_code: str = "1200"
    squawk_mode: str = "N"

    # Starting conditions
    parking_spot_name: Optional[str] = None
    arrival_runway: Optional[str] = None
    arrival_distance_nm: Optional[float] = None

    # Advanced vNAS features
    # Spawn control
    spawn_delay: Optional[int] = None  # seconds
    expected_approach: Optional[str] = None
    difficulty: str = "Easy"  # Easy, Medium, Hard
    primary_airport: Optional[str] = None

    # Enhanced starting conditions parameters
    mach: Optional[float] = None
    navigation_path: Optional[str] = None
    final_approach_course_offset: Optional[int] = None  # degrees

    # Preset commands
    preset_commands: List[str] = field(default_factory=list)

    # Auto track configuration
    auto_track_position_id: Optional[str] = None
    auto_track_handoff_delay: Optional[int] = None  # seconds
    auto_track_scratchpad: Optional[str] = None
    auto_track_interim_altitude: Optional[str] = None
    auto_track_cleared_altitude: Optional[str] = None

    def to_air_line(self) -> str:
        """Convert aircraft to .air file format"""
        crz_alt = self.cruise_altitude if self.cruise_altitude else ""
        route = self.route if self.route else ""
        dep = self.departure if self.departure else ""
        arr = self.arrival if self.arrival else ""

        parts = [
            self.callsign,
            self.aircraft_type,
            self.engine_type,
            self.flight_rules,
            dep,
            arr,
            crz_alt,
            route,
            self.remarks or "",
            self.squawk_code,
            self.squawk_mode,
            f"{self.latitude:.6f}",
            f"{self.longitude:.6f}",
            str(self.altitude),
            str(self.ground_speed),
            str(self.heading)
        ]

        return ":".join(parts)
