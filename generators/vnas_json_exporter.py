"""
vNAS JSON Exporter
Exports scenarios in the exact JSON format sent to vNAS
"""
import json
import logging
from typing import List
from datetime import datetime
from models.aircraft import Aircraft
from utils.vnas_converter import VNASConverter

logger = logging.getLogger(__name__)


class VNASJSONExporter:
    """Export scenarios as vNAS JSON payloads"""

    @staticmethod
    def export(
        aircraft_list: List[Aircraft],
        airport_icao: str = None,
        artcc_id: str = None,
        scenario_name: str = None,
        output_dir: str = "."
    ) -> str:
        """
        Export scenario as vNAS JSON file

        Args:
            aircraft_list: List of Aircraft objects
            airport_icao: Airport ICAO code (e.g., "KPHX")
            artcc_id: ARTCC identifier for enroute scenarios (e.g., "ZLA")
            scenario_name: Custom scenario name
            output_dir: Directory to save the file

        Returns:
            Path to the generated JSON file
        """
        # Determine identifier and scenario name
        if artcc_id:
            identifier = artcc_id
            default_name = f"Enroute Scenario - {artcc_id}"
        elif airport_icao:
            identifier = airport_icao
            default_name = f"Generated Scenario - {airport_icao}"
        else:
            identifier = "UNKNOWN"
            default_name = "Generated Scenario"

        # Use provided scenario name or default
        final_scenario_name = scenario_name or default_name

        # Generate simplified filename: {3-letter code}_{day}{hour}{minute}.json
        now = datetime.now()
        day = now.strftime("%d")     # Day of month (01-31)
        hour = now.strftime("%H")    # Hour (00-23)
        minute = now.strftime("%M")  # Minute (00-59)

        # Remove K prefix for US airports to get 3-letter code
        if identifier.startswith('K') and len(identifier) == 4:
            short_id = identifier[1:]
        else:
            short_id = identifier

        filename = f"{short_id}_{day}{hour}{minute}.json"
        filepath = f"{output_dir}/{filename}"

        # Create vNAS converter
        if airport_icao:
            converter = VNASConverter(airport_icao, final_scenario_name, artcc_id)
        else:
            # For enroute scenarios without a primary airport
            # Use a dummy airport code (vNAS will handle it)
            converter = VNASConverter("KZZZ", final_scenario_name, artcc_id)

        # Convert aircraft list to vNAS scenario JSON
        scenario_json = converter.create_vnas_scenario(aircraft_list)

        # Write JSON file with nice formatting
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(scenario_json, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported vNAS JSON scenario: {filepath}")
        return filepath

    @staticmethod
    def load(filepath: str) -> dict:
        """
        Load a vNAS JSON scenario file

        Args:
            filepath: Path to the JSON file

        Returns:
            The scenario JSON dictionary
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            scenario_json = json.load(f)

        logger.info(f"Loaded vNAS JSON scenario: {filepath}")
        return scenario_json
