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

    # Transponder and engine configuration
    engine_type: str = "J"
    squawk_mode: str = "N"  # Used by vNAS for transponder mode: "S" = Standby, "N" = Normal (Mode C)

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
