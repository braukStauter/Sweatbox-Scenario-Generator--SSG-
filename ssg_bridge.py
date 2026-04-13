"""
Headless CLI bridge for the Electron frontend.

Usage:
    ssg_bridge(.exe) <config_json_path>

Reads a JSON configuration, dispatches to the matching scenario generator,
writes the vNAS scenario JSON, and prints one JSON status line to stdout:

    {"status": "ok", "filename": "...", "aircraft_count": N}
    {"status": "error", "message": "...", "trace": "..."}
"""
import json
import os
import sys
import traceback
from pathlib import Path


def _resource_root():
    """In PyInstaller onefile, _MEIPASS holds the extracted bundle dir."""
    mei = getattr(sys, '_MEIPASS', None)
    if mei:
        return Path(mei)
    return Path(__file__).resolve().parent


REPO_ROOT = _resource_root()
sys.path.insert(0, str(REPO_ROOT))


def _user_resources_root():
    """Return the user-editable resources directory next to the bundled exe,
    or None in dev mode.

    The electron-builder config ships our extraResources to
    `<install>/resources/`, and the PyInstaller bridge exe lives at
    `<install>/resources/bridge/ssg_bridge.exe`. Users drop updated airport
    files, AIRAC cycles, and a customized `config.json` into that sibling
    tree so they can customize without rebuilding the bridge.
    """
    if not getattr(sys, 'frozen', False):
        return None
    exe_dir = Path(sys.executable).resolve().parent
    # <install>/resources/bridge/ → <install>/resources/
    return exe_dir.parent


def resource_path(*parts):
    """Resolve a bundled-resource path (airport_data/..., config.json, ...).

    Lookup order:
      1. User-editable copy under `<install>/resources/` — so users can edit
         airport geojsons, drop a new FAACIFP18 cycle, or tweak config.json
         without rebuilding the bundled exe.
      2. PyInstaller-baked fallback at `_MEIPASS/` (or repo root in dev).
    """
    user = _user_resources_root()
    if user is not None:
        candidate = user.joinpath(*parts)
        if candidate.exists():
            return candidate
    return REPO_ROOT.joinpath(*parts)

from utils.api_client import FlightDataAPIClient  # noqa: E402
from parsers.geojson_parser import GeoJSONParser  # noqa: E402
from generators.vnas_json_exporter import VNASJSONExporter  # noqa: E402
from utils.preset_command_processor import apply_preset_commands  # noqa: E402
from utils.data_pipeline import split_counts, load_cifp_index  # noqa: E402
from models.preset_command import PresetCommandRule  # noqa: E402


def parse_list(value, upper=False):
    """Accept either a list (preferred, from the new row-table UI) or a
    legacy comma-separated string and return a trimmed list of strings."""
    if value is None or value == '':
        return []
    if isinstance(value, list):
        out = [str(x).strip() for x in value if x is not None and str(x).strip()]
    else:
        out = [x.strip() for x in str(value).split(',') if x.strip()]
    return [x.upper() for x in out] if upper else out


def parse_runway_map(value):
    """Accept either:
      - list of {icao, runways: [..]} objects (preferred, new UI), or
      - list of {icao, runways: 'csv string'} objects, or
      - legacy string like 'KPHX:08,7R; KTUS:12'
    and return `{'KPHX': ['08','7R'], 'KTUS': ['12']}`."""
    out = {}
    if not value:
        return out
    # New object-list form
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            icao = (item.get('icao') or item.get('airport') or '').strip().upper()
            if not icao:
                continue
            runways_raw = item.get('runways')
            out[icao] = parse_list(runways_raw, upper=True)
        return out
    # Legacy string form
    for chunk in str(value).replace(';', ',,').split(',,'):
        chunk = chunk.strip()
        if not chunk or ':' not in chunk:
            continue
        code, runways = chunk.split(':', 1)
        out[code.strip().upper()] = parse_list(runways, upper=True)
    return out


def parse_waypoint_star_pairs(value):
    """Accept either:
      - list of {waypoint, star} objects (new UI), or
      - legacy string 'COLTR.COLTR4, CIM.BRRTO4'
    and return a list of 'WAYPOINT.STAR' strings that the existing scenario
    code understands.
    """
    if not value:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, str):
                item = item.strip()
                if item:
                    out.append(item)
                continue
            if not isinstance(item, dict):
                continue
            wp = (item.get('waypoint') or '').strip()
            star = (item.get('star') or '').strip()
            if wp and star:
                out.append(f"{wp}.{star}")
        return out
    return parse_list(value)


