# SSG — Electron + TypeScript Frontend

Electron/TypeScript rewrite of the Python/Tkinter Sweatbox Scenario Generator.

## How it ships (end users)

A single Windows installer. **No Python on the user's machine.**

Under the hood the installer contains:

1. The Electron renderer (React/TS UI)
2. The Electron main process (TS IPC + flight-data API client)
3. `ssg_bridge.exe` — a PyInstaller-compiled standalone binary of the Python
   scenario engine (all scenarios, CIFP parsing, FAACIFP18 database, vNAS JSON
   export — everything). Bundled under `resources/bridge/ssg_bridge.exe`.
4. `airport_data/*.geojson` for the renderer's airport picker.

At runtime the Electron main process spawns `ssg_bridge.exe` as a short-lived
child, passes the scenario config as a JSON file, and reads back the generated
vNAS scenario JSON. End users never install Python.

## Dev workflow

Only contributors need Python (to rebuild the bridge binary). Requires Node 18+
and Python 3.11+ with `requirements.txt` + `pyinstaller` installed.

```bash
cd electron-app
npm install
npm run dev         # Vite + Electron with HMR; live-uses ../ssg_bridge.py
```

In dev mode, if `../dist/ssg_bridge.exe` exists it's used directly (fast);
otherwise the TS main spawns `python ../ssg_bridge.py` so you can edit the
Python source live.

## Building the installer

```bash
npm run package
```

This runs, in order:

1. `build:renderer`  — Vite → `dist/`
2. `build:electron`  — tsc → `dist-electron/`
3. `build:bridge`    — PyInstaller → `../dist/ssg_bridge.exe`
4. `build:icon`      — Converts `gui/SSG_Logo.png` → `build/icon.ico`
5. `electron-builder --win` → `release/Sweatbox Scenario Generator-<ver>-Setup.exe`

## Window

- Initial size: **900 × 1000** (matches original Tkinter window)
- Minimum: **800 × 900**
- Title: `vNAS Sweatbox Scenario Generator`

## Wake Category Bias

Inside "Aircraft & Traffic":

- L / M / H percentage inputs, auto-adjusting to sum to 100 (largest-remainder)
- Live stacked bar
- When enabled, `fetchFlights` splits the requested count into sub-requests with
  the new `?wakecat=L|M|H` param, one per category, results merged and shuffled
- When disabled, a single call with no `wakecat` is made (legacy behavior)

## Scenario coverage

`ssg_bridge.py` dispatch handles all six scenario types:
`ground_departures`, `ground_mixed`, `tower_mixed`, `tracon_arrivals`,
`tracon_mixed`, `enroute`. Per-scenario options including separate
departure/arrival/enroute difficulty configs, VFR (tower/TRACON mixed), STAR
vs FRD arrival modes, CIFP SIDs/speeds, and ARTCC airport/runway mappings are
all passed through.

## Layout

- `electron/` — main + preload + IPC handlers
- `shared/` — types + wake-bias utilities
- `src/components/` — themed primitives, Accordion, WakeCategoryBias, SelectableCard
- `src/sections/` — AircraftCounts, Runway & Airport, Timing & Spawning,
  Arrivals & Approach (STAR/FRD/VFR), Departures & Climb, Enroute Airports,
  Output & Export, DifficultyBlock
- `src/screens/` — Splash, AirportSelection, ScenarioTypeSelection,
  ScenarioConfig, Generation
- `src/state/scenarioStore.ts` — Zustand store
- `scripts/build-bridge.mjs` — PyInstaller driver
- `scripts/build-icon.mjs` — png-to-ico driver
- `../ssg_bridge.py` + `../ssg_bridge.spec` — Python bridge + PyInstaller spec
