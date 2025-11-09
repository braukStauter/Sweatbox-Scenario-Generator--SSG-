"""
Test script for preset commands feature
"""

from models.preset_command import PresetCommandRule
from models.aircraft import Aircraft
from utils.preset_command_processor import (
    substitute_variables,
    matches_rule,
    apply_preset_commands
)


def test_preset_command_rule_validation():
    """Test PresetCommandRule validation"""
    print("\n=== Testing PresetCommandRule Validation ===")

    # Valid rules
    try:
        rule1 = PresetCommandRule("all", None, "HD270")
        print("[PASS] Valid rule (all aircraft)")
    except Exception as e:
        print(f"[FAIL] Valid rule (all aircraft): {e}")

    try:
        rule2 = PresetCommandRule("airline", "AAL", "SAYF THIS IS $aid")
        print("[PASS] Valid rule (airline filter): PASSED")
    except Exception as e:
        print(f"[FAIL] Valid rule (airline filter): FAILED - {e}")

    # Invalid rule - missing group_value
    try:
        rule3 = PresetCommandRule("airline", None, "HD270")
        print("[FAIL] Invalid rule (missing value): FAILED - Should have raised ValueError")
    except ValueError:
        print("[PASS] Invalid rule (missing value): PASSED - Correctly rejected")

    # Invalid rule - empty command
    try:
        rule4 = PresetCommandRule("all", None, "")
        print("[FAIL] Invalid rule (empty command): FAILED - Should have raised ValueError")
    except ValueError:
        print("[PASS] Invalid rule (empty command): PASSED - Correctly rejected")


def test_variable_substitution():
    """Test variable substitution"""
    print("\n=== Testing Variable Substitution ===")

    # Create a test aircraft
    aircraft = Aircraft(
        callsign="AAL123",
        aircraft_type="B738/L",
        latitude=40.6413,
        longitude=-73.7781,
        altitude=5000,
        heading=270,
        ground_speed=250,
        departure="KJFK",
        arrival="KLAX",
        route="DCT",
        cruise_altitude="35000",
        cruise_speed=450,
        remarks="",
        flight_rules="I"
    )
    aircraft.operator = "AAL"
    aircraft.altitude = 5000
    aircraft.heading = 270
    aircraft.ground_speed = 250
    aircraft.parking_spot_name = "B3"
    aircraft.arrival_runway = "25L"

    # Test various substitutions
    tests = [
        ("SAYF THIS IS $aid", "SAYF THIS IS AAL123"),
        ("HD$hdg", "HD270"),
        ("CAAA$aid", "CAAAAAL123"),  # CAAA + AAL123 = CAAAAAL123
        ("$type TO $arrival", "B738/L TO KLAX"),
        ("$operator FLIGHT AT GATE $gate", "AAL FLIGHT AT GATE B3"),
        ("CLEARED $arrival RUNWAY $runway", "CLEARED KLAX RUNWAY 25L"),
    ]

    for template, expected in tests:
        result = substitute_variables(template, aircraft)
        if result == expected:
            print(f"[PASS] '{template}' -> '{result}': PASSED")
        else:
            print(f"[FAIL] '{template}' -> '{result}' (expected '{expected}'): FAILED")

    # Test missing variable substitution
    aircraft2 = Aircraft(
        callsign="N123AB",
        aircraft_type="C172/G",
        latitude=40.6413,
        longitude=-73.7781,
        altitude=3500,
        heading=90,
        ground_speed=120,
        departure="KJFK",
        arrival="KLAX",
        route="DCT",
        cruise_altitude="3500",
        cruise_speed=120,
        remarks="",
        flight_rules="V"
    )
    # No parking spot (arrival aircraft)
    result = substitute_variables("GATE $gate", aircraft2)
    if "N/A" in result:
        print(f"[PASS] Missing variable substitution: '{result}' contains 'N/A': PASSED")
    else:
        print(f"[FAIL] Missing variable substitution: '{result}': FAILED")


def test_aircraft_matching():
    """Test aircraft matching to rules"""
    print("\n=== Testing Aircraft Matching ===")

    # Create test aircraft
    aal_departure = Aircraft(
        callsign="AAL123",
        aircraft_type="B738/L",
        latitude=40.6413,
        longitude=-73.7781,
        altitude=0,
        heading=270,
        ground_speed=0,
        departure="KJFK",
        arrival="KLAX",
        route="DCT",
        cruise_altitude="35000",
        cruise_speed=450,
        remarks="",
        flight_rules="I"
    )
    aal_departure.operator = "AAL"
    aal_departure.parking_spot_name = "B3"

    dal_arrival = Aircraft(
        callsign="DAL456",
        aircraft_type="A320/L",
        latitude=40.6413,
        longitude=-73.7781,
        altitude=5000,
        heading=90,
        ground_speed=250,
        departure="KORD",
        arrival="KJFK",
        route="DCT",
        cruise_altitude="33000",
        cruise_speed=440,
        remarks="",
        flight_rules="I"
    )
    dal_arrival.operator = "DAL"
    # No parking spot (arrival)

    # Test matching
    tests = [
        (PresetCommandRule("all", None, "TEST"), aal_departure, True, "all aircraft"),
        (PresetCommandRule("airline", "AAL", "TEST"), aal_departure, True, "airline AAL match"),
        (PresetCommandRule("airline", "DAL", "TEST"), aal_departure, False, "airline DAL no match"),
        (PresetCommandRule("destination", "KLAX", "TEST"), aal_departure, True, "destination KLAX match"),
        (PresetCommandRule("destination", "KJFK", "TEST"), aal_departure, False, "destination KJFK no match"),
        (PresetCommandRule("aircraft_type", "B738", "TEST"), aal_departure, True, "aircraft type match"),
        (PresetCommandRule("departures", None, "TEST"), aal_departure, True, "departures match"),
        (PresetCommandRule("arrivals", None, "TEST"), aal_departure, False, "arrivals no match (is departure)"),
        (PresetCommandRule("departures", None, "TEST"), dal_arrival, False, "departures no match (is arrival)"),
        (PresetCommandRule("arrivals", None, "TEST"), dal_arrival, True, "arrivals match"),
    ]

    for rule, aircraft, expected, description in tests:
        result = matches_rule(aircraft, rule)
        if result == expected:
            print(f"[PASS] {description}: PASSED")
        else:
            print(f"[FAIL] {description}: FAILED (got {result}, expected {expected})")


