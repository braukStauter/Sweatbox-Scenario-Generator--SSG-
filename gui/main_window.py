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
from utils.api_client import FlightPlanAPIClient
from generators.air_file_generator import AirFileGenerator

from scenarios.ground_departures import GroundDeparturesScenario
from scenarios.ground_mixed import GroundMixedScenario
from scenarios.tower_mixed import TowerMixedScenario
from scenarios.tracon_departures import TraconDeparturesScenario
from scenarios.tracon_arrivals import TraconArrivalsScenario
from scenarios.tracon_mixed import TraconMixedScenario

logger = logging.getLogger(__name__)


class MainWindow(tk.Tk):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("vNAS Sweatbox Scenario Generator")
        self.geometry("900x700")
        self.minsize(800, 600)
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
        self.api_client = FlightPlanAPIClient()
        self.airport_data_dir = Path("airport_data")

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

            # Hide loading and show next screen (thread-safe)
            self.after(0, self._on_airport_data_loaded)

        except Exception as e:
            logger.error(f"Error loading airport data: {e}")
            # Show error (thread-safe)
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self._on_airport_data_error(msg))

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

            # Parse configuration
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

            # Parse altitude range
            altitude_range = (7000, 18000)
            if config.get('altitude_range'):
                try:
                    parts = config['altitude_range'].split('-')
                    altitude_range = (int(parts[0]), int(parts[1]))
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

            # Parse waypoints
            arrival_waypoints = []
            if config.get('arrival_waypoints'):
                arrival_waypoints = [w.strip().upper() for w in config['arrival_waypoints'].split(',')]

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
                altitude_range,
                delay_range,
                arrival_waypoints
            )

            if not aircraft:
                raise Exception("No aircraft generated")

            # Update progress
            self._update_progress("Saving to file...")

            # Save to file
            output_filename = config.get('output_filename') or f"{self.airport_icao}_scenario.air"
            if not output_filename.endswith('.air'):
                output_filename += '.air'

            generator = AirFileGenerator(output_filename)
            generator.add_aircraft_list(aircraft)
            generator.generate()

            logger.info(f"Successfully generated {len(aircraft)} aircraft")
            logger.info(f"Saved to: {output_filename}")

            # Show success (thread-safe)
            self.after(0, lambda: self.screens['generation'].show_success(len(aircraft), output_filename))

        except Exception as e:
            logger.exception("Error generating scenario")
            # Show error (thread-safe)
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self.screens['generation'].show_error(msg))

    def _create_scenario(self):
        """Create scenario object based on type"""
        if self.scenario_type == 'ground_departures':
            return GroundDeparturesScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
            )
        elif self.scenario_type == 'ground_mixed':
            return GroundMixedScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
            )
        elif self.scenario_type == 'tower_mixed':
            return TowerMixedScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
            )
        elif self.scenario_type == 'tracon_departures':
            return TraconDeparturesScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
            )
        elif self.scenario_type == 'tracon_arrivals':
            return TraconArrivalsScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
            )
        elif self.scenario_type == 'tracon_mixed':
            return TraconMixedScenario(
                self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
            )
        else:
            raise ValueError(f"Unknown scenario type: {self.scenario_type}")

    def _generate_aircraft(self, scenario, num_departures, num_arrivals,
                          active_runways, separation_range, altitude_range,
                          delay_range, arrival_waypoints):
        """Generate aircraft based on scenario type"""
        if self.scenario_type == 'ground_departures':
            return scenario.generate(num_departures)
        elif self.scenario_type == 'ground_mixed':
            return scenario.generate(num_departures, num_arrivals, active_runways)
        elif self.scenario_type == 'tower_mixed':
            return scenario.generate(num_departures, num_arrivals, active_runways, separation_range)
        elif self.scenario_type == 'tracon_departures':
            return scenario.generate(num_departures, active_runways)
        elif self.scenario_type == 'tracon_arrivals':
            return scenario.generate(num_arrivals, arrival_waypoints, altitude_range, delay_range)
        elif self.scenario_type == 'tracon_mixed':
            return scenario.generate(num_departures, num_arrivals, arrival_waypoints, altitude_range, delay_range)
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
