#!/usr/bin/env python
"""
Test script for verifying SID/STAR route-based matching
"""

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

from models.aircraft import Aircraft
from models.preset_command import PresetCommandRule
from utils.preset_command_processor import apply_preset_commands

def test_route_matching():
    """Test that SID/STAR matching works by searching routes"""
    print("\n" + "="*60)
    print("Testing SID/STAR Route-Based Matching")
    print("="*60)

    # Create test aircraft with SID/STAR in routes (real format)
    aircraft_list = [
        # Departures with SIDs in route
        Aircraft(
            callsign="UAL123",
            aircraft_type="B738",
            latitude=39.8617,
            longitude=-104.6732,
            altitude=5400,
            heading=270,
            ground_speed=0,
            departure="KDEN",
            arrival="KLAX",
            route="KDEN.BAYLR6.TEHRU..TOADD.Q78.MARUE.DSNEE6.KLGB",
            parking_spot_name="B3"
        ),
        Aircraft(
            callsign="AAL456",
            aircraft_type="A320",
            latitude=39.8617,
            longitude=-104.6732,
            altitude=5400,
            heading=90,
            ground_speed=0,
            departure="KDEN",
            arrival="KIAH",
            route="KDEN.SLEEK2.SLEEK..NOSEW..MQP.DRLLR5.KIAH",
            parking_spot_name="C5"
        ),
        # Arrivals with STARs in route
        Aircraft(
            callsign="DAL789",
            aircraft_type="B757",
            latitude=39.8617,
            longitude=-104.6732,
            altitude=12000,
            heading=180,
            ground_speed=250,
            departure="KORD",
            arrival="KDEN",
            route="KORD..HALEN.NIIXX4.KDEN",
            parking_spot_name=None
        ),
        Aircraft(
            callsign="SWA101",
            aircraft_type="B737",
            latitude=39.8617,
            longitude=-104.6732,
            altitude=15000,
            heading=90,
            ground_speed=280,
            departure="KLAX",
            arrival="KDEN",
            route="KLAX..BRWRY.LAWGR4.KDEN",
            parking_spot_name=None
        ),
        # Aircraft without SID/STAR
        Aircraft(
            callsign="N12345",
            aircraft_type="C172",
            latitude=39.8617,
            longitude=-104.6732,
            altitude=5400,
            heading=360,
            ground_speed=0,
            departure="KDEN",
            arrival="KBJC",
            route="KDEN..DCT..KBJC",
            parking_spot_name="GA1"
        )
    ]

    # Create test rules matching SIDs/STARs (with exact format including numbers)
    rules = [
        # SID-based rules (with numbers as they appear in routes)
        PresetCommandRule(
            group_type="sid",
            group_value="BAYLR6",
            command_template="SAYF $aid using BAYLR6 departure"
        ),
        PresetCommandRule(
            group_type="sid",
            group_value="SLEEK2",
            command_template="SAYF $aid using SLEEK2 departure"
        ),
        # STAR-based rules (with numbers as they appear in routes)
        PresetCommandRule(
            group_type="star",
            group_value="NIIXX4",
            command_template="SAYF $aid arriving via NIIXX4"
        ),
        PresetCommandRule(
            group_type="star",
            group_value="LAWGR4",
            command_template="SAYF $aid arriving via LAWGR4"
        ),
        # General rules
        PresetCommandRule(
            group_type="departures",
            group_value=None,
            command_template="SAYF $aid is a departure"
        ),
        PresetCommandRule(
            group_type="arrivals",
            group_value=None,
            command_template="SAYF $aid is an arrival"
        )
    ]

    # Print initial state
    print("\nAircraft Before Command Application:")
    print("-" * 60)
    for ac in aircraft_list:
        route_short = ac.route[:50] + "..." if len(ac.route) > 50 else ac.route
        print(f"{ac.callsign:8} Route: {route_short}")

    # Apply preset commands
    print("\nApplying Preset Commands...")
    apply_preset_commands(aircraft_list, rules)

    # Print results
    print("\nAircraft After Command Application:")
    print("-" * 60)
    for ac in aircraft_list:
        print(f"\n{ac.callsign}:")
        route_short = ac.route[:60] + "..." if len(ac.route) > 60 else ac.route
        print(f"  Route: {route_short}")
        print(f"  Commands ({len(ac.preset_commands)}):")
        for cmd in ac.preset_commands:
            print(f"    - {cmd}")

    # Verify results
    print("\n" + "="*60)
    print("VERIFICATION:")
    print("-" * 60)

    expected_commands = {
        "UAL123": ["SAYF UAL123 is a departure", "SAYF UAL123 using BAYLR6 departure"],
        "AAL456": ["SAYF AAL456 is a departure", "SAYF AAL456 using SLEEK2 departure"],
        "DAL789": ["SAYF DAL789 is an arrival", "SAYF DAL789 arriving via NIIXX4"],
        "SWA101": ["SAYF SWA101 is an arrival", "SAYF SWA101 arriving via LAWGR4"],
        "N12345": ["SAYF N12345 is a departure"]
    }

    all_passed = True
    for ac in aircraft_list:
        expected = expected_commands.get(ac.callsign, [])
        actual = ac.preset_commands

        if set(actual) == set(expected):
            print(f"[PASS] {ac.callsign}: Commands matched expected")
        else:
            print(f"[FAIL] {ac.callsign}: Commands did not match")
            print(f"  Expected: {expected}")
            print(f"  Got: {actual}")
            all_passed = False

    print("\n" + "="*60)
    if all_passed:
        print("SUCCESS: All tests passed!")
    else:
        print("FAILURE: Some tests failed. Check the output above.")
    print("="*60)


if __name__ == "__main__":
    test_route_matching()