def parse_frd_rows(value):
    """Accept either:
      - list of {point, altitude, speed, initialRoute} objects, or
      - the legacy parallel-array shape (points/altitudes/speeds/initialRoutes
        as comma-separated strings).
    Returns a 4-tuple `(points_csv, alts_csv, speeds_csv, routes_csv)` matching
    the format the existing scenario paths already consume.
    """
    if not value:
        return (None, None, None, None)
    if isinstance(value, list):
        pts, alts, spds, rts = [], [], [], []
        for r in value:
            if not isinstance(r, dict):
                continue
            p = (r.get('point') or '').strip()
            if not p:
                continue
            pts.append(p)
            alts.append(str(r.get('altitude') or '').strip())
            spds.append(str(r.get('speed') or '').strip())
            rts.append((r.get('initialRoute') or '').strip())
        if not pts:
            return (None, None, None, None)
        return (
            ','.join(pts),
            ','.join(alts),
            ','.join(spds),
            ','.join(rts),
        )
    # Shouldn't happen with new UI, but be defensive:
    return (str(value) or None, None, None, None)


def difficulty_dict(d):
    if not d or not d.get('enabled'):
        return None
    return {
        'easy': int(d.get('easy', 0)),
        'medium': int(d.get('medium', 0)),
        'hard': int(d.get('hard', 0)),
    }


def load_parsers(airport):
    geojson_file = resource_path('airport_data', f'{airport}.geojson')
    if not geojson_file.exists():
        geojson_file = resource_path('airport_data', f'{airport.lstrip("K")}.geojson')
    geojson_parser = GeoJSONParser(str(geojson_file)) if geojson_file.exists() else None
    # CIFP indexes airports by ICAO (K-prefixed for the US). load_cifp_index
    # memoizes per process — each airport pays the parse cost once. Prefer
    # the user-editable FAACIFP18 next to the exe if present (AIRAC cycle
    # updates land there without rebuilding).
    cifp_parser = load_cifp_index(airport, str(resource_path('airport_data', 'FAACIFP18')))
    return geojson_parser, cifp_parser


from utils.data_pipeline import to_icao  # noqa: E402,F401


