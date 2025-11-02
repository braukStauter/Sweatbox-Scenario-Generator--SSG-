===============================================================================
  Sweatbox Scenario Generator (SSG) - Installation & Usage Guide
===============================================================================

Thank you for downloading the Sweatbox Scenario Generator!

-------------------------------------------------------------------------------
  INSTALLATION
-------------------------------------------------------------------------------

Simply extract or copy this entire folder to any location on your computer.
No Python installation required!

-------------------------------------------------------------------------------
  FOLDER STRUCTURE
-------------------------------------------------------------------------------

Your distribution folder should contain:
  - SSG.exe           : Main application executable
  - config.json       : Configuration file for parking airline preferences
  - airport_data/     : Folder containing airport data files
  - README.txt        : This file

-------------------------------------------------------------------------------
  AIRPORT DATA SETUP
-------------------------------------------------------------------------------

To use SSG with an airport, you need to add the following files to the
airport_data folder:

1. GeoJSON file: Contains airport layout (taxiways, runways, parking spots)
   Format: [AIRPORT_ICAO].geojson
   Example: KPHX.geojson

2. CIFP file: Contains navigation procedures and waypoints
   Format: [AIRPORT_ICAO]_CIFP.txt
   Example: KPHX_CIFP.txt

Place both files directly in the airport_data folder.

-------------------------------------------------------------------------------
  CONFIGURATION
-------------------------------------------------------------------------------

The config.json file allows you to configure parking airline preferences:

{
  "parking_airlines": {
    "KPHX": {
      "A#": ["AAL"],       // Parking A1-A99 for American Airlines
      "B#": ["AAL"],       // Parking B1-B99 for American Airlines
      "C#": ["SWA"],       // Parking C1-C99 for Southwest
      "F1": ["JBU"]        // Specific parking F1 for JetBlue
    }
  }
}

Use "#" as a wildcard (e.g., "A#" matches A1, A2, A10, etc.)
Specific parking names override wildcards.

-------------------------------------------------------------------------------
  RUNNING THE APPLICATION
-------------------------------------------------------------------------------

1. Double-click SSG.exe to launch the application
2. The application will check for updates on startup
3. Follow the on-screen wizard to generate your scenarios

-------------------------------------------------------------------------------
  LOGS
-------------------------------------------------------------------------------

Application logs are saved to the "logs" folder (created automatically)
Check logs if you encounter any issues.

-------------------------------------------------------------------------------
  SUPPORT & ISSUES
-------------------------------------------------------------------------------

For bug reports and feature requests, please visit:
https://github.com/[your-repo-here]

===============================================================================
