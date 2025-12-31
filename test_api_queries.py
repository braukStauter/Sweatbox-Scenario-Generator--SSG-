"""
Test script to verify API queries are returning expected results
"""
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from utils.api_client import FlightDataAPIClient


def test_api_queries():
    """Test all API query methods"""
    client = FlightDataAPIClient(cache_timeout=60)
    all_passed = True

    print("=" * 60)
    print("SSG API Query Test Suite")
    print(f"API URL: {client.BASE_URL}")
    print("=" * 60)

    # Test 1: fetch_flights with limit and offset (returns dict with pagination)
    print("\n[Test 1] fetch_flights (KDFW departures, limit=5)")
    try:
        result = client.fetch_flights(departure="KDFW", limit=5)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, dict):
            print(f"  [FAIL] Expected dict, got {type(result)}")
            all_passed = False
        elif 'flights' not in result:
            print(f"  [FAIL] Missing 'flights' key. Keys: {result.keys()}")
            all_passed = False
        elif 'pagination' not in result:
            print(f"  [FAIL] Missing 'pagination' key. Keys: {result.keys()}")
            all_passed = False
        else:
            flights = result['flights']
            pagination = result['pagination']
            print(f"  [PASS] Got {len(flights)} flights")
            print(f"    Pagination: offset={pagination.get('offset')}, hasMore={pagination.get('hasMore')}")
            if flights:
                f = flights[0]
                print(f"    Sample: {f.get('aircraftIdentification')} ({f.get('aircraftType')}) - Status: {f.get('flightStatus')}")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 2: fetch_flights with offset (pagination)
    print("\n[Test 2] fetch_flights with offset (KDFW departures, limit=3, offset=3)")
    try:
        result = client.fetch_flights(departure="KDFW", limit=3, offset=3)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, dict):
            print(f"  [FAIL] Expected dict, got {type(result)}")
            all_passed = False
        else:
            flights = result['flights']
            pagination = result['pagination']
            print(f"  [PASS] Got {len(flights)} flights with offset")
            print(f"    Pagination: offset={pagination.get('offset')}, hasMore={pagination.get('hasMore')}")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 3: fetch_departures (backwards-compatible, returns list)
    print("\n[Test 3] fetch_departures (KPHX, limit=5)")
    try:
        result = client.fetch_departures("KPHX", limit=5)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, list):
            print(f"  [FAIL] Expected list, got {type(result)}")
            all_passed = False
        else:
            print(f"  [PASS] Got {len(result)} flights (list)")
            if result:
                f = result[0]
                print(f"    Sample: {f.get('aircraftIdentification')} - {f.get('departure')} -> {f.get('arrival')}")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 4: fetch_arrivals (backwards-compatible, returns list)
    print("\n[Test 4] fetch_arrivals (KLAX, limit=5)")
    try:
        result = client.fetch_arrivals("KLAX", limit=5)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, list):
            print(f"  [FAIL] Expected list, got {type(result)}")
            all_passed = False
        else:
            print(f"  [PASS] Got {len(result)} flights (list)")
            if result:
                f = result[0]
                print(f"    Sample: {f.get('aircraftIdentification')} - {f.get('departure')} -> {f.get('arrival')}")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 5: fetch_artcc_flights (returns dict with pagination)
    print("\n[Test 5] fetch_artcc_flights (ZLA, limit=10)")
    try:
        result = client.fetch_artcc_flights("ZLA", limit=10)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, dict):
            print(f"  [FAIL] Expected dict, got {type(result)}")
            all_passed = False
        elif 'flights' not in result:
            print(f"  [FAIL] Missing 'flights' key. Keys: {result.keys()}")
            all_passed = False
        elif 'pagination' not in result:
            print(f"  [FAIL] Missing 'pagination' key. Keys: {result.keys()}")
            all_passed = False
        else:
            flights = result['flights']
            pagination = result['pagination']
            print(f"  [PASS] Got {len(flights)} flights")
            print(f"    Pagination: offset={pagination.get('offset')}, hasMore={pagination.get('hasMore')}")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 6: fetch_all_flights (pagination helper, returns list)
    print("\n[Test 6] fetch_all_flights (KORD arrivals, max=15, page_size=5)")
    try:
        result = client.fetch_all_flights(arrival="KORD", max_flights=15, page_size=5)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, list):
            print(f"  [FAIL] Expected list, got {type(result)}")
            all_passed = False
        else:
            print(f"  [PASS] Got {len(result)} flights via pagination")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 7: Verify all flights are PROPOSED status
    print("\n[Test 7] Verify API returns only PROPOSED flights")
    try:
        result = client.fetch_flights(departure="KATL", limit=20)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        else:
            flights = result.get('flights', [])
            status_counts = {}
            for f in flights:
                status = f.get('flightStatus', 'UNKNOWN')
                status_counts[status] = status_counts.get(status, 0) + 1

            if not flights:
                print("  [WARN] No flights returned to check status")
            elif status_counts.get('PROPOSED', 0) == len(flights):
                print(f"  [PASS] All {len(flights)} flights are PROPOSED")
            else:
                print(f"  [FAIL] Status distribution: {status_counts}")
                all_passed = False
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 8: Verify limit parameter is respected by server
    print("\n[Test 8] Verify server-side limit (request 3, expect <=3)")
    try:
        # Clear cache to ensure fresh request
        client.clear_cache()
        result = client.fetch_flights(departure="KJFK", limit=3)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        else:
            flights = result.get('flights', [])
            if len(flights) <= 3:
                print(f"  [PASS] Requested 3, got {len(flights)}")
            else:
                print(f"  [FAIL] Requested 3, got {len(flights)} (limit not respected)")
                all_passed = False
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 9: fetch_departures with SID filtering
    print("\n[Test 9] fetch_departures with SID filter (KDFW, SIDs: AKUNA, TERRY)")
    try:
        client.clear_cache()
        result = client.fetch_departures("KDFW", limit=20, sids=["AKUNA5", "TERRY6"])
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, list):
            print(f"  [FAIL] Expected list, got {type(result)}")
            all_passed = False
        else:
            print(f"  [PASS] Got {len(result)} flights with SID filter")
            # Check if routes contain the requested SIDs
            sid_matches = 0
            for f in result[:5]:
                route = f.get('route', '')
                if 'AKUNA' in route.upper() or 'TERRY' in route.upper():
                    sid_matches += 1
            if result:
                print(f"    Routes with AKUNA/TERRY in first 5: {sid_matches}")
                if result:
                    print(f"    Sample route: {result[0].get('route', 'N/A')[:60]}...")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 10: fetch_arrivals with STAR filtering
    print("\n[Test 10] fetch_arrivals with STAR filter (KPHX, STARs: EAGUL, KOOLY)")
    try:
        client.clear_cache()
        result = client.fetch_arrivals("KPHX", limit=20, stars=["EAGUL6", "KOOLY2"])
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        elif not isinstance(result, list):
            print(f"  [FAIL] Expected list, got {type(result)}")
            all_passed = False
        else:
            print(f"  [PASS] Got {len(result)} flights with STAR filter")
            # Check if routes contain the requested STARs
            star_matches = 0
            for f in result[:5]:
                route = f.get('route', '')
                if 'EAGUL' in route.upper() or 'KOOLY' in route.upper():
                    star_matches += 1
            if result:
                print(f"    Routes with EAGUL/KOOLY in first 5: {star_matches}")
                if result:
                    print(f"    Sample route: {result[0].get('route', 'N/A')[:60]}...")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 11: fetch_flights with raw depproc parameter
    print("\n[Test 11] fetch_flights with depproc filter (KLAS departures, depproc=BOACH+COWBY)")
    try:
        client.clear_cache()
        # Use the _format_procedures_for_api method to format properly
        depproc = client._format_procedures_for_api(["BOACH1", "COWBY8"])
        result = client.fetch_flights(departure="KLAS", limit=15, depproc=depproc)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        else:
            flights = result.get('flights', [])
            print(f"  [PASS] Got {len(flights)} flights with depproc filter")
            print(f"    depproc param sent: {depproc}")
            # Check routes
            proc_matches = 0
            for f in flights[:5]:
                route = f.get('route', '')
                if 'BOACH' in route.upper() or 'COWBY' in route.upper():
                    proc_matches += 1
            if flights:
                print(f"    Routes with BOACH/COWBY in first 5: {proc_matches}")
                print(f"    Sample route: {flights[0].get('route', 'N/A')[:60]}...")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 12: fetch_flights with raw arrproc parameter
    print("\n[Test 12] fetch_flights with arrproc filter (KLAX arrivals, arrproc=SEAVU+IRNMN)")
    try:
        client.clear_cache()
        arrproc = client._format_procedures_for_api(["SEAVU5", "IRNMN2"])
        result = client.fetch_flights(arrival="KLAX", limit=15, arrproc=arrproc)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        else:
            flights = result.get('flights', [])
            print(f"  [PASS] Got {len(flights)} flights with arrproc filter")
            print(f"    arrproc param sent: {arrproc}")
            # Check routes
            proc_matches = 0
            for f in flights[:5]:
                route = f.get('route', '')
                if 'SEAVU' in route.upper() or 'IRNMN' in route.upper():
                    proc_matches += 1
            if flights:
                print(f"    Routes with SEAVU/IRNMN in first 5: {proc_matches}")
                print(f"    Sample route: {flights[0].get('route', 'N/A')[:60]}...")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 13: Compare filtered vs unfiltered counts
    print("\n[Test 13] Compare filtered vs unfiltered (KDEN arrivals)")
    try:
        client.clear_cache()
        # Unfiltered
        unfiltered = client.fetch_arrivals("KDEN", limit=50)
        # Filtered by specific STAR
        filtered = client.fetch_arrivals("KDEN", limit=50, stars=["FLATI3"])

        if unfiltered is None or filtered is None:
            print("  [FAIL] One or both results are None")
            all_passed = False
        else:
            print(f"  [PASS] Comparison complete")
            print(f"    Unfiltered: {len(unfiltered)} flights")
            print(f"    Filtered (FLATI STAR): {len(filtered)} flights")
            # Check that filtered has FLATI in routes
            flati_count = sum(1 for f in filtered if 'FLATI' in f.get('route', '').upper())
            print(f"    Filtered flights with FLATI in route: {flati_count}/{len(filtered)}")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Test 14: ARTCC query (enroute scenario style)
    print("\n[Test 14] ARTCC enroute query (ZAB, limit=20)")
    try:
        client.clear_cache()
        result = client.fetch_artcc_flights("ZAB", limit=20)
        if result is None:
            print("  [FAIL] Result is None")
            all_passed = False
        else:
            flights = result.get('flights', [])
            pagination = result.get('pagination', {})
            print(f"  [PASS] Got {len(flights)} enroute flights")
            print(f"    Pagination: offset={pagination.get('offset')}, hasMore={pagination.get('hasMore')}")
            # Show sample flight details
            if flights:
                f = flights[0]
                print(f"    Sample: {f.get('aircraftIdentification')} - {f.get('departure')} -> {f.get('arrival')}")
                print(f"    Route: {f.get('route', 'N/A')[:50]}...")
    except Exception as e:
        print(f"  [FAIL] Exception - {e}")
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] ALL TESTS PASSED")
    else:
        print("[FAIL] SOME TESTS FAILED")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = test_api_queries()
    sys.exit(0 if success else 1)
