"""
Main application window and controller
"""
import tkinter as tk
import logging
import threading
from pathlib import Path
from gui.theme import DarkTheme
from gui.screens.airport_selection import AirportSelectionScreen
from gui.screens.scenario_type_selection import ScenarioTypeSelectionScreen
from gui.screens.scenario_config import ScenarioConfigScreen
from gui.screens.generation_screen import GenerationScreen

from parsers.geojson_parser import GeoJSONParser
from parsers.cifp_parser import CIFPParser
from utils.api_client import FlightDataAPIClient
from generators.backup_scenario_generator import BackupScenarioGenerator

from scenarios.ground_departures import GroundDeparturesScenario
from scenarios.ground_mixed import GroundMixedScenario
from scenarios.tower_mixed import TowerMixedScenario
from scenarios.tracon_departures import TraconDeparturesScenario
from scenarios.tracon_arrivals import TraconArrivalsScenario
from scenarios.tracon_mixed import TraconMixedScenario
from models.spawn_delay_mode import SpawnDelayMode

logger = logging.getLogger(__name__)


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

        # Cached flight data
        self.cached_departures = []
        self.cached_arrivals = []
        self.flight_cache_timestamp = None

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

    def load_airport_data(self, airport_icao):
        """Load airport data in a background thread"""
        # Run loading in a separate thread
        loading_thread = threading.Thread(target=self._load_airport_data_thread, args=(airport_icao,), daemon=True)
        loading_thread.start()

    def _load_airport_data_thread(self, airport_icao):
        """Load airport data (runs in separate thread)"""
        try:
            import time
            self.airport_icao = airport_icao
            logger.info(f"Selected airport: {airport_icao}")

            # Load GeoJSON data
            logger.info("Loading GeoJSON data...")
            geojson_path = self.airport_data_dir / f"{airport_icao[1:].lower()}.geojson"
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

            # Load flight data from API in parallel
            logger.info("Pre-loading flight data from API...")
            self._preload_flight_data(airport_icao)

            # Hide loading and show next screen (thread-safe)
            self.after(0, self._on_airport_data_loaded)

        except Exception as e:
            logger.error(f"Error loading airport data: {e}")
            # Show error (thread-safe)
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self._on_airport_data_error(msg))

    def _preload_flight_data(self, airport_icao):
        """Pre-load flight data from API (called from background thread)"""
        import time
        import threading

        # Containers for results
        departures_result = [None]
        arrivals_result = [None]

        def fetch_departures():
            try:
                logger.info(f"Fetching 200 departures from {airport_icao}...")
                departures_result[0] = self.api_client.fetch_departures(airport_icao, limit=200)
                logger.info(f"Fetched {len(departures_result[0]) if departures_result[0] else 0} departures")
            except Exception as e:
                logger.error(f"Error fetching departures: {e}")
                departures_result[0] = []

        def fetch_arrivals():
            try:
                logger.info(f"Fetching 200 arrivals to {airport_icao}...")
                arrivals_result[0] = self.api_client.fetch_arrivals(airport_icao, limit=200)
                logger.info(f"Fetched {len(arrivals_result[0]) if arrivals_result[0] else 0} arrivals")
            except Exception as e:
                logger.error(f"Error fetching arrivals: {e}")
                arrivals_result[0] = []

        # Start both threads
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

        logger.info(f"Flight data pre-loading complete: {len(self.cached_departures)} departures, {len(self.cached_arrivals)} arrivals")

    def _on_airport_data_loaded(self):
        """Called when airport data is loaded successfully"""
        self.screens['airport'].hide_loading()
        self.show_screen('scenario_type')

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
            if config.get('enable_difficulty'):
                easy_count = int(config.get('difficulty_easy', 0) or 0)
                medium_count = int(config.get('difficulty_medium', 0) or 0)
                hard_count = int(config.get('difficulty_hard', 0) or 0)

                difficulty_config = {
                    'easy': easy_count,
                    'medium': medium_count,
                    'hard': hard_count
                }

                # When difficulty is enabled, calculate total aircraft from difficulty counts
                total_aircraft = easy_count + medium_count + hard_count

                # Split aircraft based on scenario type
                if self.scenario_type in ['ground_mixed', 'tower_mixed', 'tracon_mixed']:
                    # Mixed scenarios: split evenly between departures and arrivals
                    num_departures = total_aircraft // 2
                    num_arrivals = total_aircraft - num_departures  # Gives remainder to arrivals if odd
                elif self.scenario_type == 'tracon_arrivals':
                    # Arrivals-only scenario
                    num_departures = 0
                    num_arrivals = total_aircraft
                else:
                    # Departure-only scenarios (ground_departures, tracon_departures)
                    num_departures = total_aircraft
                    num_arrivals = 0
            else:
                # Parse manual configuration
                num_departures = int(config.get('num_departures', 0)) if config.get('num_departures') else 0
                num_arrivals = int(config.get('num_arrivals', 0)) if config.get('num_arrivals') else 0

            # Parse runways
            active_runways = []
            if config.get('active_runways'):
                active_runways = [r.strip() for r in config['active_runways'].split(',')]

            # Parse separation range
            separation_range = (3, 6)
            if config.get('separation_range'):
                try:
                    parts = config['separation_range'].split('-')
                    separation_range = (int(parts[0]), int(parts[1]))
                except:
                    pass

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
                separation_range,
                delay_range,
                arrival_waypoints,
                spawn_delay_mode,
                delay_value,
                total_session_minutes,
                difficulty_config,
                enable_cifp_sids,
                manual_sids,
                num_vfr,
                vfr_spawn_locations
            )

            if not aircraft:
                raise Exception("No aircraft generated")

            # Update progress
            self._update_progress("Saving backup scenario file...")

            # Auto-generate backup scenario filename based on airport
            output_filename = f"{self.airport_icao}_scenario_backup.txt"

            generator = BackupScenarioGenerator(output_filename)
            generator.add_aircraft_list(aircraft)
            generator.generate()

            logger.info(f"Successfully generated {len(aircraft)} aircraft")
            logger.info(f"Saved backup scenario to: {output_filename}")

            # Show success (thread-safe)
            self.after(0, lambda: self.screens['generation'].show_success(
                len(aircraft),
                output_filename,
                aircraft_list=aircraft,
                airport_icao=self.airport_icao
            ))

        except Exception as e:
            logger.exception("Error generating scenario")
            # Show error (thread-safe)
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self.screens['generation'].show_error(msg))

    def _create_scenario(self):
        """Create scenario object based on type"""
        # Prepare cached flights dictionary
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
        elif self.scenario_type == 'tracon_departures':
            return TraconDeparturesScenario(
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
                          active_runways, separation_range,
                          delay_range, arrival_waypoints, spawn_delay_mode,
                          delay_value, total_session_minutes, difficulty_config=None,
                          enable_cifp_sids=False, manual_sids=None,
                          num_vfr=0, vfr_spawn_locations=None):
        """Generate aircraft based on scenario type"""
        if self.scenario_type == 'ground_departures':
            return scenario.generate(num_departures, spawn_delay_mode, delay_value,
                                    total_session_minutes, None, difficulty_config,
                                    active_runways, enable_cifp_sids, manual_sids)
        elif self.scenario_type == 'ground_mixed':
            # Note: ground_mixed doesn't support VFR aircraft yet
            return scenario.generate(num_departures, num_arrivals, active_runways,
                                    spawn_delay_mode, delay_value, total_session_minutes,
                                    None, difficulty_config, enable_cifp_sids, manual_sids)
        elif self.scenario_type == 'tower_mixed':
            return scenario.generate(num_departures, num_arrivals, active_runways,
                                    separation_range, spawn_delay_mode, delay_value,
                                    total_session_minutes, None, difficulty_config,
                                    enable_cifp_sids, manual_sids,
                                    num_vfr, vfr_spawn_locations)
        elif self.scenario_type == 'tracon_departures':
            return scenario.generate(num_departures, active_runways, spawn_delay_mode,
                                    delay_value, total_session_minutes, None, difficulty_config,
                                    enable_cifp_sids, manual_sids)
        elif self.scenario_type == 'tracon_arrivals':
            return scenario.generate(num_arrivals, arrival_waypoints,
                                    delay_range, spawn_delay_mode, delay_value,
                                    total_session_minutes, None, difficulty_config, active_runways)
        elif self.scenario_type == 'tracon_mixed':
            return scenario.generate(num_departures, num_arrivals, arrival_waypoints,
                                    delay_range, spawn_delay_mode,
                                    delay_value, total_session_minutes, None,
                                    difficulty_config, active_runways, enable_cifp_sids, manual_sids)
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
