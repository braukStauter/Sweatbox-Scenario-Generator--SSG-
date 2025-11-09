"""Test script to verify threshold offset calculations for parallel runway separation"""

import math
from utils.runway_utils import calculate_diagonal_separation

# Test case from the user's issue:
# Runway 8 at 6.0 NM, Runway 7R at 7.3 NM
# Centerline spacing: 0.733 NM
# Expected: ~1.49 NM without offset, ~1.12 NM with offset

def test_diagonal_separation():
    """Test diagonal separation with and without threshold offset"""

    # Test without threshold offset
    runway1_distance = 6.0  # Runway 8
    runway2_distance = 7.3  # Runway 7R
    centerline_spacing = 0.733

    diagonal_no_offset = calculate_diagonal_separation(
        runway1_distance,
        runway2_distance,
        centerline_spacing,
        threshold_offset=0.0
    )

    print(f"Test Case 1: No threshold offset")
    print(f"  Runway 8: {runway1_distance} NM")
    print(f"  Runway 7R: {runway2_distance} NM")
    print(f"  Centerline spacing: {centerline_spacing} NM")
    print(f"  Diagonal separation: {diagonal_no_offset:.2f} NM")
    print(f"  Expected: ~1.49 NM")
    print()

    # Test with threshold offset (7R threshold ahead by ~0.45 NM)
    threshold_offset = 0.45

    diagonal_with_offset = calculate_diagonal_separation(
        runway1_distance,
        runway2_distance,
        centerline_spacing,
        threshold_offset=threshold_offset
    )

    print(f"Test Case 2: With threshold offset")
    print(f"  Runway 8: {runway1_distance} NM")
    print(f"  Runway 7R: {runway2_distance} NM (threshold {threshold_offset} NM ahead)")
    print(f"  Adjusted 7R position: {runway2_distance - threshold_offset:.1f} NM")
    print(f"  Centerline spacing: {centerline_spacing} NM")
    print(f"  Diagonal separation: {diagonal_with_offset:.2f} NM")
    print(f"  Expected: ~1.12 NM (radar measurement)")
    print()

    # Verify the math
    adjusted_runway2 = runway2_distance - threshold_offset
    along_track = abs(runway1_distance - adjusted_runway2)
    diagonal_manual = math.sqrt(along_track**2 + centerline_spacing**2)

    print(f"Verification:")
    print(f"  Along-track separation: |{runway1_distance} - {adjusted_runway2:.1f}| = {along_track:.2f} NM")
    print(f"  Diagonal = sqrt({along_track:.2f}^2 + {centerline_spacing}^2) = {diagonal_manual:.2f} NM")
    print()

    # Test required separation
    required_sep = 1.5  # For runways 0.733 NM apart
    if diagonal_with_offset < required_sep:
        print(f"VIOLATION: Diagonal {diagonal_with_offset:.2f} NM < Required {required_sep} NM")

        # Calculate how much we need to adjust
        # We need: sqrt(along_track^2 + centerline^2) >= 1.5
        # So: along_track >= sqrt(1.5^2 - 0.733^2) = sqrt(2.25 - 0.537) = sqrt(1.713) = 1.31 NM
        min_along_track = math.sqrt(required_sep**2 - centerline_spacing**2)
        print(f"  Minimum along-track needed: {min_along_track:.2f} NM")
        print(f"  Current along-track: {along_track:.2f} NM")
        print(f"  Need to increase by: {min_along_track - along_track:.2f} NM")
    else:
        print(f"OK: Diagonal {diagonal_with_offset:.2f} NM >= Required {required_sep} NM")

if __name__ == "__main__":
    test_diagonal_separation()