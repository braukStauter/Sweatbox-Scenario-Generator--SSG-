# vNAS Sweatbox Scenario Generator

A production-ready Python application with a modern graphical interface for generating realistic air traffic control simulation scenarios for vNAS Data Admin Sweatbox files.

> **Note:** This application now uses a graphical user interface (GUI) exclusively for the best user experience.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Prepare your airport data:**
   - Place your airport's GeoJSON file in `airport_data/`
   - Add CIFP file (FAACIFP18) for TRACON scenarios

3. **Launch the application:**
   ```bash
   python main.py
   ```

4. **Follow the GUI workflow:**
   - Select airport → Choose scenario → Configure → Generate!

## Features

- **Modern Dark-Themed GUI**: Beautiful, user-friendly graphical interface with step-by-step workflow
- **Multiple Scenario Types**: Ground, Tower, and TRACON operations with departures and/or arrivals
- **Realistic Flight Plans**: Integrates with flight-plans.csko.hu API for authentic routing, callsigns, and aircraft types
- **Parking-Specific Airlines**: Configure specific airlines for parking spots with wildcard support (e.g., "A#" for all A gates)
- **GA Aircraft Support**: Automatic N-number callsigns, low-altitude routes, and less-common airports for GA parking
- **Authentic Callsigns**: Uses real-world callsigns from flight plan API matching airline and equipment
- **Equipment Suffixes**: Aircraft types include proper equipment suffixes (e.g., B738/L, C172/G)
- **Dynamic Airport Elevation**: Automatically fetches accurate field elevation from FlightRadar24 API
- **Airport Data Integration**: Parses GeoJSON files for parking spots, runways, and airport geometry
- **CIFP Support**: Reads FAA CIFP data for waypoint information and arrival procedures
- **Intelligent Aircraft Placement**: Proper spacing, altitude restrictions, and realistic positioning
- **3-Degree Glideslope**: Arrival aircraft positioned on proper glideslope relative to field elevation
- **Flexible Configuration**: Customizable parameters for each scenario type

## Scenario Types

1. **Ground (Departures)**: Generate departure aircraft at parking spots
2. **Ground (Departures/Arrivals)**: Mix of ground departures and arriving aircraft on final approach
3. **Tower (Departures/Arrivals)**: Tower operations with departures, including GA traffic, and arrivals with customizable spacing
4. **TRACON (Departures)**: Departure aircraft at parking ready for tower handoff
5. **TRACON (Arrivals)**: Arrival aircraft spawned at designated waypoints with altitude restrictions
6. **TRACON (Departures/Arrivals)**: Combined TRACON operations with both departures and arrivals

## Installation

1. Install Python 3.8 or higher

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure your airport data is set up in the `airport_data/` directory:
   - `[AIRPORT].geojson` - Airport GeoJSON file with parking and runway data
   - `FAACIFP18` - FAA CIFP file for waypoint and procedure data
   - `CIFP Readme 2510.pdf` - CIFP decode instructions (optional, for reference)

## Usage

Launch the application:
```bash
python main.py
```

Or alternatively:
```bash
python main_gui.py
```

### GUI Workflow

The intuitive graphical interface guides you through four simple steps:

1. **Select Airport** - Choose your primary airport from available GeoJSON files
2. **Choose Scenario Type** - Select from six different scenario types:
   - Ground (Departures)
   - Ground (Departures/Arrivals)
   - Tower (Departures/Arrivals)
   - TRACON (Departures)
   - TRACON (Arrivals)
   - TRACON (Departures/Arrivals)
3. **Configure Parameters** - Set aircraft counts, runways, waypoints, etc. with helpful examples
4. **Generate** - Watch the progress and get your `.air` file

The application features:
- Clean, dark-themed interface
- Step-by-step workflow with progress tracking
- Visual feedback and validation
- Built-in help text and examples
- Mouse wheel scrolling support
- Automatic error handling

> **Legacy CLI:** A command-line version is available in `main_cli_legacy.py` for advanced users, but the GUI is the recommended interface.

## Configuration

### Parking-Specific Airlines

Create a `config.json` file to assign specific airlines to parking spots:

```json
{
  "parking_airlines": {
    "KPHX": {
      "A#": ["AAL", "AAL", "AAL"],
      "B#": ["SWA", "SWA", "SWA"],
      "C#": ["UAL", "UAL", "UAL"],
      "E1": ["JBU"]
    }
  }
}
```

**Wildcard Support:**
- Use `#` to match multiple parking spots
- `A#` matches `A1`, `A2`, `A3`, `A10`, `A11`, etc.
- Specific names override wildcards (e.g., `A1` overrides `A#`)

**Airline Weighting:**
- Repeat airline codes to increase probability
- `["AAL", "AAL", "DAL"]` = 67% AAL, 33% DAL

### GA (General Aviation) Parking

Parking spots with "GA" in the name automatically:
- Generate N-number callsigns (e.g., N123AB)
- Use GA aircraft types (C172, C182, PA28, etc.)
- Route to less-common airports
- Fly at lower altitudes (3000-8000 feet)

## Airport Data Format

### GeoJSON File Structure

