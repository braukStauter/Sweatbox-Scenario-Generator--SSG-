"""
vNAS API client for pushing scenarios
"""
import requests
import logging
import json
import time
import re
from typing import Dict, Optional, Tuple
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)


class VNASClient:
    """Client for vNAS Data API"""

    BASE_URL = "https://data-api.vnas.vatsim.net"
    LOGIN_URL = "https://data-admin.vnas.vatsim.net/training"

    def __init__(self):
        """Initialize the vNAS client"""
        self.scenario_id = None
        self.driver = None  # Keep browser open for session

    def _login_via_browser(self) -> bool:
        """
        Launch browser for user to log in and navigate to their scenario
        Automatically extracts scenario ID from URL
        Uses undetected_chromedriver to bypass CloudFlare bot detection

        IMPORTANT: Browser stays open to maintain session validity.
        Call cleanup() when done to close the browser.

        Returns:
            True if successful, False otherwise
        """
        logger.info("Launching undetected Chrome browser for vNAS login...")

        try:
            # Use undetected_chromedriver - automatically bypasses CloudFlare
            options = uc.ChromeOptions()
            options.add_argument('--start-maximized')

            # Initialize undetected Chrome driver
            self.driver = uc.Chrome(options=options, use_subprocess=True)

            # Navigate to vNAS data-admin training page
            logger.info(f"Navigating to {self.LOGIN_URL}")
            self.driver.get(self.LOGIN_URL)

            logger.info("=" * 60)
            logger.info("BROWSER INSTRUCTIONS")
            logger.info("=" * 60)
            logger.info("1. Log in to vNAS Data Admin")
            logger.info("2. Navigate to the scenario you want to update")
            logger.info("3. Scenario ID will be extracted automatically")
            logger.info("=" * 60)

            # Wait for user to navigate to their scenario
            timeout = 300  # 5 minutes

            try:
                # Wait for URL to match the scenario pattern
                WebDriverWait(self.driver, timeout).until(
                    lambda d: re.search(r'/scenarios/([a-zA-Z0-9_-]+)', d.current_url)
                )

                current_url = self.driver.current_url
                logger.info(f"Scenario page detected! URL: {current_url}")

                # Extract scenario ID from URL
                match = re.search(r'/scenarios/([a-zA-Z0-9_-]+)', current_url)
                if match:
                    self.scenario_id = match.group(1)
                    logger.info(f"Automatically extracted scenario ID: {self.scenario_id}")
                else:
                    logger.error("Could not extract scenario ID from URL")
                    return False

            except TimeoutException:
                logger.error("Timeout waiting for scenario navigation. Please try again.")
                return False

            logger.info("Browser authenticated successfully. Ready to make API requests.")
            return True

        except Exception as e:
            logger.error(f"Error during browser login: {e}", exc_info=True)
            # On error, close the browser
            if self.driver:
                try:
                    self.driver.quit()
                    self.driver = None
                except:
                    pass
            return False

    def get_existing_scenario(self, scenario_id: str) -> Optional[Dict]:
        """
        Fetch the existing scenario data from vNAS

        Args:
            scenario_id: The scenario ID to fetch

        Returns:
            Scenario dict if successful, None otherwise
        """
        if not self.driver:
            logger.error("No browser connection available")
            return None

        endpoint = f"{self.BASE_URL}/api/training/scenarios/{scenario_id}"

        try:
            logger.info(f"Fetching existing scenario: {scenario_id}")

            js_code = f"""
                var callback = arguments[arguments.length - 1];
                fetch('{endpoint}', {{
                    method: 'GET',
                    credentials: 'include',
                    headers: {{
                        'Accept': 'application/json'
                    }}
                }})
                .then(response => {{
                    return response.json().then(data => {{
                        return {{
                            status: response.status,
                            ok: response.ok,
                            data: data
                        }};
                    }});
                }})
                .then(callback)
                .catch(error => {{
                    callback({{
                        status: 0,
                        ok: false,
                        data: null
                    }});
                }});
            """

            result = self.driver.execute_async_script(js_code)

            if result.get('status') == 200 and result.get('data'):
                logger.info("Successfully fetched existing scenario")
                return result['data']
            else:
                logger.error(f"Failed to fetch scenario: status {result.get('status')}")
                return None

        except Exception as e:
            logger.error(f"Error fetching scenario: {e}", exc_info=True)
            return None

    def push_scenario(self, scenario_data: Dict, scenario_id: str = None) -> tuple:
        """
        Push scenario data to vNAS using the browser (bypasses cookie issues)

        Args:
            scenario_data: The scenario JSON data with aircraft list
            scenario_id: Optional scenario ID to override auto-extracted ID

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Use cached scenario_id or login via browser
        if not self.driver or not self.scenario_id:
            success = self._login_via_browser()
            if not success:
                return False, "Authentication failed. Could not log in to vNAS."

        # Use provided scenario_id or auto-extracted one
        target_scenario_id = scenario_id or self.scenario_id

        if not target_scenario_id:
            return False, "No scenario ID available. Please navigate to your scenario in the browser."

        # Fetch existing scenario to preserve all fields
        # This also validates that we have access to the scenario
        logger.info("Fetching existing scenario data...")
        existing_scenario = self.get_existing_scenario(target_scenario_id)

        if not existing_scenario:
            logger.warning("Could not fetch existing scenario. Using new scenario data.")
            # Use the provided scenario data as-is
            scenario_to_push = scenario_data
            scenario_to_push['id'] = target_scenario_id
        else:
            logger.info("Merging new aircraft with existing scenario...")
            # Update only the aircraft list, keep everything else
            scenario_to_push = existing_scenario
            scenario_to_push['aircraft'] = scenario_data['aircraft']
            # Optionally update name if provided
            if 'name' in scenario_data:
                scenario_to_push['name'] = scenario_data['name']

        endpoint = f"{self.BASE_URL}/api/training/scenarios/{target_scenario_id}"

        try:
            logger.info("=" * 60)
            logger.info("PUSHING SCENARIO VIA BROWSER")
            logger.info("=" * 60)
            logger.info(f"Endpoint: {endpoint}")
            logger.info(f"Scenario ID: {target_scenario_id}")
            logger.info(f"Request body size: {len(json.dumps(scenario_to_push))} bytes")

            # Debug: Log first aircraft to verify spawnDelay is present
            if scenario_to_push.get('aircraft') and len(scenario_to_push['aircraft']) > 0:
                first_aircraft = scenario_to_push['aircraft'][0]
                logger.info(f"DEBUG: First aircraft: {first_aircraft.get('aircraftId')} - spawnDelay: {first_aircraft.get('spawnDelay')}")

            logger.info("=" * 60)

            # Use JavaScript fetch() in the browser to make the PUT request
            # This replicates exactly what happens when user clicks Save
            # credentials: 'include' is CRITICAL for cross-origin requests to send cookies

            # Convert scenario data to JSON string (do NOT use JSON.stringify in JS)
            scenario_json = json.dumps(scenario_to_push)

            js_code = f"""
                var callback = arguments[arguments.length - 1];
                var scenarioData = {scenario_json};

                fetch('{endpoint}', {{
                    method: 'PUT',
                    credentials: 'include',
                    headers: {{
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }},
                    body: JSON.stringify(scenarioData)
                }})
                .then(response => {{
                    return response.text().then(text => {{
                        return {{
                            status: response.status,
                            statusText: response.statusText,
                            body: text,
                            ok: response.ok
                        }};
                    }});
                }})
                .then(callback)
                .catch(error => {{
                    callback({{
                        status: 0,
                        statusText: error.toString(),
                        body: '',
                        ok: false
                    }});
                }});
            """

            logger.info("Executing PUT request through browser...")
            result = self.driver.execute_async_script(js_code)

            logger.info("=" * 60)
            logger.info("API RESPONSE DEBUG")
            logger.info("=" * 60)
            logger.info(f"Status Code: {result.get('status', 'unknown')}")
            logger.info(f"Status Text: {result.get('statusText', 'unknown')}")
            logger.info(f"Response Body (first 500 chars): {result.get('body', '')[:500]}")
            logger.info("=" * 60)

            status = result.get('status', 0)

            if status in (200, 204):
                logger.info(f"Successfully pushed scenario to vNAS (status {status})")
                return True, "Successfully pushed scenario to vNAS!"

            elif status == 401:
                logger.error("Authentication failed - session may have expired")
                return False, "Authentication failed. Please try again."

            elif status == 404:
                logger.error(f"Scenario ID {target_scenario_id} not found")
                return False, f"Scenario ID '{target_scenario_id}' not found. Please check the ID and try again."

            else:
                error_msg = f"Failed to push scenario. Status: {status}"
                if result.get('body'):
                    error_msg += f"\nDetails: {result['body'][:500]}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    def test_connection(self) -> tuple:
        """
        Test connection to vNAS API by verifying browser session

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Ensure browser is authenticated
        if not self.driver or not self.scenario_id:
            success = self._login_via_browser()
            if not success:
                return False, "Authentication failed. Could not log in to vNAS."

        try:
            # Test connection using browser fetch
            js_code = f"""
                var callback = arguments[arguments.length - 1];
                fetch('{self.BASE_URL}/api/training/scenarios', {{
                    method: 'GET',
                    credentials: 'include',
                    headers: {{
                        'Accept': 'application/json'
                    }}
                }})
                .then(response => {{
                    callback({{
                        status: response.status,
                        ok: response.ok
                    }});
                }})
                .catch(error => {{
                    callback({{
                        status: 0,
                        ok: false
                    }});
                }});
            """

            result = self.driver.execute_async_script(js_code)

            if result.get('status') == 200:
                return True, "Successfully connected to vNAS API"
            elif result.get('status') == 401:
                return False, "Authentication failed. Please log in to vNAS in your browser."
            else:
                return False, f"Connection test failed with status {result.get('status')}"

        except Exception as e:
            return False, f"Connection test failed: {str(e)}"

    def get_artcc_info(self, artcc_id: str) -> Optional[Dict]:
        """
        Query vNAS API for ARTCC information (public endpoint, no auth required)

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB")

        Returns:
            ARTCC info dict, or None if failed
        """
        try:
            endpoint = f"{self.BASE_URL}/api/artccs/{artcc_id}"
            response = requests.get(endpoint, timeout=10)

            if response.status_code == 200:
                artcc_data = response.json()
                logger.info(f"Successfully fetched ARTCC info for {artcc_id}")
                return artcc_data
            else:
                logger.warning(f"Could not fetch ARTCC info for {artcc_id}: HTTP {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching ARTCC info: {e}")
            return None

    def cleanup(self):
        """
        Close the browser and clean up resources

        Call this after push_scenario() completes to close the browser window
        """
        if self.driver:
            try:
                logger.info("Closing browser...")
                self.driver.quit()
                self.driver = None
                logger.info("Browser closed successfully")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
                self.driver = None
