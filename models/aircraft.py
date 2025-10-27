"""
Aircraft data model
"""
from dataclasses import dataclass
from typing import Optional


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

    departure: Optional[str] = None
    arrival: Optional[str] = None
    route: Optional[str] = None
    cruise_altitude: Optional[str] = None
    remarks: Optional[str] = None
    flight_rules: str = "I"

    engine_type: str = "J"
    squawk_code: str = "1200"
    squawk_mode: str = "N"

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