def test_apply_preset_commands():
    """Test applying preset commands to aircraft list"""
    print("\n=== Testing Apply Preset Commands ===")

    # Create test aircraft
    aircraft_list = []

    # AAL departures
    for i in range(3):
        ac = Aircraft(
            callsign=f"AAL{100+i}",
            aircraft_type="B738/L",
            latitude=40.6413,
            longitude=-73.7781,
            altitude=0,
            heading=270,
            ground_speed=0,
            departure="KJFK",
            arrival="KLAX",
            route="DCT",
            cruise_altitude="35000",
            cruise_speed=450,
            remarks="",
            flight_rules="I"
        )
        ac.operator = "AAL"
        ac.parking_spot_name = f"B{i+1}"
        aircraft_list.append(ac)

    # DAL arrivals
    for i in range(2):
        ac = Aircraft(
            callsign=f"DAL{200+i}",
            aircraft_type="A320/L",
            latitude=40.6413,
            longitude=-73.7781,
            altitude=5000,
            heading=90,
            ground_speed=250,
            departure="KORD",
            arrival="KJFK",
            route="DCT",
            cruise_altitude="33000",
            cruise_speed=440,
            remarks="",
            flight_rules="I"
        )
        ac.operator = "DAL"
        # No parking spot (arrivals)
        aircraft_list.append(ac)

    # Create rules
    rules = [
        PresetCommandRule("all", None, "CMD_ALL"),
        PresetCommandRule("airline", "AAL", "CMD_AAL_$aid"),
        PresetCommandRule("departures", None, "CMD_DEP"),
        PresetCommandRule("arrivals", None, "CMD_ARR"),
        PresetCommandRule("random", "2", "CMD_RANDOM"),
    ]

    # Apply commands
    apply_preset_commands(aircraft_list, rules)

    # Verify results
    print("\nAircraft preset commands:")
    for ac in aircraft_list:
        print(f"{ac.callsign}: {ac.preset_commands}")

    # Check specific conditions
    aal_aircraft = [ac for ac in aircraft_list if ac.operator == "AAL"]
    dal_aircraft = [ac for ac in aircraft_list if ac.operator == "DAL"]

    # All aircraft should have CMD_ALL
    if all("CMD_ALL" in ac.preset_commands for ac in aircraft_list):
        print("[PASS] All aircraft have CMD_ALL: PASSED")
    else:
        print("[FAIL] All aircraft should have CMD_ALL: FAILED")

    # AAL aircraft should have CMD_AAL with callsign substitution
    aal_checks = [f"CMD_AAL_{ac.callsign}" in ac.preset_commands for ac in aal_aircraft]
    if all(aal_checks):
        print("[PASS] AAL aircraft have CMD_AAL_<callsign>: PASSED")
    else:
        print("[FAIL] AAL aircraft should have CMD_AAL_<callsign>: FAILED")

    # AAL departures should have both CMD_DEP and CMD_AAL
    if all("CMD_DEP" in ac.preset_commands for ac in aal_aircraft):
        print("[PASS] AAL departures have CMD_DEP: PASSED")
    else:
        print("[FAIL] AAL departures should have CMD_DEP: FAILED")

    # DAL arrivals should have CMD_ARR
    if all("CMD_ARR" in ac.preset_commands for ac in dal_aircraft):
        print("[PASS] DAL arrivals have CMD_ARR: PASSED")
    else:
        print("[FAIL] DAL arrivals should have CMD_ARR: FAILED")

    # Exactly 2 aircraft should have CMD_RANDOM
    random_count = sum(1 for ac in aircraft_list if "CMD_RANDOM" in ac.preset_commands)
    if random_count == 2:
        print(f"[PASS] Exactly 2 aircraft have CMD_RANDOM: PASSED")
    else:
        print(f"[FAIL] Expected 2 aircraft with CMD_RANDOM, got {random_count}: FAILED")

    # Check cumulative (AAL departures should have 4 commands: ALL, AAL, DEP, and possibly RANDOM)
    aal_command_counts = [len(ac.preset_commands) for ac in aal_aircraft]
    if all(count >= 3 for count in aal_command_counts):
        print(f"[PASS] AAL departures have at least 3 commands (cumulative): PASSED")
    else:
        print(f"[FAIL] AAL departures should have at least 3 commands: FAILED")


if __name__ == "__main__":
    print("=" * 70)
    print("PRESET COMMANDS FEATURE TEST SUITE")
    print("=" * 70)

    test_preset_command_rule_validation()
    test_variable_substitution()
    test_aircraft_matching()
    test_apply_preset_commands()

    print("\n" + "=" * 70)
    print("TEST SUITE COMPLETE")
    print("=" * 70)
