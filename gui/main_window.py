"""
Main application window and controller
"""
import tkinter as tk
import logging
import threading
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from gui.theme import DarkTheme
from gui.screens.airport_selection import AirportSelectionScreen
from gui.screens.scenario_type_selection import ScenarioTypeSelectionScreen
from gui.screens.scenario_config import ScenarioConfigScreen
from gui.screens.generation_screen import GenerationScreen

from parsers.geojson_parser import GeoJSONParser
from parsers.cifp_parser import CIFPParser
from utils.api_client import FlightDataAPIClient
from utils.preset_command_processor import apply_preset_commands
from generators.vnas_json_exporter import VNASJSONExporter

from scenarios.ground_departures import GroundDeparturesScenario
from scenarios.ground_mixed import GroundMixedScenario
from scenarios.tower_mixed import TowerMixedScenario
from scenarios.tracon_arrivals import TraconArrivalsScenario
from scenarios.tracon_mixed import TraconMixedScenario
from scenarios.artcc_enroute import ArtccEnrouteScenario
from models.spawn_delay_mode import SpawnDelayMode

logger = logging.getLogger(__name__)


class DarkThemedDialog(tk.Toplevel):
    """Custom dark-themed dialog for text input"""

    def __init__(self, parent, title, prompt, initial_value="", info_text="", validator=None):
        super().__init__(parent)
        self.result = None
        self.validator = validator

        # Configure window
        self.title(title)
        self.configure(bg=DarkTheme.BG_PRIMARY)
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Main frame
        main_frame = tk.Frame(self, bg=DarkTheme.BG_PRIMARY)
        main_frame.pack(fill='both', expand=True, padx=DarkTheme.PADDING_XLARGE, pady=DarkTheme.PADDING_LARGE)

        # Prompt label
        prompt_label = tk.Label(
            main_frame,
            text=prompt,
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            justify='left'
        )
        prompt_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Entry field
        self.entry_var = tk.StringVar(value=initial_value)
        entry_frame = tk.Frame(main_frame, bg=DarkTheme.BG_SECONDARY, highlightthickness=1, highlightbackground=DarkTheme.BORDER)
        entry_frame.pack(fill='x', pady=(0, DarkTheme.PADDING_SMALL))

        self.entry = tk.Entry(
            entry_frame,
            textvariable=self.entry_var,
            bg=DarkTheme.BG_SECONDARY,
            fg=DarkTheme.FG_PRIMARY,
            insertbackground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            relief='flat',
            bd=0
        )
        self.entry.pack(fill='x', padx=DarkTheme.PADDING_SMALL, pady=DarkTheme.PADDING_SMALL)
        self.entry.focus_set()
        self.entry.select_range(0, tk.END)

        # Info text (helper text)
        if info_text:
            info_label = tk.Label(
                main_frame,
                text=info_text,
                bg=DarkTheme.BG_PRIMARY,
                fg=DarkTheme.FG_SECONDARY,
                font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
                justify='left'
            )
            info_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))

        # Error message label (initially hidden)
        self.error_label = tk.Label(
            main_frame,
            text="",
            bg=DarkTheme.BG_PRIMARY,
            fg=DarkTheme.ERROR,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_SMALL),
            justify='left'
        )

        # Bind Enter key
        self.entry.bind('<Return>', lambda e: self.ok())
        self.entry.bind('<Escape>', lambda e: self.cancel())

        # Button frame
        button_frame = tk.Frame(main_frame, bg=DarkTheme.BG_PRIMARY)
        button_frame.pack(fill='x')

        # Cancel button
        cancel_btn = tk.Button(
            button_frame,
            text="Cancel",
            command=self.cancel,
            bg=DarkTheme.BG_SECONDARY,
            fg=DarkTheme.FG_PRIMARY,
            activebackground=DarkTheme.BG_TERTIARY,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL),
            relief='flat',
            bd=0,
            padx=DarkTheme.PADDING_LARGE,
            pady=DarkTheme.PADDING_SMALL,
            cursor='hand2'
        )
        cancel_btn.pack(side='left', padx=(0, DarkTheme.PADDING_SMALL))

        # OK button
        ok_btn = tk.Button(
            button_frame,
            text="OK",
            command=self.ok,
            bg=DarkTheme.ACCENT_PRIMARY,
            fg=DarkTheme.FG_PRIMARY,
            activebackground=DarkTheme.ACCENT_HOVER,
            activeforeground=DarkTheme.FG_PRIMARY,
            font=(DarkTheme.FONT_FAMILY, DarkTheme.FONT_SIZE_NORMAL, 'bold'),
            relief='flat',
            bd=0,
            padx=DarkTheme.PADDING_LARGE,
            pady=DarkTheme.PADDING_SMALL,
            cursor='hand2'
        )
        ok_btn.pack(side='right')

        # Center on parent
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (width // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

    def ok(self):
        value = self.entry_var.get()

        # Validate if validator is provided
        if self.validator:
            is_valid, error_msg = self.validator(value)
            if not is_valid:
                # Show error message
                self.error_label.config(text=error_msg)
                self.error_label.pack(anchor='w', pady=(0, DarkTheme.PADDING_SMALL))
                # Highlight entry field
                self.entry.master.config(highlightbackground=DarkTheme.ERROR, highlightthickness=2)
                # Shake the window slightly (simple visual feedback)
                self.bell()
                return

        self.result = value
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


class MainWindow(tk.Tk):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("vNAS Sweatbox Scenario Generator")
        self.geometry("900x1000")
        self.minsize(800, 900)
        self.configure(bg=DarkTheme.BG_PRIMARY)

        # Center window on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

        # Application state
        self.airport_icao = None
        self.scenario_type = None
        self.geojson_parser = None
        self.cifp_parser = None
        self.api_client = FlightDataAPIClient()
        self.airport_data_dir = Path("airport_data")

        # Enroute scenario state
        self.is_enroute_scenario = False
        self.artcc_id = None

        # Cached flight data
        self.cached_departures = []
        self.cached_arrivals = []
        self.flight_cache_timestamp = None
        self.flight_data_loading = False
        self.flight_data_ready = False

        # Cached enroute transient pool (loaded when ARTCC is selected)
        # Departure/arrival pools are fetched during generation based on selected airports
        self.cached_enroute_transient_pool = []
        self.enroute_pool_cache_timestamp = None

        # Container for screens
        self.container = tk.Frame(self, bg=DarkTheme.BG_PRIMARY)
        self.container.pack(fill='both', expand=True)

        # Initialize screens
        self.screens = {}
        self._init_screens()

        # Show initial screen
        self.show_screen('airport')

    def _init_screens(self):
        """Initialize all application screens"""
        self.screens['airport'] = AirportSelectionScreen(self.container, self)
        self.screens['scenario_type'] = ScenarioTypeSelectionScreen(self.container, self)
        self.screens['scenario_config'] = ScenarioConfigScreen(self.container, self)
        self.screens['generation'] = GenerationScreen(self.container, self)

        # Place all screens in the same location
        for screen in self.screens.values():
            screen.place(x=0, y=0, relwidth=1, relheight=1)

    def show_screen(self, screen_name):
        """Show a specific screen"""
        if screen_name not in self.screens:
            logger.error(f"Screen '{screen_name}' not found")
            return

        # If showing scenario_config, load the appropriate form
        if screen_name == 'scenario_config':
            self.screens['scenario_config'].load_config_for_scenario(self.scenario_type)

        # Raise the screen to the front
        self.screens[screen_name].tkraise()

    def upload_scenario_to_vnas(self, filepath: str):
        """Upload a JSON scenario file directly to vNAS"""
        try:
            logger.info(f"Loading scenario file for upload: {filepath}")

            # Load the JSON file
            from generators.vnas_json_exporter import VNASJSONExporter
            scenario_json = VNASJSONExporter.load(filepath)

            # Get aircraft count for display
            aircraft_count = len(scenario_json.get('aircraft', []))
            scenario_name = scenario_json.get('name', 'Unknown Scenario')

            logger.info(f"Loaded scenario '{scenario_name}' with {aircraft_count} aircraft")

            # Show info dialog about browser login
            from tkinter import messagebox
            result = messagebox.showinfo(
                "Upload to vNAS",
                f"Ready to upload scenario:\n\n"
                f"Name: {scenario_name}\n"
                f"Aircraft: {aircraft_count}\n\n"
                f"A browser window will open for you to log in to vNAS.\n\n"
                f"IMPORTANT STEPS:\n"
                f"1. Log in to vNAS Data Admin\n"
                f"2. Navigate to the scenario you want to update\n"
                f"3. The scenario ID will be extracted automatically\n\n"
                f"The browser will close after the upload completes.",
                icon=messagebox.INFO
            )

            # Initialize vNAS client and push scenario
            from utils.vnas_client import VNASClient
            client = VNASClient()

            try:
                success, message = client.push_scenario(scenario_json)

                if success:
                    messagebox.showinfo(
                        "Upload Successful",
                        f"Successfully uploaded scenario to vNAS!\n\n{message}"
                    )
                else:
                    messagebox.showerror(
                        "Upload Failed",
                        f"Failed to upload scenario to vNAS:\n\n{message}"
                    )

            finally:
                # Clean up browser
                client.close()

        except Exception as e:
            logger.exception(f"Error uploading scenario file: {e}")
            from tkinter import messagebox
            messagebox.showerror(
                "Upload Error",
                f"Failed to upload scenario file:\n\n{str(e)}"
            )

    def load_airport_data(self, airport_icao):
        """Load airport data in a background thread"""
        # Check if this is an enroute scenario
        if airport_icao == "ENROUTE":
            self._handle_enroute_scenario()
            return

        # Run loading in a separate thread for regular airport scenarios
        loading_thread = threading.Thread(target=self._load_airport_data_thread, args=(airport_icao,), daemon=True)
        loading_thread.start()

    def _handle_enroute_scenario(self):
        """Handle enroute scenario selection"""
        from utils.artcc_utils import get_artcc_boundaries

        # Hide loading on airport screen
        self.screens['airport'].hide_loading()

        # Get available ARTCCs
        artcc_boundaries = get_artcc_boundaries()
        artcc_list = artcc_boundaries.get_all_artcc_ids()

        # Create validator function
        def validate_artcc(value):
            if not value:
                return False, "ARTCC identifier cannot be empty"

            value_upper = value.upper().strip()

            if len(value_upper) != 3:
                return False, "ARTCC identifier must be exactly 3 letters"

            if not value_upper.isalpha():
                return False, "ARTCC identifier must contain only letters"

            if value_upper not in artcc_list:
                return False, f"Unknown ARTCC '{value_upper}'. Available: {', '.join(sorted(artcc_list))}"

            return True, ""

        # Show dark-themed ARTCC selection dialog
        dialog = DarkThemedDialog(
            self,
            title="Select ARTCC",
            prompt="Enter ARTCC identifier:",
            initial_value="",
            info_text="Enter the three-letter ARTCC identifier (e.g., ZAB, ZLA, ZDV)",
            validator=validate_artcc
        )
        artcc_id = dialog.show()

        if artcc_id:
            self.artcc_id = artcc_id.upper().strip()
            logger.info(f"Selected ARTCC: {self.artcc_id}")

            # Show loading screen
            self.screens['airport'].show_loading(f"Loading data for ARTCC {self.artcc_id}...")

            # Load ARTCC data in background thread
            loading_thread = threading.Thread(
                target=self._load_artcc_data_thread,
                args=(self.artcc_id,),
                daemon=True
            )
            loading_thread.start()
        else:
            logger.info("ARTCC selection cancelled")
            # Stay on airport selection screen

    def _load_artcc_data_thread(self, artcc_id):
        """Load ARTCC data (runs in separate thread)"""
        try:
            import time
            import json
            from pathlib import Path

            self.airport_icao = None  # No single airport for enroute
            self.is_enroute_scenario = True
            self.scenario_type = 'enroute'

            logger.info(f"Loading ARTCC data for: {artcc_id}")

            # Load config to get airport lists
            config_path = Path('config.json')
            airport_groups = {}

            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    airport_groups = config.get('artcc_airport_groups', {}).get(artcc_id, {})

            # Pre-load ONLY the transient pool (we don't know which airports will be selected yet)
            logger.info(f"Pre-loading transient pool for ARTCC {artcc_id}...")
            self._preload_transient_pool(artcc_id)

            # Store the airport groups for later loading
            self.artcc_airport_groups = airport_groups

            logger.info(f"Found {len(airport_groups)} airport groups for ARTCC {artcc_id}")

            # Initialize empty parsers - will be loaded during generation
            self.geojson_parsers = {}
            self.cifp_parsers = {}

            # Hide loading and show next screen (thread-safe)
            self.after(0, self._on_artcc_data_loaded)

        except Exception as e:
            logger.error(f"Error loading ARTCC data: {e}")
            # Show error (thread-safe)
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self._on_artcc_data_error(msg))

    def _preload_transient_pool(self, artcc_id: str):
        """Pre-load transient pool for ARTCC (called from background thread)"""
        import time
        from utils.flight_data_filter import filter_valid_flights

        try:
            logger.info(f"Fetching Transient Pool for ARTCC {artcc_id} (artcc=K{artcc_id.upper()})")
            flights = self.api_client.fetch_artcc_flights(artcc_id, limit=400)

            if flights:
                # Filter pool
                filtered = self._filter_enroute_pool(flights, "Transient")
                self.cached_enroute_transient_pool = filtered
                logger.info(f"Transient Pool loaded: {len(filtered)} aircraft from {len(flights)} total")
            else:
                self.cached_enroute_transient_pool = []
                logger.warning(f"No transient flights found for ARTCC {artcc_id}")

            self.enroute_pool_cache_timestamp = time.time()

        except Exception as e:
            logger.error(f"Error loading transient pool: {e}")
            self.cached_enroute_transient_pool = []

    def _filter_enroute_pool(self, flights: List[Dict], pool_name: str) -> List[Dict]:
        """Filter enroute pool: Accept ACTIVE and PROPOSED flights with complete flight plans"""
        from utils.flight_data_filter import filter_valid_flights

        if not flights:
            return []

        # NEW: Accept both ACTIVE and PROPOSED flights
        accepted_flights = [f for f in flights if f.get('flightStatus') in ['ACTIVE', 'PROPOSED']]
        logger.debug(f"{pool_name} Pool: {len(accepted_flights)}/{len(flights)} with ACTIVE/PROPOSED status")

        # Apply standard validity filtering
        valid_flights = filter_valid_flights(accepted_flights)
        logger.debug(f"{pool_name} Pool: {len(valid_flights)}/{len(accepted_flights)} passed validity checks")

        # Filter for required fields, complete procedures, and no lat/long in routes
        clean_flights = []
        missing_dep_proc = 0
        missing_arr_proc = 0

        for flight in valid_flights:
            route = flight.get('route', '')
            altitude = flight.get('requestedAltitude') or flight.get('assignedAltitude')
            speed = flight.get('requestedAirspeed')  # API uses 'requestedAirspeed' not 'cruiseSpeed'
            dep_proc = flight.get('departureProcedure', '')
            arr_proc = flight.get('arrivalProcedure', '')

            # NEW: Require complete flight plans (both departure and arrival procedures)
            if not dep_proc:
                missing_dep_proc += 1
                continue
            if not arr_proc:
                missing_arr_proc += 1
                continue

            # Check for lat/long format in route
            if self._has_lat_long_format(route):
                continue

            # Ensure required fields exist (altitude is optional for transient pool)
            if not route or not speed:
                continue

            clean_flights.append(flight)

        logger.debug(f"{pool_name} Pool: {len(clean_flights)}/{len(valid_flights)} after route/field filtering")
        if missing_dep_proc > 0 or missing_arr_proc > 0:
            logger.info(f"  - Filtered out {missing_dep_proc} flights missing departure procedure")
            logger.info(f"  - Filtered out {missing_arr_proc} flights missing arrival procedure")
        logger.info(f"{pool_name} Pool filtered: {len(clean_flights)} valid aircraft from {len(flights)} total")

        return clean_flights

    def _has_lat_long_format(self, route: str) -> bool:
        """Check if route contains lat/long coordinates"""
        if not route:
            return False

        # Simple check for lat/long patterns (e.g., N40W120, 40N120W, etc.)
        import re
        lat_long_pattern = r'[NS]\d{2,4}[EW]\d{3,5}|\d{2,4}[NS]\d{3,5}[EW]'
        return bool(re.search(lat_long_pattern, route.upper()))

    def _on_artcc_data_loaded(self):
        """Callback when ARTCC data is loaded (runs on main thread)"""
        # Hide loading
        self.screens['airport'].hide_loading()

        # Load config screen for enroute scenario
        self.screens['scenario_config'].load_config_for_scenario('enroute')

        # Go directly to scenario configuration
        self.show_screen('scenario_config')

    def _on_artcc_data_error(self, error_msg):
        """Callback when ARTCC data loading fails (runs on main thread)"""
        # Hide loading
        self.screens['airport'].hide_loading()

        # Show error message
        from tkinter import messagebox
        messagebox.showerror(
            "ARTCC Data Error",
            f"Failed to load ARTCC data:\n\n{error_msg}"
        )

    def _load_airport_data_thread(self, airport_icao):
        """Load airport data (runs in separate thread)"""
        try:
            import time
            self.airport_icao = airport_icao
            self.is_enroute_scenario = False
            logger.info(f"Selected airport: {airport_icao}")

            # Load GeoJSON data
            logger.info("Loading GeoJSON data...")
            # Use full ICAO for non-K airports (P, T, C, etc.), strip K for US airports
            geojson_filename = airport_icao[1:].lower() if airport_icao.startswith('K') else airport_icao.lower()
            geojson_path = self.airport_data_dir / f"{geojson_filename}.geojson"
            self.geojson_parser = GeoJSONParser(str(geojson_path), airport_icao)
            logger.info("GeoJSON data loaded successfully")

            # Load CIFP data
            logger.info("Loading CIFP data...")
            cifp_path = self.airport_data_dir / "FAACIFP18"
            if cifp_path.exists():
                self.cifp_parser = CIFPParser(str(cifp_path), airport_icao)
                logger.info("CIFP data loaded successfully")
            else:
                self.cifp_parser = None
                logger.warning("CIFP data not found")

            # Start loading flight data from API in background (non-blocking)
            logger.info("Starting background flight data loading from API...")
            self._start_flight_data_loading(airport_icao)

            # Hide loading and show next screen immediately (thread-safe)
            self.after(0, self._on_airport_data_loaded)

        except Exception as e:
            logger.error(f"Error loading airport data: {e}")
            # Show error (thread-safe)
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self._on_airport_data_error(msg))

    def _start_flight_data_loading(self, airport_icao):
        """Start loading flight data from API in background (non-blocking)"""
        import time
        import threading

        # Mark data as loading
        self.flight_data_loading = True
        self.flight_data_ready = False

        def fetch_and_store():
            """Fetch both departures and arrivals in parallel"""
            departures_result = [None]
            arrivals_result = [None]

            def fetch_departures():
                try:
                    logger.info(f"Fetching 1000 departures from {airport_icao}...")
                    departures_result[0] = self.api_client.fetch_departures(airport_icao, limit=1000)
                    logger.info(f"Fetched {len(departures_result[0]) if departures_result[0] else 0} departures")
                except Exception as e:
                    logger.error(f"Error fetching departures: {e}")
                    departures_result[0] = []

            def fetch_arrivals():
                try:
                    logger.info(f"Fetching 1000 arrivals to {airport_icao}...")
                    arrivals_result[0] = self.api_client.fetch_arrivals(airport_icao, limit=1000)
                    logger.info(f"Fetched {len(arrivals_result[0]) if arrivals_result[0] else 0} arrivals")
                except Exception as e:
                    logger.error(f"Error fetching arrivals: {e}")
                    arrivals_result[0] = []

            # Start both fetch threads
            dep_thread = threading.Thread(target=fetch_departures, daemon=True)
            arr_thread = threading.Thread(target=fetch_arrivals, daemon=True)

            dep_thread.start()
            arr_thread.start()

            # Wait for both to complete
            dep_thread.join()
            arr_thread.join()

            # Store results
            self.cached_departures = departures_result[0] if departures_result[0] else []
            self.cached_arrivals = arrivals_result[0] if arrivals_result[0] else []
            self.flight_cache_timestamp = time.time()
            self.flight_data_loading = False
            self.flight_data_ready = True

            logger.info(f"Flight data loading complete: {len(self.cached_departures)} departures, {len(self.cached_arrivals)} arrivals")

            # Update GUI status (thread-safe)
            self.after(0, lambda: self._on_flight_data_loaded())

        # Start the loading thread (non-blocking)
        loading_thread = threading.Thread(target=fetch_and_store, daemon=True)
        loading_thread.start()
        logger.info("Flight data loading started in background")

    def _on_airport_data_loaded(self):
        """Called when airport data is loaded successfully"""
        self.screens['airport'].hide_loading()
        self.show_screen('scenario_type')

        # Show loading status if flight data is still loading
        if self.flight_data_loading and not self.flight_data_ready:
            self.screens['scenario_type'].update_loading_status(True)

    def _on_flight_data_loaded(self):
        """Called when flight data loading completes"""
        # Update status in scenario type screen if it's visible
        if hasattr(self, 'screens') and 'scenario_type' in self.screens:
            self.screens['scenario_type'].update_loading_status(
                False,
                len(self.cached_departures),
                len(self.cached_arrivals)
            )

    def _on_airport_data_error(self, error_message):
        """Called when airport data loading fails"""
        self.screens['airport'].hide_loading()
        logger.error(f"Failed to load airport data: {error_message}")
        # Could show an error dialog here if needed

    def set_airport(self, airport_icao):
        """Set selected airport (for backward compatibility)"""
        self.airport_icao = airport_icao

    def set_scenario_type(self, scenario_type):
        """Set selected scenario type"""
        self.scenario_type = scenario_type
        logger.info(f"Selected scenario type: {scenario_type}")

    def generate_scenario(self, config):
        """Generate scenario with given configuration"""
        # Show generation screen
        self.show_screen('generation')
        self.screens['generation'].show_progress()

        # Run generation in a separate thread to keep UI responsive
        generation_thread = threading.Thread(target=self._do_generation, args=(config,), daemon=True)
        generation_thread.start()

    def _update_progress(self, message):
        """Update progress message (thread-safe)"""
        self.after(0, lambda: self.screens['generation'].progress.label.config(text=message))

    def _do_generation(self, config):
        """Actually perform the generation (runs in separate thread)"""
        try:
            # Update progress
            self._update_progress("Parsing configuration...")

            # Parse difficulty levels first to determine aircraft counts
            difficulty_config = None
            difficulty_departures_config = None
            difficulty_arrivals_config = None

            if config.get('enable_difficulty'):
                if self.scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_mixed']:
                    # Mixed scenarios: separate difficulty for departures and arrivals
                    difficulty_departures_config = {
                        'easy': int(config.get('difficulty_departures_easy', 0) or 0),
                        'medium': int(config.get('difficulty_departures_medium', 0) or 0),
                        'hard': int(config.get('difficulty_departures_hard', 0) or 0)
                    }
                    difficulty_arrivals_config = {
                        'easy': int(config.get('difficulty_arrivals_easy', 0) or 0),
                        'medium': int(config.get('difficulty_arrivals_medium', 0) or 0),
                        'hard': int(config.get('difficulty_arrivals_hard', 0) or 0)
                    }

                    # Calculate counts from difficulty
                    num_departures = sum(difficulty_departures_config.values())
                    num_arrivals = sum(difficulty_arrivals_config.values())

                    # Use the single difficulty_config for backward compatibility with departure-only logic
                    difficulty_config = difficulty_departures_config

                elif self.scenario_type == 'tracon_arrivals':
                    # Arrivals-only scenario - use arrivals difficulty
                    difficulty_arrivals_config = {
                        'easy': int(config.get('difficulty_arrivals_easy', 0) or 0),
                        'medium': int(config.get('difficulty_arrivals_medium', 0) or 0),
                        'hard': int(config.get('difficulty_arrivals_hard', 0) or 0)
                    }
                    num_departures = 0
                    num_arrivals = sum(difficulty_arrivals_config.values())
                    difficulty_config = difficulty_arrivals_config

                else:
                    # Departure-only scenarios (ground_departures) - use departures difficulty
                    difficulty_departures_config = {
                        'easy': int(config.get('difficulty_departures_easy', 0) or 0),
                        'medium': int(config.get('difficulty_departures_medium', 0) or 0),
                        'hard': int(config.get('difficulty_departures_hard', 0) or 0)
                    }
                    num_departures = sum(difficulty_departures_config.values())
                    num_arrivals = 0
                    difficulty_config = difficulty_departures_config
            else:
                # Parse manual configuration
                num_departures = int(config.get('num_departures', 0)) if config.get('num_departures') else 0
                num_arrivals = int(config.get('num_arrivals', 0)) if config.get('num_arrivals') else 0

            # Parse runways
            active_runways = []
            if config.get('active_runways'):
                active_runways = [r.strip() for r in config['active_runways'].split(',')]

            # Parse additional separation (single integer value to add to minimum separation)
            additional_separation = 0
            if config.get('separation_range'):
                try:
                    additional_separation = int(config['separation_range'])
                except ValueError:
                    logger.warning(f"Invalid separation value: {config.get('separation_range')}, using default 0")
                    additional_separation = 0

            # Parse delay range
            delay_range = (4, 7)
            if config.get('delay_range'):
                try:
                    parts = config['delay_range'].split('-')
                    delay_range = (int(parts[0]), int(parts[1]))
                except:
                    pass

            # Parse spawn delay configuration
            spawn_delay_mode = SpawnDelayMode.NONE  # default - all aircraft spawn at once
            delay_value = None
            total_session_minutes = None

            if config.get('enable_spawn_delays', False):
                mode_str = config.get('spawn_delay_mode', 'incremental')
                if mode_str == 'incremental':
                    spawn_delay_mode = SpawnDelayMode.INCREMENTAL
                    delay_value = config.get('incremental_delay_value', '2-5')
                elif mode_str == 'total':
                    spawn_delay_mode = SpawnDelayMode.TOTAL
                    total_minutes_str = config.get('total_session_minutes', '30')
                    try:
                        total_session_minutes = int(total_minutes_str)
                    except ValueError:
                        total_session_minutes = 30

            # Parse waypoints
            arrival_waypoints = []
            if config.get('arrival_waypoints'):
                arrival_waypoints = [w.strip().upper() for w in config['arrival_waypoints'].split(',')]

            # Parse CIFP speed configuration for arrivals
            use_cifp_speeds = config.get('use_cifp_speeds', True)

            # Parse CIFP SID configuration
            enable_cifp_sids = config.get('enable_cifp_sids', False)
            manual_sids = []
            if config.get('manual_sids'):
                manual_sids = [s.strip().upper() for s in config['manual_sids'].split(',') if s.strip()]

            # Parse VFR aircraft configuration
            enable_vfr = config.get('enable_vfr', False)
            num_vfr = 0
            vfr_spawn_locations = []
            if enable_vfr:
                try:
                    num_vfr = int(config.get('num_vfr', 0))
                except ValueError:
                    num_vfr = 0

                if config.get('vfr_spawn_locations'):
                    vfr_spawn_locations = [loc.strip().upper() for loc in config['vfr_spawn_locations'].split(',') if loc.strip()]

            # Parse enroute-specific configuration
            num_enroute = 0
            arrival_airports = None
            departure_airports = None
            difficulty_config_enroute = None
            difficulty_config_arrivals = None
            difficulty_config_departures = None

            if self.is_enroute_scenario:
                # Check if difficulty mode is enabled for enroute
                difficulty_enabled = config.get('enable_difficulty_enroute', False)

                if difficulty_enabled:
                    # Parse difficulty levels for each category
                    difficulty_config_enroute = {
                        'easy': int(config.get('difficulty_enroute_easy', 0) or 0),
                        'medium': int(config.get('difficulty_enroute_medium', 0) or 0),
                        'hard': int(config.get('difficulty_enroute_hard', 0) or 0)
                    }

                    difficulty_config_arrivals = {
                        'easy': int(config.get('difficulty_arrivals_easy', 0) or 0),
                        'medium': int(config.get('difficulty_arrivals_medium', 0) or 0),
                        'hard': int(config.get('difficulty_arrivals_hard', 0) or 0)
                    }

                    difficulty_config_departures = {
                        'easy': int(config.get('difficulty_departures_easy', 0) or 0),
                        'medium': int(config.get('difficulty_departures_medium', 0) or 0),
                        'hard': int(config.get('difficulty_departures_hard', 0) or 0)
                    }

                    # Calculate total aircraft from difficulty levels
                    num_enroute = (difficulty_config_enroute['easy'] +
                                  difficulty_config_enroute['medium'] +
                                  difficulty_config_enroute['hard'])

                    num_arrivals = (difficulty_config_arrivals['easy'] +
                                   difficulty_config_arrivals['medium'] +
                                   difficulty_config_arrivals['hard'])

                    num_departures = (difficulty_config_departures['easy'] +
                                     difficulty_config_departures['medium'] +
                                     difficulty_config_departures['hard'])
                else:
                    # Parse simple aircraft counts
                    num_enroute = int(config.get('num_enroute', 0)) if config.get('num_enroute') else 0
                    num_arrivals = int(config.get('num_arrivals_enroute', 0)) if config.get('num_arrivals_enroute') else 0
                    num_departures = int(config.get('num_departures_enroute', 0)) if config.get('num_departures_enroute') else 0

                # Initialize airport lists
                arrival_airports = []
                departure_airports = []

                # Parse arrival airports with runways
                # Format: "Group Name: ICAO:runway1,runway2,ICAO:runway1,runway2"
                arrival_group = config.get('arrival_airports_group', '')
                arrival_airport_runways = {}  # Maps ICAO to list of runways
                if arrival_group:
                    if ':' in arrival_group:
                        # Split to get airport data after "Group Name: "
                        airports_str = arrival_group.split(':', 1)[1].strip()
                        # Parse comma-separated entries (ICAO:runway,runway,ICAO:runway,runway)
                        # We need to handle entries that may have colons in them
                        current_icao = None
                        for entry in airports_str.split(','):
                            entry = entry.strip()
                            if ':' in entry:
                                # This is a new airport entry (ICAO:runway)
                                icao, runway = entry.split(':', 1)
                                current_icao = icao.strip()
                                runway = runway.strip()
                                if current_icao not in arrival_airports:
                                    arrival_airports.append(current_icao)
                                    arrival_airport_runways[current_icao] = []
                                arrival_airport_runways[current_icao].append(runway)
                            elif entry and current_icao:
                                # This is another runway for the current airport
                                arrival_airport_runways[current_icao].append(entry)
                            elif entry:
                                # Fallback: just ICAO (no runways specified)
                                if entry not in arrival_airports:
                                    arrival_airports.append(entry)
                elif config.get('arrival_airports_manual'):
                    arrival_airports = [a.strip() for a in config['arrival_airports_manual'].split(',') if a.strip()]

                # Parse departure airports with runways
                # Format: "Group Name: ICAO:runway1,runway2,ICAO:runway1,runway2"
                departure_group = config.get('departure_airports_group', '')
                departure_airport_runways = {}  # Maps ICAO to list of runways
                if departure_group:
                    if ':' in departure_group:
                        # Split to get airport data after "Group Name: "
                        airports_str = departure_group.split(':', 1)[1].strip()
                        # Parse comma-separated entries (ICAO:runway,runway,ICAO:runway,runway)
                        current_icao = None
                        for entry in airports_str.split(','):
                            entry = entry.strip()
                            if ':' in entry:
                                # This is a new airport entry (ICAO:runway)
                                icao, runway = entry.split(':', 1)
                                current_icao = icao.strip()
                                runway = runway.strip()
                                if current_icao not in departure_airports:
                                    departure_airports.append(current_icao)
                                    departure_airport_runways[current_icao] = []
                                departure_airport_runways[current_icao].append(runway)
                            elif entry and current_icao:
                                # This is another runway for the current airport
                                departure_airport_runways[current_icao].append(entry)
                            elif entry:
                                # Fallback: just ICAO (no runways specified)
                                if entry not in departure_airports:
                                    departure_airports.append(entry)
                elif config.get('departure_airports_manual'):
                    departure_airports = [a.strip() for a in config['departure_airports_manual'].split(',') if a.strip()]

                # Log runway information for debugging
                if arrival_airport_runways:
                    logger.info(f"Arrival airport runways: {arrival_airport_runways}")
                if departure_airport_runways:
                    logger.info(f"Departure airport runways: {departure_airport_runways}")

            # Wait for flight data to finish loading (if still in progress)
            if self.flight_data_loading and not self.flight_data_ready:
                self._update_progress("Waiting for flight data to finish loading...")
                logger.info("Waiting for background flight data loading to complete...")
                import time
                while self.flight_data_loading and not self.flight_data_ready:
                    time.sleep(0.1)  # Check every 100ms
                logger.info("Flight data loading complete")

            # Update progress
            self._update_progress("Creating scenario...")

            # Generate scenario based on type
            scenario = self._create_scenario()

            # Update progress
            self._update_progress("Generating aircraft...")

            aircraft = self._generate_aircraft(
                scenario,
                num_departures,
                num_arrivals,
                active_runways,
                additional_separation,
                delay_range,
                arrival_waypoints,
                spawn_delay_mode,
                delay_value,
                total_session_minutes,
                difficulty_config,
                enable_cifp_sids,
                manual_sids,
                num_vfr,
                vfr_spawn_locations,
                use_cifp_speeds,
                # Enroute parameters
                num_enroute,
                arrival_airports,
                departure_airports,
                arrival_airport_runways if self.is_enroute_scenario else None,
                departure_airport_runways if self.is_enroute_scenario else None,
                difficulty_config_enroute,
                difficulty_config_arrivals,
                difficulty_config_departures,
                # Mixed scenario separate difficulty configs
                difficulty_departures_config,
                difficulty_arrivals_config
            )

            if not aircraft:
                raise Exception("No aircraft generated")

            # Check for CIFP/waypoint errors and show warning if any occurred
            if hasattr(scenario, 'cifp_waypoint_errors') and scenario.cifp_waypoint_errors:
                error_count = len(scenario.cifp_waypoint_errors)
                error_list = '\n'.join(f"• {err}" for err in scenario.cifp_waypoint_errors[:10])  # Show first 10
                if len(scenario.cifp_waypoint_errors) > 10:
                    error_list += f"\n... and {len(scenario.cifp_waypoint_errors) - 10} more"

                warning_msg = (f"Generation completed with {error_count} waypoint/CIFP error(s).\n"
                              f"These aircraft were skipped:\n\n{error_list}\n\n"
                              f"Check the logs for more details.")

                # Show warning (thread-safe)
                from tkinter import messagebox
                self.after(0, lambda: messagebox.showwarning(
                    "CIFP/Waypoint Warnings",
                    warning_msg
                ))
                logger.warning(f"Generation completed with {error_count} CIFP/waypoint errors")

            # Check for gate assignment warnings and show info dialog if any occurred
            if hasattr(scenario, 'gate_assignment_warnings') and scenario.gate_assignment_warnings:
                warning_count = len(scenario.gate_assignment_warnings)

                # Build detailed message with gate failure reasons
                msg_parts = [scenario.gate_assignment_warnings[0]]  # Main summary line

                # Add detailed failure breakdown if available
                if hasattr(scenario, 'gate_failure_reasons') and scenario.gate_failure_reasons:
                    failures_by_reason = defaultdict(list)
                    for gate, reason in scenario.gate_failure_reasons.items():
                        # Skip "Unknown reason" entries
                        if reason != "Unknown reason":
                            failures_by_reason[reason].append(gate)

                    if failures_by_reason:
                        msg_parts.append("\nGate assignment details:")
                        for reason, gates in sorted(failures_by_reason.items()):
                            gate_list = ', '.join(gates[:10])
                            if len(gates) > 10:
                                gate_list += f" (and {len(gates) - 10} more)"
                            msg_parts.append(f"  • {reason}: {gate_list}")

                warning_msg = '\n'.join(msg_parts)

                # Show info dialog (thread-safe)
                from tkinter import messagebox
                self.after(0, lambda: messagebox.showinfo(
                    "Generation Complete",
                    warning_msg
                ))
                logger.warning(f"Generation completed with {warning_count} gate assignment warnings")

            # Apply preset commands if configured
            preset_command_rules = config.get('preset_command_rules', [])
            if preset_command_rules:
                self._update_progress("Applying preset commands...")
                apply_preset_commands(aircraft, preset_command_rules)
                logger.info(f"Applied {len(preset_command_rules)} preset command rules to aircraft")

            # Update progress
            self._update_progress("Saving vNAS scenario file...")

            # Export as vNAS JSON payload
            if self.is_enroute_scenario and self.artcc_id:
                # For enroute scenarios, use ARTCC ID as the identifier
                scenario_identifier = self.artcc_id
                output_filepath = VNASJSONExporter.export(
                    aircraft,
                    artcc_id=self.artcc_id,
                    scenario_name=None
                )
            else:
                scenario_identifier = self.airport_icao
                output_filepath = VNASJSONExporter.export(
                    aircraft,
                    airport_icao=self.airport_icao,
                    scenario_name=None
                )

            logger.info(f"Successfully generated {len(aircraft)} aircraft")
            logger.info(f"Saved vNAS scenario to: {output_filepath}")

            # Show success (thread-safe)
            self.after(0, lambda: self.screens['generation'].show_success(
                len(aircraft),
                output_filepath,
                aircraft_list=aircraft,
                airport_icao=scenario_identifier
            ))

        except Exception as e:
            logger.exception("Error generating scenario")
            # Show error (thread-safe)
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self.screens['generation'].show_error(msg))

    def _create_scenario(self):
        """Create scenario object based on type"""
        # Check if this is an enroute scenario
        if self.is_enroute_scenario:
            import json
            from pathlib import Path
            # Load config for enroute scenario
            config_path = Path('config.json')
            config = {}
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)

            # Load CIFP/GeoJSON data for configured airports only when generating
            geojson_parsers = {}
            cifp_parsers = {}

            # Get the airports from the stored groups
            if hasattr(self, 'artcc_airport_groups'):
                all_airports = set()
                for group_name, airports_str in self.artcc_airport_groups.items():
                    # Parse each group's airports string
                    if ':' in airports_str:
                        # Has runways specified - parse carefully
                        current_icao = None
                        for entry in airports_str.split(','):
                            entry = entry.strip()
                            if ':' in entry:
                                # New airport entry
                                icao, runway = entry.split(':', 1)
                                current_icao = icao.strip()
                                all_airports.add(current_icao)
                    else:
                        # No runways specified, might be comma-separated list
                        for airport in airports_str.split(','):
                            airport = airport.strip()
                            if airport and len(airport) >= 4:
                                all_airports.add(airport)

                # Load parsers for these airports
                cifp_path = self.airport_data_dir / "FAACIFP18"
                for icao in all_airports:
                    try:
                        # Load GeoJSON if available
                        # Use full ICAO for non-K airports (P, T, C, etc.), strip K for US airports
                        geojson_filename = icao[1:].lower() if icao.startswith('K') else icao.lower()
                        geojson_path = self.airport_data_dir / f"{geojson_filename}.geojson"
                        if geojson_path.exists():
                            geojson_parsers[icao] = GeoJSONParser(str(geojson_path), icao)
                            logger.debug(f"Loaded GeoJSON for {icao}")

                        # Load CIFP
                        if cifp_path.exists():
                            cifp_parsers[icao] = CIFPParser(str(cifp_path), icao)
                            logger.debug(f"Loaded CIFP for {icao}")
                    except Exception as e:
                        logger.warning(f"Could not load data for {icao}: {e}")

            return ArtccEnrouteScenario(
                self.artcc_id, self.api_client, config,
                geojson_parsers=geojson_parsers,
                cifp_parsers=cifp_parsers
            )

        # Prepare cached flights dictionary for airport-based scenarios
        cached_flights = {
            'departures': self.cached_departures,
            'arrivals': self.cached_arrivals
        }

        if self.scenario_type == 'ground_departures':
            return GroundDeparturesScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client, cached_flights
            )
        elif self.scenario_type == 'ground_mixed':
            return GroundMixedScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client, cached_flights
            )
        elif self.scenario_type == 'tower_mixed':
            return TowerMixedScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client, cached_flights
            )
        elif self.scenario_type == 'tracon_arrivals':
            return TraconArrivalsScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client, cached_flights
            )
        elif self.scenario_type == 'tracon_mixed':
            return TraconMixedScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client, cached_flights
            )
        else:
            raise ValueError(f"Unknown scenario type: {self.scenario_type}")

    def _generate_aircraft(self, scenario, num_departures, num_arrivals,
                          active_runways, additional_separation,
                          delay_range, arrival_waypoints, spawn_delay_mode,
                          delay_value, total_session_minutes, difficulty_config=None,
                          enable_cifp_sids=False, manual_sids=None,
                          num_vfr=0, vfr_spawn_locations=None,
                          use_cifp_speeds=True,
                          # Enroute-specific parameters
                          num_enroute=0,
                          arrival_airports=None, departure_airports=None,
                          arrival_airport_runways=None, departure_airport_runways=None,
                          difficulty_config_enroute=None, difficulty_config_arrivals=None,
                          difficulty_config_departures=None,
                          # Mixed scenario separate difficulty configs
                          difficulty_departures_config=None, difficulty_arrivals_config=None):
        """Generate aircraft based on scenario type"""
        # Handle enroute scenario
        if self.is_enroute_scenario:
            return scenario.generate(
                num_enroute=num_enroute,
                num_arrivals=num_arrivals,
                num_departures=num_departures,
                arrival_airports=arrival_airports,
                departure_airports=departure_airports,
                arrival_airport_runways=arrival_airport_runways,
                departure_airport_runways=departure_airport_runways,
                difficulty_config_enroute=difficulty_config_enroute,
                difficulty_config_arrivals=difficulty_config_arrivals,
                difficulty_config_departures=difficulty_config_departures,
                spawn_delay_mode=spawn_delay_mode,
                delay_value=delay_value,
                total_session_minutes=total_session_minutes,
                cached_departures_pool=None,  # Fetched during generation based on selected airports
                cached_arrivals_pool=None,  # Fetched during generation based on selected airports
                cached_transient_pool=self.cached_enroute_transient_pool  # Pre-loaded when ARTCC selected
            )

        # Handle airport-based scenarios
        if self.scenario_type == 'ground_departures':
            return scenario.generate(num_departures, spawn_delay_mode, delay_value,
                                    total_session_minutes, None, difficulty_config,
                                    active_runways, enable_cifp_sids, manual_sids)
        elif self.scenario_type == 'ground_mixed':
            # Note: ground_mixed doesn't support VFR aircraft yet
            return scenario.generate(num_departures, num_arrivals, active_runways,
                                    additional_separation, spawn_delay_mode, delay_value,
                                    total_session_minutes, None, difficulty_config,
                                    enable_cifp_sids, manual_sids,
                                    difficulty_departures_config, difficulty_arrivals_config)
        elif self.scenario_type == 'tower_mixed':
            return scenario.generate(num_departures, num_arrivals, active_runways,
                                    additional_separation, spawn_delay_mode, delay_value,
                                    total_session_minutes, None, difficulty_config,
                                    enable_cifp_sids, manual_sids,
                                    num_vfr, vfr_spawn_locations,
                                    difficulty_departures_config, difficulty_arrivals_config)
        elif self.scenario_type == 'tracon_arrivals':
            return scenario.generate(num_arrivals, arrival_waypoints,
                                    delay_range, spawn_delay_mode, delay_value,
                                    total_session_minutes, None, difficulty_config, active_runways,
                                    use_cifp_speeds)
        elif self.scenario_type == 'tracon_mixed':
            return scenario.generate(num_departures, num_arrivals, arrival_waypoints,
                                    delay_range, spawn_delay_mode,
                                    delay_value, total_session_minutes, None,
                                    difficulty_config, active_runways, enable_cifp_sids, manual_sids,
                                    use_cifp_speeds, num_vfr, vfr_spawn_locations,
                                    difficulty_departures_config, difficulty_arrivals_config)
        else:
            raise ValueError(f"Unknown scenario type: {self.scenario_type}")

    def reset(self):
        """Reset application state and return to first screen"""
        self.airport_icao = None
        self.scenario_type = None
        self.geojson_parser = None
        self.cifp_parser = None
        self.show_screen('airport')

    def quit_app(self):
        """Quit the application"""
        self.quit()
        self.destroy()
