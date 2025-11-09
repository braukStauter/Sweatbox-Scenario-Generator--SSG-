"""
Preset Command Processor

This module handles the processing and application of preset commands to aircraft,
including variable substitution and group matching.
"""

import random
import re
from typing import List
from models.aircraft import Aircraft
from models.preset_command import PresetCommandRule


# Variable mapping: variable name -> aircraft attribute name
VARIABLE_MAP = {
    # Primary identification
    "$aid": "callsign",
    "$callsign": "callsign",
    "$type": "aircraft_type",
    "$actype": "aircraft_type",

    # Airports
    "$dep": "departure",
    "$departure": "departure",
    "$arr": "arrival",
    "$arrival": "arrival",
    "$dest": "arrival",
    "$destination": "arrival",
    "$origin": "departure",

    # Operator/Airline
    "$operator": "operator",
    "$airline": "operator",

    # Position
    "$lat": "latitude",
    "$latitude": "latitude",
    "$lon": "longitude",
    "$longitude": "longitude",
    "$alt": "altitude",
    "$altitude": "altitude",
    "$hdg": "heading",
    "$heading": "heading",

    # Speed
    "$spd": "ground_speed",
    "$speed": "ground_speed",
    "$gs": "ground_speed",
    "$groundspeed": "ground_speed",
    "$mach": "mach",

    # Flight plan
    "$route": "route",
    "$cruise_alt": "cruise_altitude",
    "$cruise_altitude": "cruise_altitude",
    "$cruise_spd": "cruise_speed",
    "$cruise_speed": "cruise_speed",
    "$remarks": "remarks",
    "$rules": "flight_rules",
    "$flight_rules": "flight_rules",

    # Airport operations
    "$gate": "parking_spot_name",
    "$parking": "parking_spot_name",
    "$spot": "parking_spot_name",
    "$runway": "arrival_runway",
    "$rwy": "arrival_runway",
    "$arrival_runway": "arrival_runway",

    # Advanced
    "$registration": "registration",
    "$tail": "registration",
    "$gufi": "gufi",
    "$wake": "wake_turbulence",
    "$engine": "engine_type",
    "$difficulty": "difficulty",
    "$fix": "fix",
    "$approach": "expected_approach",
}


def substitute_variables(command_template: str, aircraft: Aircraft) -> str:
    """
    Substitute variables in a command template with actual aircraft values.

    Variables use the format $variable_name (e.g., $aid, $type, $operator).
    If a variable's value is None or empty, it's replaced with "N/A".

    Args:
        command_template: Command string with variables (e.g., "SAYF THIS IS $aid")
        aircraft: Aircraft object to extract values from

    Returns:
        Command string with all variables replaced with actual values
    """
    result = command_template

    # Sort variables by length (longest first) to avoid partial replacements
    # This prevents $arr from matching inside $arrival
    sorted_variables = sorted(VARIABLE_MAP.items(), key=lambda x: len(x[0]), reverse=True)

    for variable, attribute in sorted_variables:
        if variable in result:
            # Get the attribute value from the aircraft
            value = getattr(aircraft, attribute, None)

            # Convert to string, handle None/empty values
            if value is None or value == "":
                value_str = "N/A"
            elif isinstance(value, float):
                # Format floats to reasonable precision
                value_str = f"{value:.2f}"
            else:
                value_str = str(value)

            # Replace the variable
            result = result.replace(variable, value_str)

    return result


def _expand_gate_range(range_str: str) -> List[str]:
    """
    Expand a gate range string into individual gate names

    Examples:
        "B1-B11" -> ["B1", "B2", "B3", ..., "B11"]
        "A10-A15" -> ["A10", "A11", "A12", "A13", "A14", "A15"]
        "C1-C3" -> ["C1", "C2", "C3"]

    Args:
        range_str: Range string in format "PREFIX#-PREFIX#"

    Returns:
        List of expanded gate names
    """
    # Match pattern like "B1-B11" or "A10-A15"
    match = re.match(r'^([A-Z]+)(\d+)-([A-Z]+)(\d+)$', range_str)

    if not match:
        return []

    prefix1, start_num, prefix2, end_num = match.groups()

    # Prefixes must match
    if prefix1 != prefix2:
        return []

    start = int(start_num)
    end = int(end_num)

    # Generate gate names
    gates = []
    for i in range(start, end + 1):
        gates.append(f"{prefix1}{i}")

    return gates


def _matches_parking_pattern(parking_spot: str, pattern: str) -> bool:
    """
    Check if a parking spot matches a pattern.

    Supports:
    - Exact match: "B3"
    - Range: "B1-B11"
    - Wildcard: "B#" (# matches any digits)

    Args:
        parking_spot: Parking spot name (e.g., "B3")
        pattern: Pattern to match against

    Returns:
        True if parking spot matches pattern
    """
    if not parking_spot:
        return False

    # Priority 1: Exact match
    if parking_spot == pattern:
        return True

    # Priority 2: Range match
    if '-' in pattern and '#' not in pattern:
        expanded_gates = _expand_gate_range(pattern)
        return parking_spot in expanded_gates

    # Priority 3: Wildcard match
    if '#' in pattern:
        prefix = pattern.replace('#', '')
        return parking_spot.startswith(prefix)

    return False


