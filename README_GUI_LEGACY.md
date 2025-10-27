# vNAS Sweatbox Scenario Generator - GUI

A modern, dark-themed graphical user interface for the vNAS Sweatbox Scenario Generator.

## Features

- **Dark Theme**: Easy on the eyes with a modern dark color scheme
- **Splash Screen**: Professional loading screen on startup
- **Step-by-Step Workflow**: Guided process through all configuration steps
- **Dynamic Forms**: Configuration options adapt based on selected scenario type
- **User-Friendly**: Intuitive interface with clear labels and examples
- **Progress Feedback**: Visual feedback during scenario generation

## Running the GUI

To launch the GUI version of the application, run:

```bash
python main_gui.py
```

## Workflow

### 1. Airport Selection
Select the primary airport for your scenario from available GeoJSON files in the `airport_data` directory.

### 2. Scenario Type Selection
Choose from six scenario types:
- **Ground (Departures)**: Ground departure aircraft only at parking spots
- **Ground (Departures/Arrivals)**: Ground departures with arriving aircraft on final approach
- **Tower (Departures/Arrivals)**: Tower position with mixed departures and arrivals
- **TRACON (Departures)**: TRACON departure aircraft starting from the ground
- **TRACON (Arrivals)**: TRACON arrival aircraft at designated waypoints
- **TRACON (Departures/Arrivals)**: TRACON position with mixed departures and arrivals

### 3. Scenario Configuration
Configure parameters specific to your selected scenario type:

**All Departure Scenarios:**
- Number of departure aircraft

**Arrival Scenarios:**
- Number of arrival aircraft

**Runway-Based Scenarios:**
- Active runway(s) (comma-separated, e.g., "7L, 25R")

**Tower Mixed:**
- Separation interval (min-max in nautical miles, e.g., "3-6")

**TRACON Arrivals:**
- Arrival waypoints (comma-separated, e.g., "EAGUL, CHILY")
- Altitude range (min-max in feet, e.g., "7000-18000")
- Spawn delay range (min-max in minutes, e.g., "4-7")

**All Scenarios:**
- Output filename (defaults to airport_scenario.air)

### 4. Generation
Watch as your scenario is generated. Upon completion, you'll see:
- Success confirmation
- Number of aircraft generated
- Output file location

## Configuration File

The GUI supports the same `config.json` file as the CLI version for parking-specific airlines:

```json
{
  "parking_airlines": {
    "KPHX": {
      "A#": ["AAL", "AAL", "AAL"],
      "B#": ["SWA", "SWA", "SWA"],
      "C#": ["UAL", "UAL", "UAL"],
      "E1": ["JBU"],
      "E2": ["JBU"]
    }
  }
}
```

### Wildcard Support

Use `#` as a wildcard to match multiple parking spots:
- **`A#`** matches `A1`, `A2`, `A3`, `A10`, `A11`, etc. (any parking starting with "A")
- **`B#`** matches `B1`, `B2`, `B3`, etc.
- **Specific names override wildcards**: If you specify both `A#` and `A1`, then `A1` will use its specific configuration

### Airline Weighting

Repeat airline codes to increase their probability:
- `["AAL", "AAL", "DAL"]` = 67% AAL, 33% DAL
- `["SWA", "SWA", "SWA"]` = 100% SWA

## GA Parking

Parking spots with "GA" in the name automatically:
- Generate N-number callsigns (e.g., N123AB)
- Use general aviation aircraft types
- Route to less-common airports
- Fly at lower altitudes (3000-8000 feet)

## Navigation

- **Next/Back**: Navigate between screens
- **Generate**: Start scenario generation
- **New Scenario**: Return to start to create another scenario
- **Exit**: Close the application

## Tips

- Leave input fields blank to use default values (shown in placeholders)
- All comma-separated inputs support spaces (e.g., "7L, 25R" or "7L,25R")
- The application validates inputs and provides clear error messages
- Configuration is loaded automatically from `config.json` if present

## Keyboard Shortcuts

- **Tab**: Navigate between input fields
- **Enter**: Activate focused button
- **Escape**: (Future: cancel/go back)

## Architecture

The GUI is built with a modular architecture:

```
gui/
├── __init__.py
├── theme.py              # Dark theme configuration
├── widgets.py            # Reusable themed widgets
├── splash_screen.py      # Startup splash screen
├── main_window.py        # Main application controller
└── screens/
    ├── __init__.py
    ├── airport_selection.py      # Airport selection screen
    ├── scenario_type_selection.py # Scenario type selection screen
    ├── scenario_config.py         # Dynamic configuration screen
    └── generation_screen.py       # Generation progress and results
```

## Customization

### Theme Colors
Edit `gui/theme.py` to customize colors, fonts, and spacing.

### Adding Widgets
Create new reusable widgets in `gui/widgets.py`.

### Adding Screens
Add new screens in `gui/screens/` and register them in `main_window.py`.

## Troubleshooting

**GUI doesn't start:**
- Ensure tkinter is installed: `python -m tkinter`
- Check Python version is 3.7+

**Airport not showing:**
- Verify GeoJSON files exist in `airport_data/`
- Check file naming matches pattern: `{airport}.geojson`

**Scenario generation fails:**
- Check console output for detailed error messages
- Verify all required configuration fields are filled
- Ensure runway names match those in your GeoJSON file

## CLI vs GUI

Both interfaces provide the same functionality:
- **CLI** (`main.py`): Traditional command-line interface
- **GUI** (`main_gui.py`): Modern graphical interface

Choose based on your preference and workflow!