Your airport GeoJSON file should contain features for parking spots and runways:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "type": "parking",
        "name": "B26",
        "heading": 140
      },
      "geometry": {
        "type": "Point",
        "coordinates": [-111.994765, 33.437938]
      }
    },
    {
      "type": "Feature",
      "properties": {
        "type": "runway",
        "name": "7L - 25R",
        "threshold": "1105 - 1130"
      },
      "geometry": {
        "type": "LineString",
        "coordinates": [...]
      }
    }
  ]
}
```

### CIFP File

Place the FAA CIFP file (FAACIFP18) in the `airport_data/` directory. The application will automatically parse waypoint and arrival procedure information.

## Generated .air File Format

The output file follows the vNAS format:
```
Callsign:Type:Engine:Rules:Dep Field:Arr Field:Crz Alt:Route:Remarks:Sqk Code:Sqk Mode:Lat:Lon:Alt:Speed:Heading
```

Example:
```
AAL2566:B738/L:J:I:KPHX:KLAX:35000:KEENS3 WLVRN ESTWD HLYWD1::1200:N:33.437938:-111.994765:1135:0:140
DAL2589:A320/L:J:I:KLAS:KPHX:33000:CUTLA2.MAIER::1200:N:33.445123:-112.001234:2800:140:70
N123AB:C172/G:P:V:::::1200:N:33.437938:-111.994765:1135:0:140
```

Fields:
- **Callsign**: Aircraft callsign from flight plan API (e.g., AAL2566, SWA1934) or N-number for GA
  - GA N-numbers: N + 3 digits + 2 letters (e.g., N123AB, N994LU)
  - Always exactly 6 characters
- **Type**: Aircraft type ICAO code with equipment suffix (e.g., B738/L, A320/L, C172/G)
  - /L = RNAV capable (most modern jets)
  - /G = GPS equipped (most GA aircraft)
- **Engine**: Engine type (J for jet, P for prop)
- **Rules**: Flight rules (I for IFR, V for VFR)
- **Dep Field**: Departure airport ICAO
- **Arr Field**: Arrival airport ICAO
- **Crz Alt**: Cruise altitude in MSL feet (e.g., 35000 for FL350)
- **Route**: Flight route from real-world flight plans
- **Remarks**: Any remarks
- **Sqk Code**: Squawk code (transponder code, default 1200)
- **Sqk Mode**: Squawk mode (N for Normal - default, S for Standby)
- **Lat**: Latitude in decimal degrees
- **Lon**: Longitude in decimal degrees
- **Alt**: Current altitude MSL in feet
- **Speed**: Ground speed in knots
- **Heading**: Magnetic heading in degrees

## Architecture

The application is organized into modular components:

### Backend Components
- **models/**: Data models for aircraft, airports, and waypoints
- **parsers/**: GeoJSON and CIFP file parsers
- **scenarios/**: Scenario generators for each type
- **generators/**: .air file generator
- **utils/**: Geographic calculations, API client, and constants

### GUI Components
- **gui/**: Graphical user interface package
  - **theme.py**: Dark theme configuration and styling
  - **widgets.py**: Reusable custom GUI widgets
  - **splash_screen.py**: Application splash screen
  - **main_window.py**: Main application window and controller
  - **screens/**: Individual GUI screens (airport selection, scenario config, etc.)

## API Integration

The application integrates with two external APIs:

1. **Flight Plans API** (flight-plans.csko.hu): Fetches realistic flight plan data including:
   - Real-world callsigns (e.g., SWA1934, AAL2566)
   - Aircraft types with equipment qualifiers (B738/L, A320/L)
   - Actual routing used by airlines
   - Cruise altitudes

   Falls back to generated data if unavailable.

2. **FlightRadar24 API**: Automatically fetches accurate airport field elevations for any airport worldwide. This ensures:
   - Ground aircraft spawn at correct field elevation
   - Arrival aircraft follow proper 3-degree glideslope
   - Altitudes are accurate MSL values

   Falls back to 1000 ft MSL default if API is unavailable.

## Requirements

- Python 3.8+
- See `requirements.txt` for all dependencies:
  - requests (for API calls)
  - Pillow (for GUI logo display)
- Airport GeoJSON data
- FAA CIFP data (optional, required for TRACON arrival scenarios)

Install all requirements:
```bash
pip install -r requirements.txt
```

## Logging

The application includes comprehensive logging. Logs are output to the console and include:
- Data loading information
- Aircraft generation progress
- API call results
- Warnings and errors

## Error Handling

The application includes robust error handling for:
- Missing or invalid airport data
- API failures with fallback generation
- Invalid user input
- File I/O errors

## Notes

- Aircraft altitudes are specified in MSL (Mean Sea Level), including ground aircraft
- Ground aircraft have ground_speed set to 0
- Arrival aircraft are positioned with realistic spacing and altitude profiles
- TRACON arrival aircraft respect waypoint altitude restrictions when available
- Callsigns can include number suffixes for easy grouping (e.g., AAL2566, DAL2589 both spawn over the same waypoint)

## Troubleshooting

**GUI doesn't start:**
- Ensure Pillow is installed: `pip install Pillow`
- Check Python version is 3.8 or higher
- Verify tkinter is available: `python -m tkinter`

**No airports showing:**
- Verify GeoJSON files exist in `airport_data/`
- Check file naming: `{airport}.geojson` (e.g., `phx.geojson`)

**No waypoints found:**
- Ensure CIFP file (FAACIFP18) is in `airport_data/`
- Required for TRACON arrival scenarios

**API timeout:**
- Application automatically falls back to generated routing
- Internet connection required for real flight plans

**Too many departures:**
- Number of aircraft cannot exceed available parking spots
- The GUI will show an error if you exceed the limit

**Generation fails:**
- Check console output for detailed error messages
- Ensure runway names match those in your GeoJSON file
- Verify waypoint names are correct

## License

This application is provided as-is for air traffic control training and simulation purposes.

## Credits

**Developed by Creative Shrimp™ (Ethan M) for ZAB**

Special thanks to:
- Flight plan data from flight-plans.csko.hu
- vNAS format documentation from twrtrainer.rosscarlson.dev

---

For questions, support, or feature requests, please contact Creative Shrimp™.