def matches_rule(aircraft: Aircraft, rule: PresetCommandRule) -> bool:
    """
    Check if an aircraft matches a preset command rule's grouping criteria.

    Args:
        aircraft: Aircraft to check
        rule: Preset command rule with group_type and group_value

    Returns:
        True if the aircraft matches the rule's criteria, False otherwise
    """
    if rule.group_type == "all":
        return True

    elif rule.group_type == "airline":
        # Match by operator/airline code
        return aircraft.operator and aircraft.operator.upper() == rule.group_value.upper()

    elif rule.group_type == "destination":
        # Match by arrival airport
        return aircraft.arrival and aircraft.arrival.upper() == rule.group_value.upper()

    elif rule.group_type == "origin":
        # Match by departure airport
        return aircraft.departure and aircraft.departure.upper() == rule.group_value.upper()

    elif rule.group_type == "aircraft_type":
        # Match by aircraft type (remove equipment suffix for comparison)
        aircraft_base_type = aircraft.aircraft_type.split('/')[0] if aircraft.aircraft_type else ""
        rule_base_type = rule.group_value.split('/')[0] if rule.group_value else ""
        return aircraft_base_type.upper() == rule_base_type.upper()

    elif rule.group_type == "departures":
        # Departures have parking spots
        return aircraft.parking_spot_name is not None and aircraft.parking_spot_name != ""

    elif rule.group_type == "arrivals":
        # Arrivals don't have parking spots
        return aircraft.parking_spot_name is None or aircraft.parking_spot_name == ""

    elif rule.group_type == "parking":
        # Match by parking spot pattern (exact, range, or wildcard)
        return _matches_parking_pattern(aircraft.parking_spot_name, rule.group_value)

    elif rule.group_type == "random":
        # Random matching handled separately in apply_preset_commands
        return False

    return False


def apply_preset_commands(aircraft_list: List[Aircraft], command_rules: List[PresetCommandRule]) -> None:
    """
    Apply preset commands to aircraft based on rules.

    Commands are applied cumulatively (aircraft can receive multiple commands).
    Rules are sorted by specificity (general → specific) before application.

    Special handling for 'random' group_type:
    - Randomly selects N aircraft (where N = group_value) and applies command to them
    - Random selection is independent for each random rule

    Args:
        aircraft_list: List of Aircraft objects to apply commands to
        command_rules: List of PresetCommandRule objects defining which commands to apply

    Side effects:
        Modifies aircraft.preset_commands for matching aircraft
    """
    if not command_rules:
        return

    # Sort rules by specificity (general commands applied first)
    sorted_rules = sorted(command_rules, key=lambda r: r.get_specificity_score())

    for rule in sorted_rules:
        if rule.group_type == "random":
            # Special handling for random selection
            try:
                count = int(rule.group_value)
                # Randomly select N aircraft
                if count > 0 and count <= len(aircraft_list):
                    selected_aircraft = random.sample(aircraft_list, count)
                    for aircraft in selected_aircraft:
                        command = substitute_variables(rule.command_template, aircraft)
                        aircraft.preset_commands.append(command)
            except (ValueError, TypeError):
                # Invalid count value, skip this rule
                continue
        else:
            # Normal matching for other group types
            for aircraft in aircraft_list:
                if matches_rule(aircraft, rule):
                    command = substitute_variables(rule.command_template, aircraft)
                    aircraft.preset_commands.append(command)


def get_available_variables() -> List[str]:
    """
    Get a list of all available variable names for display in the GUI.

    Returns:
        List of variable names sorted alphabetically
    """
    # Get unique variable names (remove duplicates like $aid and $callsign)
    unique_vars = sorted(set(VARIABLE_MAP.keys()))
    return unique_vars


def get_variable_description(variable: str) -> str:
    """
    Get a human-readable description of what a variable represents.

    Args:
        variable: Variable name (e.g., "$aid")

    Returns:
        Description string
    """
    descriptions = {
        "$aid": "Aircraft ID / Callsign",
        "$callsign": "Aircraft Callsign",
        "$type": "Aircraft Type",
        "$actype": "Aircraft Type",
        "$dep": "Departure Airport",
        "$departure": "Departure Airport",
        "$arr": "Arrival Airport",
        "$arrival": "Arrival Airport",
        "$dest": "Destination Airport",
        "$destination": "Destination Airport",
        "$origin": "Origin Airport",
        "$operator": "Airline / Operator Code",
        "$airline": "Airline Code",
        "$lat": "Latitude",
        "$latitude": "Latitude",
        "$lon": "Longitude",
        "$longitude": "Longitude",
        "$alt": "Altitude",
        "$altitude": "Altitude",
        "$hdg": "Heading",
        "$heading": "Heading",
        "$spd": "Ground Speed",
        "$speed": "Ground Speed",
        "$gs": "Ground Speed",
        "$groundspeed": "Ground Speed",
        "$mach": "Mach Number",
        "$route": "Flight Route",
        "$cruise_alt": "Cruise Altitude",
        "$cruise_altitude": "Cruise Altitude",
        "$cruise_spd": "Cruise Speed",
        "$cruise_speed": "Cruise Speed",
        "$remarks": "Flight Plan Remarks",
        "$rules": "Flight Rules (I/V)",
        "$flight_rules": "Flight Rules",
        "$gate": "Gate / Parking Spot",
        "$parking": "Parking Spot Name",
        "$spot": "Parking Spot",
        "$runway": "Arrival Runway",
        "$rwy": "Runway",
        "$arrival_runway": "Arrival Runway",
        "$registration": "Aircraft Registration",
        "$tail": "Tail Number",
        "$gufi": "Global Unique Flight ID",
        "$wake": "Wake Turbulence Category",
        "$engine": "Engine Type",
        "$difficulty": "Difficulty Level",
        "$fix": "Fix / Waypoint",
        "$approach": "Expected Approach",
    }
    return descriptions.get(variable, variable)
