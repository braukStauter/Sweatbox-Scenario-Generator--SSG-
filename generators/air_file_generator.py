"""
Generator for .air files
"""
import logging
from typing import List
from models.aircraft import Aircraft

logger = logging.getLogger(__name__)


class AirFileGenerator:
    """Generator for vNAS .air files"""

    def __init__(self, output_path: str):
        """
        Initialize the generator

        Args:
            output_path: Path where the .air file will be saved
        """
        self.output_path = output_path
        self.aircraft: List[Aircraft] = []

    def add_aircraft(self, aircraft: Aircraft):
        """
        Add an aircraft to the scenario

        Args:
            aircraft: Aircraft object to add
        """
        self.aircraft.append(aircraft)

    def add_aircraft_list(self, aircraft_list: List[Aircraft]):
        """
        Add multiple aircraft to the scenario

        Args:
            aircraft_list: List of Aircraft objects
        """
        self.aircraft.extend(aircraft_list)

    def generate(self) -> str:
        """
        Generate the .air file

        Returns:
            Path to the generated file
        """
        try:
            with open(self.output_path, 'w') as f:
                # Write header comment
                f.write("; vNAS Sweatbox Scenario File\n")
                f.write(f"; Generated with Sweatbox Scenario Generator\n")
                f.write(f"; Total aircraft: {len(self.aircraft)}\n\n")

                # Write each aircraft
                for aircraft in self.aircraft:
                    line = aircraft.to_air_line()
                    f.write(line + '\n')

            logger.info(f"Generated .air file with {len(self.aircraft)} aircraft at {self.output_path}")
            return self.output_path

        except Exception as e:
            logger.error(f"Error generating .air file: {e}")
            raise

    def clear(self):
        """Clear all aircraft from the generator"""
        self.aircraft.clear()
