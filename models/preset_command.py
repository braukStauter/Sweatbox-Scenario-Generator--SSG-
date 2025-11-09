"""
Preset Command Rule Model

This module defines the data model for preset command rules that can be applied
to groups of aircraft in vNAS scenarios.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PresetCommandRule:
    """
    Represents a preset command rule that applies a vNAS command to a group of aircraft.

    Attributes:
        group_type: Type of aircraft grouping:
            - "all": All aircraft
            - "airline": Filter by airline/operator
            - "destination": Filter by arrival airport
            - "origin": Filter by departure airport
            - "aircraft_type": Filter by aircraft type
            - "random": Random selection of aircraft
            - "departures": All departures (aircraft with parking spots)
            - "arrivals": All arrivals (aircraft without parking spots)
        group_value: Value for the group filter (e.g., "AAL" for airline, "5" for random count).
                    Not used for "all", "departures", "arrivals".
        command_template: vNAS command with optional variables (e.g., "SAYF THIS IS $aid")
    """
    group_type: str
    group_value: Optional[str]
    command_template: str

    def __post_init__(self):
        """Validate the preset command rule"""
        valid_group_types = [
            "all", "airline", "destination", "origin", "aircraft_type",
            "random", "departures", "arrivals", "parking"
        ]

        if self.group_type not in valid_group_types:
            raise ValueError(f"Invalid group_type: {self.group_type}. Must be one of {valid_group_types}")

        # Validate that group_value is provided when required
        if self.group_type in ["airline", "destination", "origin", "aircraft_type", "random", "parking"]:
            if not self.group_value:
                raise ValueError(f"group_value is required for group_type '{self.group_type}'")

        if not self.command_template:
            raise ValueError("command_template cannot be empty")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "group_type": self.group_type,
            "group_value": self.group_value,
            "command_template": self.command_template
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PresetCommandRule':
        """Create from dictionary (deserialization)"""
        return cls(
            group_type=data["group_type"],
            group_value=data.get("group_value"),
            command_template=data["command_template"]
        )

    def get_specificity_score(self) -> int:
        """
        Return a specificity score for ordering command application.
        Higher score = more specific. Used to apply general commands before specific ones.

        Scores:
            0: all aircraft
            1: departures/arrivals (operation type)
            2: random (subset)
            3: airline, destination, origin, aircraft_type (specific criteria)
            4: parking (most specific - exact location)
        """
        specificity_map = {
            "all": 0,
            "departures": 1,
            "arrivals": 1,
            "random": 2,
            "airline": 3,
            "destination": 3,
            "origin": 3,
            "aircraft_type": 3,
            "parking": 4
        }
        return specificity_map.get(self.group_type, 0)
