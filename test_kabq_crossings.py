"""Test script to verify crossing detection for KABQ runways"""

import sys
import logging
from parsers.geojson_parser import GeoJSONParser

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_kabq_crossings():
    """Test that KABQ runways 3, 8, 12 are properly grouped"""

    print("="*80)
    print("TESTING KABQ RUNWAY CROSSING DETECTION")
    print("="*80)
    print()

    # Load KABQ GeoJSON
    geojson_path = r"C:\Users\flyma\Desktop\Creative Shrimp\Sweatbox Scenario Generator (SSG)\airport_data\ABQ.geojson"
    parser = GeoJSONParser(geojson_path, "KABQ")

    print(f"Loaded {len(parser.runways)} runways from KABQ GeoJSON")
    print()

    # List all runway ends
    print("Runway Ends:")
    for runway in parser.runways:
        ends = runway.get_runway_ends()
        print(f"  Runway: {runway.name} -> Ends: {ends}")
    print()

    # Get parallel runway info
    print("-" * 80)
    print("PARALLEL RUNWAY DETECTION:")
    print("-" * 80)
    parallel_info = parser.get_parallel_runway_info()
    if parallel_info:
        for runway_end, data in parallel_info.items():
            print(f"  {runway_end}: parallels = {data.get('parallels', [])}")
    else:
        print("  No parallel runways detected")
    print()

    # Get crossing/converging runway info
    print("-" * 80)
    print("CROSSING/CONVERGING RUNWAY DETECTION:")
    print("-" * 80)
    from utils.runway_utils import identify_crossing_converging_runways
    crossing_map = identify_crossing_converging_runways(parser.runways)
    if crossing_map:
        for runway_end, crossings in crossing_map.items():
            print(f"  {runway_end}: crosses/converges with {crossings}")
    else:
        print("  No crossing/converging runways detected")
    print()

    # Get runway groups
    print("-" * 80)
    print("RUNWAY GROUPING:")
    print("-" * 80)
    runway_groups = parser.get_runway_groups()

    # Organize by group
    groups = {}
    for runway_end, group_id in runway_groups.items():
        if group_id not in groups:
            groups[group_id] = []
        groups[group_id].append(runway_end)

    for group_id, members in sorted(groups.items()):
        print(f"  Group {group_id}: {sorted(members)}")
    print()

    # Verify expected grouping
    print("-" * 80)
    print("VERIFICATION:")
    print("-" * 80)

    # Check if 3, 8, 12 are in the same group
    runways_to_check = ['3', '8', '12']
    group_ids = [runway_groups.get(rwy) for rwy in runways_to_check]

    print(f"Runway 3 group: {runway_groups.get('3')}")
    print(f"Runway 8 group: {runway_groups.get('8')}")
    print(f"Runway 12 group: {runway_groups.get('12')}")
    print()

    if all(gid == group_ids[0] for gid in group_ids if gid is not None):
        print("[SUCCESS] Runways 3, 8, and 12 are all in the same group!")
        print(f"  They share Group {group_ids[0]} and will use the same distance counter")
    else:
        print("[FAILURE] Runways 3, 8, and 12 are NOT all in the same group!")
        print("  Expected: All three in same group due to:")
        print("    - Runway 3 physically crosses runway 12")
        print("    - Runway 12 extended centerline crosses runway 8")
        print("    - Transitive closure should group all three together")

    print()
    print("="*80)

if __name__ == "__main__":
    test_kabq_crossings()
