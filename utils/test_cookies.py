"""
Debug utility to test Selenium-based vNAS login
Run this script to test the browser automation login flow
"""
import logging
import sys

# Set UTF-8 encoding for console output
if sys.platform == 'win32':
    import os
    os.system('chcp 65001 >nul 2>&1')

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def test_selenium_login():
    """Test Selenium-based browser login"""
    print("\n" + "="*60)
    print("VNAS Selenium Login Test")
    print("="*60 + "\n")

    try:
        import selenium
        print("[OK] selenium is installed\n")
    except ImportError:
        print("[FAIL] selenium is NOT installed")
        print("  Install with: pip install selenium\n")
        return

    from vnas_client import VNASClient

    print("Initializing vNAS client...\n")
    client = VNASClient()

    print("Testing connection (will launch browser for login)...\n")
    print("=" * 60)
    print("INSTRUCTIONS:")
    print("1. A Chrome browser window will open")
    print("2. Log in to vNAS Data Admin")
    print("3. Navigate to a scenario (URL: /scenarios/{scenario-id})")
    print("4. After navigating to scenario, browser will close automatically")
    print("5. The test will show results below")
    print("=" * 60 + "\n")

    success, message = client.test_connection()

    print("\n" + "="*60)
    if success:
        print("[SUCCESS] vNAS connection test passed!")
        print(f"Message: {message}")

        if client.scenario_id:
            print(f"\nAuto-extracted Scenario ID: {client.scenario_id}")

        print(f"\nCaptured {len(client.cookies)} cookies")
        if client.cookies:
            print("\nCookie details:")
            for cookie in client.cookies:
                print(f"  - {cookie.name}")
                print(f"    Domain: {cookie.domain}")
                print(f"    Path: {cookie.path}")
                print()
    else:
        print("[FAIL] vNAS connection test failed")
        print(f"Error: {message}")
    print("="*60 + "\n")

if __name__ == "__main__":
    test_selenium_login()
