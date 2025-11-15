[![Version Image](https://img.shields.io/badge/Stable_Version-1.1.1-Green)](https://github.com/braukStauter/Sweatbox-Scenario-Generator--SSG-/releases) [![Build Image](https://img.shields.io/badge/Build-120-blue)](https://github.com/braukStauter/Sweatbox-Scenario-Generator--SSG-/releases)

(Temporarily, the most up-to-date distribution can be found on the ATCTrainer Discord)
# vNAS Sweatbox Scenario Generator

A standalone desktop application with a modern graphical interface for generating realistic air traffic control simulation scenarios for vNAS Data Admin Sweatbox files.

## Requirements

- Windows 10/11 (64-bit)
- Google Chrome (for vNAS support)
- Internet connection (for flight plan API and auto-updates)
- Access to vNAS Data Admin (for GeoJSON, scenario, and pushing data)
- [CIFP file](https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/cifp/download/) (required for TRACON arrival scenarios; shipped with releases)

## Quick Start

1. **Download the latest release** from [the releases page](https://github.com/braukStauter/Sweatbox-Scenario-Generator--SSG-/releases)

2. **Extract the distribution folder** to any location on your computer

3. **Add your airport data** to the `airport_data/` folder:
   - `[AIRPORT].geojson` (e.g., PHX.geojson). This should be the training airport .geojson, not the tower map.
   - FAA CIFP File (can be downloaded [here](https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/cifp/download/); shipped with releases)

4. **Launch SSG.exe** and follow the GUI workflow:
   - Select airport → Choose scenario → Configure → Generate!
> [!WARNING]
> When pushing a scenario to vNAS Data Admin, be *very* cautious you don't override any existing scenario that you don't want to change. This is unrecoverable.

## Features

- **vNAS Integration**: Directly modify scenarios in vNAS
- **Multiple Scenario Types**: Ground, Tower, and TRACON operations with departures and/or arrivals. Enroute scenarios are supported, but are a large work in progress.
- **Realistic Flight Plans**: Integrates with FAA SWIM data via an internal API for authentic routing, callsigns, and aircraft types
- **Parking-Specific Airlines**: Configure specific airlines for parking spots with wildcard support (e.g., "A#" for all A gates)
- **GA Aircraft Support**: Automatic N-number callsigns, low-altitude routes, and less-common airports for GA parking
- **Airport Data Integration**: Parses GeoJSON files for parking spots, runways, and airport geometry
- **CIFP Support**: Reads FAA CIFP data for waypoint information and arrival procedures
- **Intelligent Aircraft Placement**: Proper spacing, altitude restrictions, and realistic positioning
- **Flexible Configuration**: Customizable parameters for each scenario type

## Scenario Types

1. **Ground (Departures)**: Generate departure aircraft at parking spots
2. **Ground (Departures/Arrivals)**: Mix of ground departures and arriving aircraft on final approach
3. **Tower (Departures/Arrivals)**: Tower operations with departures, including GA traffic, and arrivals
4. **TRACON (Departures)**: Departure aircraft at parking.
5. **TRACON (Arrivals)**: Arrival aircraft spawned at designated waypoints; handles specified arrival routing
6. **TRACON (Departures/Arrivals)**: Combined TRACON operations with both departures and arrivals
7. **Enroute.**

## Installation

1. **Download** the latest release (SSG_Distribution.zip) from the releases page

2. **Extract** the folder to any location on your computer

3. **Add your airport data** to the `airport_data/` folder as specified above

4. **(Optional)** Edit `config.json` to configure airline parking preferences

## Usage

**Simply double-click `SSG.exe` to launch the application!**

## Configuration

### Parking-Specific Airlines

Modify the `config.json` file to assign specific airlines to parking spots:

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

**Gate 'Blocking' Support:**
Mixed Terminal with Overrides:
```json
  "E1-E20": ["ASA", "ACA"],
  "E5": ["JBU"],
  "E10": ["JBU"],
  "E#": ["FFT"]
```
- Most E gates = Alaska/Air Canada
- E5 dedicated to JetBlue
- E10 dedicated to JetBlue
- Any other E gates = Frontier

### GA (General Aviation) Parking

Parking spots with "GA" in the name automatically:
- Generate N-number callsigns (e.g., N123AB)
- Use GA aircraft types (C172, C182, PA28, etc.)
- Route to less-common airports (Can be configured in the config.json)

### Enroute (ARTCC) Scenario Airport Groups

For enroute scenarios, you can define named groups of airports with their active runways for departures and arrivals.

```json
{
  "artcc_airport_groups": {
    "ZAB": {
      "Primary Airports (East)": "KPHX:08,7R,KTUS:12,KABQ:08,03,KAMA:04,KELP:04,8R",
      "Primary Airports (West)": "KPHX:26,25L,KTUS:30,KABQ:26,21,KAMA:22,KELP:22,26L"
    },
    "ZLA": {
      "Major Airports": "KLAX:24R,25L,KSAN:27,KLAS:26L,KONT:26L",
      "Regional Airports": "KBUR:08,KSNA:20R,KSMF:16L"
    }
  }
}
```

**Format:** `"Group Name": "ICAO:runway,runway,ICAO:runway,runway"`

**Features:**
- Group names appear as dropdown options when configuring enroute scenarios
- Runways specify ACTIVE runways for CIFP SID/STAR parsing and routing
- Multiple airports can be included in each group
- Each airport can have multiple active runways listed
>[!WARNING]
> This requires a matching GeoJSON files in `airport_data/` folder for each airport specified in the group string, otherwise, it will be ignored.

**Example:**
- `KPHX:08,7R` - Phoenix with runways 08 and 7R active
- `KTUS:12` - Tucson with runway 12 active
- Full string creates a selectable airport group for enroute arrival/departure generation

## vNAS Scenario JSON Format

SSG exports scenarios as JSON files that can be edited and then directly uploaded to vNAS. 

Generated files follow this pattern: `{AIRPORT}_{DDHHMM}.json`

### Top-Level Scenario Fields

```json
{
  "name": "Generated Scenario - KPHX",
  "artccId": "ZAB",
  "primaryAirportId": "PHX",
  "aircraft": ["..."],
  "initializationTriggers": [],
  "aircraftGenerators": [],
  "atc": [],
  "autoDeleteMode": "None",
  "flightStripConfigurations": []
}
```

### Aircraft Object Fields

Each aircraft in the `aircraft` array uses the following structure:

#### Required Fields
- `aircraftId` (string): Aircraft callsign (e.g., "AAL123", "N123AB")
- `aircraftType` (string): Aircraft type with equipment suffix (e.g., "B738/L", "A320/L", "C172/G")
- `startingConditions` (object): Defines where and how the aircraft spawns (see below)
- `difficulty` (string): "Easy", "Medium", or "Hard"

#### Optional Fields
- `spawnDelay` (integer): Delay in seconds before aircraft spawns (default: 0)
- `transponderMode` (string): "Standby" or "C" (Mode C)
- `onAltitudeProfile` (boolean): Whether aircraft follows altitude profile (default: false)
- `presetCommands` (array): List of preset command objects (see below)
- `flightplan` (object): Flight plan information (see below)
- `expectedApproach` (string): Expected approach type (e.g., "ILS 25L")
- `airportId` (string): Override primary airport for this aircraft

### Starting Conditions

Aircraft can spawn in one of three ways:

#### 1. Parking
```json
"startingConditions": {
  "type": "Parking",
  "parking": "A1"
}
```

#### 2. On Final Approach
```json
"startingConditions": {
  "type": "OnFinal",
  "runway": "25L",
  "distanceFromRunway": 8,
  "speed": 180,
  "finalApproachCourseOffset": 0
}
```
- `distanceFromRunway`: Distance in nautical miles
- `speed`: Ground speed in knots
- `finalApproachCourseOffset`: Optional heading offset in degrees

#### 3. Fix or FRD (Fix-Radial-Distance)
```json
"startingConditions": {
  "type": "FixOrFrd",
  "fix": "HOMRR020003",
  "altitude": 12000,
  "speed": 280,
  "heading": 150,
  "navigationPath": "HOMRR EAGUL6.8L",
  "mach": 0.78
}
```
- `fix`: Fix name or FRD format string
- `altitude`: Altitude in feet MSL
- `speed`: Ground speed in knots
- `heading`: (Optional) heading in degrees
- `navigationPath`: Initial route path
- `mach`: (Optional) mach number

### Flight Plan

```json
"flightplan": {
  "rules": "IFR",
  "departure": "KPHX",
  "destination": "KDEN",
  "cruiseAltitude": 35000,
  "cruiseSpeed": 450,
  "route": "FORPE1 ...",
  "remarks": "/V/",
  "aircraftType": "B738/L"
}
```

Fields:
- `rules`: "IFR" or "VFR"
- `departure`: Departure airport ICAO
- `destination`: Arrival airport ICAO
- `cruiseAltitude`: Integer altitude in feet
- `cruiseSpeed`: Integer speed in knots
- `route`: Route string (SID/STAR included in route)
- `remarks`: Additional remarks
- `aircraftType`: Aircraft type (should match top-level `aircraftType`)

### Preset Commands

Preset commands are automatically issued to aircraft when they spawn. Be careful when editing these manually as they do need a ULID:

```json
"presetCommands": [
  {
    "id": "01K9RMZQ0JJSFMADVJQHXC1NB8",
    "command": "DM 360"
  },
  {
    "id": "01K9RMZQ0JJSFMADVJQHXC1NB9",
    "command": "AT HOMRR SLN 210"
  }
]
```

Each command object has:
- `id`: Unique identifier (auto-generated ULID)
- `command`: The actual command string

### Editing JSON Files

You can manually edit the generated JSON files before uploading to vNAS:

**Upload Process:**
1. Open SSG
2. Click "Backup File Upload" on the home screen
3. Select your JSON file
4. Browser opens for vNAS authentication
6. Upload completes automatically

## Airport Data Format

### GeoJSON File Structure

This file is exported directly from vNAS Data Admin from the training airports section.

## Logging

The application includes comprehensive logging. Logs are saved to the `logs/` folder (created automatically on first run) and include:
- Data loading information
- Aircraft generation progress
- API call results
- Update check results
- Warnings and errors

## Notes

- Arrival aircraft are positioned along their specified route of flight and automatically add the runway assignment. You can change this per arrival with group commands.
- TRACON arrival aircraft respect waypoint altitude restrictions when available
- Callsigns can include number suffixes for easy grouping (e.g., AAL**25**66, DAL**25**89 both spawn over the same waypoint)

## Credits

**Created by EM for ZAB**

Special thanks to:
- The FAST project for the idea, starting point, and questions answered.
- While now no longer used, I do offer thanks to Kornel C. for the flight plan data used in the initial iterations of this program

