"""
vNAS Sweatbox Scenario Generator

Main entry point for the application
"""
import os
import sys
import logging
from pathlib import Path

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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


class SweatboxScenarioGenerator:
    """Main application class"""

    SCENARIO_TYPES = {
        "1": "Ground (Departures)",
        "2": "Ground (Departures/Arrivals)",
        "3": "Tower (Departures/Arrivals)",
        "4": "TRACON (Departures)",
        "5": "TRACON (Arrivals)",
        "6": "TRACON (Departures/Arrivals)"
    }

    def __init__(self):
        self.airport_data_dir = Path("airport_data")
        self.api_client = FlightPlanAPIClient()
        self.geojson_parser = None
        self.cifp_parser = None
        self.airport_icao = None

    def run(self):
        """Main application loop"""
        print("=" * 60)
        print("vNAS Sweatbox Scenario Generator")
        print("=" * 60)
        print()

        # Step 1: Select airport
        self.select_airport()

        # Step 2: Select scenario type
        scenario_type = self.select_scenario_type()

        # Step 3: Generate scenario based on type
        aircraft = self.generate_scenario(scenario_type)

        if not aircraft:
            print("No aircraft generated. Exiting.")
            return

        # Step 4: Save to .air file
        output_filename = self.get_output_filename()
        self.save_scenario(aircraft, output_filename)

        print()
        print("=" * 60)
        print(f"Successfully generated scenario with {len(aircraft)} aircraft!")
        print(f"Output file: {output_filename}")
        print("=" * 60)

    def select_airport(self):
        """Select and load airport data"""
        print("Step 1: Select Primary Airport")
        print("-" * 60)

        # Find all GeoJSON files in airport_data directory
        geojson_files = list(self.airport_data_dir.glob("*.geojson"))

        if not geojson_files:
            print("ERROR: No GeoJSON files found in airport_data directory!")
            sys.exit(1)

        if len(geojson_files) == 1:
            # Only one airport available, use it
            geojson_path = geojson_files[0]
            self.airport_icao = "K" + geojson_path.stem.upper()
            print(f"Using airport: {self.airport_icao}")
        else:
            # Multiple airports, let user choose
            print("Available airports:")
            for i, gj_file in enumerate(geojson_files, 1):
                icao = "K" + gj_file.stem.upper()
                print(f"  {i}. {icao}")

            while True:
                try:
                    choice = int(input("Select airport (number): "))
                    if 1 <= choice <= len(geojson_files):
                        geojson_path = geojson_files[choice - 1]
                        self.airport_icao = "K" + geojson_path.stem.upper()
                        break
                    else:
                        print("Invalid choice. Try again.")
                except ValueError:
                    print("Please enter a number.")

        # Load airport data
        print(f"\nLoading airport data for {self.airport_icao}...")

        try:
            self.geojson_parser = GeoJSONParser(str(geojson_path), self.airport_icao)
            print(f"  Loaded {len(self.geojson_parser.get_parking_spots())} parking spots")
            print(f"  Loaded {len(self.geojson_parser.get_runways())} runways")
            print(f"  Field elevation: {self.geojson_parser.field_elevation} ft MSL")

            # Load CIFP data
            cifp_path = self.airport_data_dir / "FAACIFP18"
            if cifp_path.exists():
                self.cifp_parser = CIFPParser(str(cifp_path), self.airport_icao)
                print(f"  Loaded {len(self.cifp_parser.get_all_waypoints())} waypoints from CIFP")
            else:
                print("  WARNING: CIFP file not found. TRACON arrival scenarios may not work.")
                self.cifp_parser = None

        except Exception as e:
            print(f"ERROR loading airport data: {e}")
            sys.exit(1)

        print()

    def select_scenario_type(self) -> str:
        """Select scenario type"""
        print("Step 2: Select Scenario Type")
        print("-" * 60)

        for key, name in self.SCENARIO_TYPES.items():
            print(f"  {key}. {name}")

        while True:
            choice = input("\nSelect scenario type (number): ").strip()
            if choice in self.SCENARIO_TYPES:
                print(f"Selected: {self.SCENARIO_TYPES[choice]}")
                print()
                return choice
            else:
                print("Invalid choice. Try again.")

    def generate_scenario(self, scenario_type: str):
        """Generate scenario based on type"""
        print("Step 3: Generate Scenario")
        print("-" * 60)

        try:
            if scenario_type == "1":
                return self._generate_ground_departures()
            elif scenario_type == "2":
                return self._generate_ground_mixed()
            elif scenario_type == "3":
                return self._generate_tower_mixed()
            elif scenario_type == "4":
                return self._generate_tracon_departures()
            elif scenario_type == "5":
                return self._generate_tracon_arrivals()
            elif scenario_type == "6":
                return self._generate_tracon_mixed()
        except Exception as e:
            print(f"ERROR generating scenario: {e}")
            logger.exception("Error generating scenario")
            return None

    def _generate_ground_departures(self):
        """Generate Ground (Departures) scenario"""
        num_departures = self._get_int_input(
            "Number of Departure Aircraft: ",
            max_val=len(self.geojson_parser.get_parking_spots())
        )

        scenario = GroundDeparturesScenario(
            self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
        )

        return scenario.generate(num_departures)

    def _generate_ground_mixed(self):
        """Generate Ground (Departures/Arrivals) scenario"""
        num_departures = self._get_int_input(
            "Number of Departure Aircraft: ",
            max_val=len(self.geojson_parser.get_parking_spots())
        )
        num_arrivals = self._get_int_input("Number of Arrival Aircraft: ")
        active_runways = self._get_runway_input()

        scenario = GroundMixedScenario(
            self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
        )

        return scenario.generate(num_departures, num_arrivals, active_runways)

    def _generate_tower_mixed(self):
        """Generate Tower (Departures/Arrivals) scenario"""
        num_departures = self._get_int_input(
            "Number of Departure Aircraft: ",
            max_val=len(self.geojson_parser.get_parking_spots())
        )
        num_arrivals = self._get_int_input("Number of Arrival Aircraft: ")
        active_runways = self._get_runway_input()

        separation_input = input("Separation interval? [Random between A-B] (default 3-6): ").strip()
        if separation_input:
            try:
                parts = separation_input.split("-")
                separation_range = (int(parts[0]), int(parts[1]))
            except:
                print("Invalid format. Using default 3-6.")
                separation_range = (3, 6)
        else:
            separation_range = (3, 6)

        scenario = TowerMixedScenario(
            self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
        )

        return scenario.generate(num_departures, num_arrivals, active_runways, separation_range)

    def _generate_tracon_departures(self):
        """Generate TRACON (Departures) scenario"""
        num_departures = self._get_int_input("Number of Departure Aircraft: ")
        active_runways = self._get_runway_input()

        scenario = TraconDeparturesScenario(
            self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
        )

        return scenario.generate(num_departures, active_runways)

    def _generate_tracon_arrivals(self):
        """Generate TRACON (Arrivals) scenario"""
        if not self.cifp_parser:
            print("ERROR: CIFP data not available. Cannot generate arrival scenario.")
            return None

        num_arrivals = self._get_int_input("Number of Arrival Aircraft: ")
        arrival_waypoints = self._get_waypoint_input()

        altitude_input = input("Arrival Altitude Min-Max? (default 7000-18000): ").strip()
        if altitude_input:
            try:
                parts = altitude_input.split("-")
                altitude_range = (int(parts[0]), int(parts[1]))
            except:
                print("Invalid format. Using default 7000-18000.")
                altitude_range = (7000, 18000)
        else:
            altitude_range = (7000, 18000)

        delay_input = input("Spawn Delay Min-Max in minutes? (default 4-7): ").strip()
        if delay_input:
            try:
                parts = delay_input.split("-")
                delay_range = (int(parts[0]), int(parts[1]))
            except:
                print("Invalid format. Using default 4-7.")
                delay_range = (4, 7)
        else:
            delay_range = (4, 7)

        scenario = TraconArrivalsScenario(
            self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
        )

        return scenario.generate(num_arrivals, arrival_waypoints, altitude_range, delay_range)

    def _generate_tracon_mixed(self):
        """Generate TRACON (Departures/Arrivals) scenario"""
        if not self.cifp_parser:
            print("ERROR: CIFP data not available. Cannot generate arrival scenario.")
            return None

        num_departures = self._get_int_input(
            "Number of Departure Aircraft: ",
            max_val=len(self.geojson_parser.get_parking_spots())
        )
        num_arrivals = self._get_int_input("Number of Arrival Aircraft: ")
        arrival_waypoints = self._get_waypoint_input()

        altitude_input = input("Arrival Altitude Min-Max? (default 7000-18000): ").strip()
        if altitude_input:
            try:
                parts = altitude_input.split("-")
                altitude_range = (int(parts[0]), int(parts[1]))
            except:
                print("Invalid format. Using default 7000-18000.")
                altitude_range = (7000, 18000)
        else:
            altitude_range = (7000, 18000)

        delay_input = input("Spawn Delay Min-Max in minutes? (default 4-7): ").strip()
        if delay_input:
            try:
                parts = delay_input.split("-")
                delay_range = (int(parts[0]), int(parts[1]))
            except:
                print("Invalid format. Using default 4-7.")
                delay_range = (4, 7)
        else:
            delay_range = (4, 7)

        scenario = TraconMixedScenario(
            self.airport_icao, self.geojson_parser, self.cifp_parser, self.api_client
        )

        return scenario.generate(num_departures, num_arrivals, arrival_waypoints, altitude_range, delay_range)

    def _get_int_input(self, prompt: str, min_val: int = 1, max_val: int = None) -> int:
        """Get integer input from user"""
        while True:
            try:
                value = int(input(prompt))
                if value < min_val:
                    print(f"Value must be at least {min_val}")
                    continue
                if max_val and value > max_val:
                    print(f"Value cannot exceed {max_val}")
                    continue
                return value
            except ValueError:
                print("Please enter a valid number.")

    def _get_runway_input(self) -> list:
        """Get active runway input from user"""
        runways = self.geojson_parser.get_runways()
        print("\nAvailable runways:")
        all_ends = []
        for runway in runways:
            ends = runway.get_runway_ends()
            all_ends.extend(ends)
            print(f"  {ends[0]}, {ends[1]}")

        while True:
            runway_input = input("Active runway(s)? [Comma separated]: ").strip()
            active_runways = [r.strip() for r in runway_input.split(",")]

            # Validate runways
            valid = True
            for rwy in active_runways:
                if rwy not in all_ends:
                    print(f"Invalid runway: {rwy}")
                    valid = False
                    break

            if valid and active_runways:
                return active_runways

    def _get_waypoint_input(self) -> list:
        """Get arrival waypoint input from user"""
        # Show some available waypoints
        waypoints = self.cifp_parser.get_all_waypoints()
        waypoint_names = [wp.name for wp in waypoints if wp.latitude != 0.0 and wp.longitude != 0.0]

        if waypoint_names:
            print(f"\nSome available waypoints: {', '.join(waypoint_names[:10])}...")
        else:
            print("\nWARNING: No waypoints with valid coordinates found in CIFP data.")

        while True:
            waypoint_input = input("Active Arrival Waypoints? [Comma separated]: ").strip()
            waypoints = [w.strip().upper() for w in waypoint_input.split(",")]

            if waypoints:
                return waypoints

    def get_output_filename(self) -> str:
        """Get output filename from user"""
        default_name = f"{self.airport_icao}_scenario.air"
        filename = input(f"\nOutput filename? (default: {default_name}): ").strip()

        if not filename:
            filename = default_name

        if not filename.endswith('.air'):
            filename += '.air'

        return filename

    def save_scenario(self, aircraft, filename: str):
        """Save scenario to .air file"""
        generator = AirFileGenerator(filename)
        generator.add_aircraft_list(aircraft)
        generator.generate()


def main():
    """Main entry point"""
    try:
        app = SweatboxScenarioGenerator()
        app.run()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        logger.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