def dispatch(cfg):
    airport = cfg['departureAirport']
    scenario_type = cfg['scenarioType']
    api = FlightDataAPIClient()

    active_runways = parse_list(cfg.get('activeRunways', ''), upper=True)
    separation = int(cfg.get('separationRange', 0) or 0)

    # Coerce the string payload to the SpawnDelayMode enum. Without this the
    # `==` checks in `BaseScenario.apply_spawn_delays` all return False, so
    # every aircraft.spawn_delay stays None and the vNAS converter omits the
    # `spawnDelay` field entirely.
    from models.spawn_delay_mode import SpawnDelayMode  # local import: avoid widening the top-level surface
    raw_mode = cfg.get('spawnDelayMode', 'none')
    if not cfg.get('spawnDelayEnabled'):
        raw_mode = 'none'
    try:
        spawn_mode = SpawnDelayMode(raw_mode)
    except ValueError:
        spawn_mode = SpawnDelayMode.NONE

    delay_value = cfg.get('incrementalDelayValue') or None
    total_minutes = int(cfg.get('totalSessionMinutes', 30) or 30)
    dep_diff = difficulty_dict(cfg.get('departureDifficulty'))
    arr_diff = difficulty_dict(cfg.get('arrivalDifficulty'))
    enr_diff = difficulty_dict(cfg.get('enrouteDifficulty'))
    arrival_mode = cfg.get('arrivalMode', 'star')
    arrival_waypoints = parse_waypoint_star_pairs(cfg.get('arrivalWaypoints', ''))
    enable_cifp_sids = bool(cfg.get('enableCifpSids', True))
    manual_sids_raw = cfg.get('manualSids')
    manual_sids = parse_list(manual_sids_raw, upper=True) if manual_sids_raw else None
    use_cifp_speeds = bool(cfg.get('useCifpSpeeds', True))
    num_vfr = int(cfg.get('numVfr', 0) or 0) if cfg.get('enableVfr') else 0
    vfr_raw = cfg.get('vfrSpawnLocations')
    vfr_locs = parse_list(vfr_raw) if vfr_raw else None
    # FRD: prefer the new structured `frd: [{point,altitude,speed,initialRoute}]`
    # form; fall back to the legacy parallel-array shape if the new field is absent.
    if cfg.get('frd'):
        frd = parse_frd_rows(cfg.get('frd'))
    else:
        frd = (
            cfg.get('frdPoints') or None,
            cfg.get('frdAltitudes') or None,
            cfg.get('frdSpeeds') or None,
            cfg.get('frdInitialRoutes') or None,
        )

    num_dep = int(cfg.get('numDepartures', 0) or 0)
    num_arr = int(cfg.get('numArrivals', 0) or 0)
    num_enr = int(cfg.get('numEnroute', 0) or 0)
    num_ovf = int(cfg.get('numOverflight', 0) or 0)

    wake_bias_raw = cfg.get('wakeBias') or {}
    if cfg.get('wakeBiasEnabled') and wake_bias_raw:
        wake_weights = {k.upper(): float(wake_bias_raw.get(k, 0) or 0) for k in ('L', 'M', 'H')}
        # Proportional renormalization so client drift (sum != 100) doesn't
        # silently under/over-weight the mix. split_counts already handles
        # sum==0 by falling back to a flat distribution.
        wake_total = sum(wake_weights.values())
        if wake_total and wake_total != 100:
            scale = 100.0 / wake_total
            wake_weights = {k: v * scale for k, v in wake_weights.items()}
    else:
        wake_weights = {'L': 1.0, 'M': 1.0, 'H': 1.0}
    dep_wake_counts = split_counts(num_dep, wake_weights)
    arr_wake_counts = split_counts(num_arr, wake_weights)

    # Server-side validation for the subset of rules the renderer skips.
    if (scenario_type in ('tracon_arrivals', 'tracon_mixed')
            and arrival_mode == 'star'
            and not arrival_waypoints):
        raise ValueError(
            "STAR arrival mode requires at least one 'WAYPOINT.STAR' pair "
            "(e.g. 'COLTR.COLTR4'). Set arrivalWaypoints or switch to FRD mode."
        )

    # --- Enroute -----------------------------------------------------------
    if scenario_type == 'enroute':
        from scenarios.artcc_enroute import ArtccEnrouteScenario

        # New config unifies airports and runways into a single
        # [{icao, runways}] list per direction. Legacy configs kept them
        # split (`arrivalAirports` + `arrivalAirportRunways`), so fall back.
        arr_items = cfg.get('arrivalAirports')
        dep_items = cfg.get('departureAirports')

        def _extract_icaos(items):
            if isinstance(items, list):
                return [
                    (i.get('icao') or i.get('airport') or '').strip().upper()
                    for i in items if isinstance(i, dict) and (i.get('icao') or i.get('airport'))
                ]
            return parse_list(items, upper=True)

        arr_airports = _extract_icaos(arr_items)
        dep_airports = _extract_icaos(dep_items)
        arr_rwys = parse_runway_map(
            arr_items if isinstance(arr_items, list) else cfg.get('arrivalAirportRunways', '')
        )
        dep_rwys = parse_runway_map(
            dep_items if isinstance(dep_items, list) else cfg.get('departureAirportRunways', '')
        )

        def _extract_counts(items):
            """{ICAO: int} from per-airport `count` field on the new UI shape."""
            if not isinstance(items, list):
                return {}
            out = {}
            for i in items:
                if not isinstance(i, dict):
                    continue
                icao = (i.get('icao') or i.get('airport') or '').strip().upper()
                if not icao:
                    continue
                raw = i.get('count')
                try:
                    out[icao] = max(0, int(raw)) if raw not in (None, '') else 0
                except (TypeError, ValueError):
                    out[icao] = 0
            return out

        arr_counts = _extract_counts(arr_items)
        dep_counts = _extract_counts(dep_items)

        # When the per-airport counts are populated, they authoritatively
        # define the enroute arrivals/departures total. Renderer already
        # does this math; this makes direct-bridge invocations robust too.
        if sum(arr_counts.values()) > 0:
            num_arr = sum(arr_counts.values())
        if sum(dep_counts.values()) > 0:
            num_dep = sum(dep_counts.values())
        sc = ArtccEnrouteScenario(
            airport, api, cfg,
            geojson_parsers={}, cifp_parsers={},
        )
        aircraft = sc.generate(
            num_enroute=num_enr, num_arrivals=num_arr, num_departures=num_dep,
            num_overflight=num_ovf,
            arrival_airports=arr_airports, departure_airports=dep_airports,
            arrival_airport_runways=arr_rwys, departure_airport_runways=dep_rwys,
            per_airport_arrival_counts=arr_counts,
            per_airport_departure_counts=dep_counts,
            difficulty_config_enroute=enr_diff,
            difficulty_config_arrivals=arr_diff,
            difficulty_config_departures=dep_diff,
            spawn_delay_mode=spawn_mode, delay_value=delay_value,
            total_session_minutes=total_minutes,
            cached_departures_pool=None, cached_arrivals_pool=None,
            cached_transient_pool=None,
        )
        return aircraft, airport

    # --- Airport-based -----------------------------------------------------
    geojson_parser, cifp_parser = load_parsers(airport)
    # Scenarios issue their own targeted API calls via
    # BaseScenario._prepare_departure_flight_pool / _prepare_arrival_flight_pool;
    # no pre-populated flight data is threaded through.

    ga_config = cfg.get('ga') or {}

    def _attach_budgets(s):
        s.set_wake_budgets(dep_wake_counts, arr_wake_counts)
        s.set_ga_config(ga_config)
        return s

    if scenario_type == 'ground_departures':
        from scenarios.ground_departures import GroundDeparturesScenario
        sc = _attach_budgets(GroundDeparturesScenario(airport, geojson_parser, cifp_parser, api))
        aircraft = sc.generate(
            num_dep, spawn_mode, delay_value, total_minutes, None,
            dep_diff, active_runways, enable_cifp_sids, manual_sids,
        )

    elif scenario_type == 'ground_mixed':
        from scenarios.ground_mixed import GroundMixedScenario
        sc = _attach_budgets(GroundMixedScenario(airport, geojson_parser, cifp_parser, api))
        aircraft = sc.generate(
            num_dep, num_arr, active_runways, separation,
            spawn_mode, delay_value, total_minutes, None, None,
            enable_cifp_sids, manual_sids,
            dep_diff, arr_diff,
        )

    elif scenario_type == 'tower_mixed':
        from scenarios.tower_mixed import TowerMixedScenario
        sc = _attach_budgets(TowerMixedScenario(airport, geojson_parser, cifp_parser, api))
        aircraft = sc.generate(
            num_dep, num_arr, active_runways, separation,
            spawn_mode, delay_value, total_minutes, None, None,
            enable_cifp_sids, manual_sids,
            num_vfr, vfr_locs,
            dep_diff, arr_diff,
        )

    elif scenario_type == 'tracon_arrivals':
        from scenarios.tracon_arrivals import TraconArrivalsScenario
        sc = _attach_budgets(TraconArrivalsScenario(airport, geojson_parser, cifp_parser, api))
        aircraft = sc.generate(
            num_arr, arrival_waypoints, None, spawn_mode, delay_value, total_minutes,
            None, arr_diff, active_runways, use_cifp_speeds,
            arrival_mode=arrival_mode,
            frd_points=frd[0], frd_altitudes=frd[1],
            frd_speeds=frd[2], frd_initial_routes=frd[3],
        )

    elif scenario_type == 'tracon_mixed':
        from scenarios.tracon_mixed import TraconMixedScenario
        sc = _attach_budgets(TraconMixedScenario(airport, geojson_parser, cifp_parser, api))
        aircraft = sc.generate(
            num_dep, num_arr, arrival_waypoints, None, spawn_mode,
            delay_value, total_minutes, None,
            None, active_runways, enable_cifp_sids, manual_sids,
            use_cifp_speeds, num_vfr, vfr_locs,
            dep_diff, arr_diff,
            arrival_mode=arrival_mode,
            frd_points=frd[0], frd_altitudes=frd[1],
            frd_speeds=frd[2], frd_initial_routes=frd[3],
        )

    else:
        raise ValueError(f'Unknown scenario type: {scenario_type}')

    return aircraft, None


def main(config_path):
    cfg = json.loads(Path(config_path).read_text('utf-8'))
    aircraft, artcc_id = dispatch(cfg)

    preset_rules = [
        PresetCommandRule(
            group_type=r['groupType'],
            group_value=r.get('groupValue') or None,
            command_template=r['commandTemplate'],
        )
        for r in cfg.get('presetCommands', [])
        if r.get('commandTemplate')
    ]
    if preset_rules:
        apply_preset_commands(aircraft, preset_rules)

    out_dir = Path(cfg.get('outputDir') or (Path.home() / 'SSG' / 'scenarios'))
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = VNASJSONExporter.export(
        aircraft,
        cfg['departureAirport'],
        artcc_id,
        cfg['scenarioType'],
        str(out_dir),
    )
    print(json.dumps({
        'status': 'ok',
        'filename': str(filename),
        'aircraft_count': len(aircraft),
    }))


if __name__ == '__main__':
    try:
        if len(sys.argv) < 2:
            raise SystemExit('usage: ssg_bridge <config.json>')
        main(sys.argv[1])
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            'status': 'error',
            'message': str(exc),
            'trace': traceback.format_exc(),
        }))
        sys.exit(1)
