"""
ARTCC Enroute scenario for Center-level operations
Supports enroute transient, arrival, and departure aircraft
"""
import logging
import random
import re
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from scenarios.base_scenario import BaseScenario
from models.aircraft import Aircraft
from models.spawn_delay_mode import SpawnDelayMode
from utils.flight_data_filter import filter_valid_flights, clean_route_string
from utils.route_positioning import RouteParser
from utils.artcc_utils import get_artcc_boundaries
from utils.data_pipeline import load_cifp_index

logger = logging.getLogger(__name__)


class _LazyCifpMap(dict):
    """Dict-like wrapper around `self.cifp_parsers` that lazily materializes a
    CIFPIndex for any airport on first access. Lets enroute code keep its
    ``self.cifp_parsers.get(icao)`` call pattern while actually loading
    procedure data (the bridge previously passed an empty dict, so every
    lookup silently returned None).
    """

    def get(self, icao, default=None):
        if not icao:
            return default
        if icao in self:
            return dict.__getitem__(self, icao)
        try:
            idx = load_cifp_index(icao)
            self[icao] = idx
            return idx
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Lazy CIFP load failed for {icao}: {exc}")
            return default

    def __getitem__(self, icao):
        val = self.get(icao)
        if val is None:
            raise KeyError(icao)
        return val


class _LazyGeoJSONMap(dict):
    """Parallel to _LazyCifpMap: lazy-loads `airport_data/{ICAO}.geojson`.

    Enroute departures need per-airport parking data. The bridge doesn't
    pre-build these parsers (the list of departure airports is a runtime
    config), so we load on demand keyed by ICAO. Falls back to stripping
    the leading `K` (the geojson files are named by 3-letter FAA code).
    """

    def get(self, icao, default=None):
        if not icao:
            return default
        if icao in self:
            return dict.__getitem__(self, icao)
        from parsers.geojson_parser import GeoJSONParser
        # Go through the bridge's resource_path helper so we pick up the
        # user-editable `<install>/resources/airport_data/` first and fall
        # back to the PyInstaller-baked copy second. Works identically in
        # dev mode (both paths resolve to the repo's airport_data).
        from ssg_bridge import resource_path
        candidates = [resource_path('airport_data', f"{icao}.geojson")]
        if icao.startswith('K') and len(icao) == 4:
            candidates.append(resource_path('airport_data', f"{icao[1:]}.geojson"))
        for path in candidates:
            if path.exists():
                try:
                    parser = GeoJSONParser(str(path))
                    self[icao] = parser
                    return parser
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to load GeoJSON for {icao}: {exc}")
                    return default
        logger.warning(f"No GeoJSON file for {icao}; enroute departures from this airport will be skipped")
        return default

    def __getitem__(self, icao):
        val = self.get(icao)
        if val is None:
            raise KeyError(icao)
        return val


class ArtccEnrouteScenario(BaseScenario):
    """Scenario for ARTCC enroute operations"""

    # Minimum remaining route distance (NM) a transient-enroute aircraft must
    # have inside the ARTCC from its spawn waypoint. Prevents spawning aircraft
    # 10 NM from the edge that immediately hand off and leave.
    MIN_REMAINING_IN_ARTCC_NM: float = 50.0
    # Default band (NM) outside ARTCC boundary where overflights spawn.
    DEFAULT_OVERFLIGHT_BAND_NM: Tuple[float, float] = (10.0, 25.0)
    # Default band (NM) from destination airport for arrival spawns.
    DEFAULT_ARRIVAL_BAND_NM: Tuple[float, float] = (80.0, 140.0)

    def __init__(self, artcc_id: str, api_client, config: Dict = None,
                 geojson_parsers: Dict = None, cifp_parsers: Dict = None):
        """
        Initialize ARTCC scenario

        Args:
            artcc_id: ARTCC identifier (e.g., "ZAB", "ZLA")
            api_client: API client for flight data
            config: Configuration dictionary from config.json
            geojson_parsers: Dictionary mapping airport ICAO to GeoJSONParser instances
            cifp_parsers: Dictionary mapping airport ICAO to CIFPParser instances
        """
        import threading

        # Initialize ARTCC data
        self.artcc_id = artcc_id.upper()
        self.api_client = api_client
        self.aircraft: List[Aircraft] = []
        self.used_callsigns: set = set()
        self.used_spawn_points: set = set()  # Track used spawn waypoints to prevent duplicates
        self.artcc_boundaries = get_artcc_boundaries()
        self.route_parser = RouteParser()

        # Thread-safety locks for parallel generation
        self.aircraft_lock = threading.Lock()
        self.callsign_lock = threading.Lock()
        self.spawn_point_lock = threading.Lock()

        # Store airport-specific parsers. For the bridge path (Electron) we
        # don't prepopulate a parser dict — instead, cifp_parsers lazy-loads
        # each airport's CIFPIndex on first access (LRU-cached per process),
        # so runway-aware code paths keep working without an explicit
        # construction loop. Legacy PyQt callers pass pre-built dicts.
        self.geojson_parsers = _LazyGeoJSONMap(geojson_parsers or {})
        self.cifp_parsers = _LazyCifpMap(cifp_parsers or {})

        # Load config (handle being passed the full config or just loading it)
        if config:
            self.config = config
        else:
            self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load config.json file"""
        import json
        from pathlib import Path

        config_path = Path('config.json')
        if config_path.exists():
            with open(config_path, 'r') as f:
                return json.load(f)
        return {}

    def generate(self,
                 num_enroute: int = 0,
                 num_arrivals: int = 0,
                 num_departures: int = 0,
                 num_overflight: int = 0,
                 arrival_airports: Optional[List[str]] = None,
                 departure_airports: Optional[List[str]] = None,
                 arrival_airport_runways: Optional[Dict[str, List[str]]] = None,
                 departure_airport_runways: Optional[Dict[str, List[str]]] = None,
                 per_airport_arrival_counts: Optional[Dict[str, int]] = None,
                 per_airport_departure_counts: Optional[Dict[str, int]] = None,
                 arrival_spawn_band: Optional[Tuple[float, float]] = None,
                 overflight_spawn_band: Optional[Tuple[float, float]] = None,
                 per_airport_arrival_bands: Optional[Dict[str, Tuple[float, float]]] = None,
                 per_airport_arrival_procedures: Optional[Dict[str, List[str]]] = None,
                 config_warnings: Optional[List[str]] = None,
                 enroute_min_remaining_nm: Optional[float] = None,
                 difficulty_config_enroute: Dict = None,
                 difficulty_config_arrivals: Dict = None,
                 difficulty_config_departures: Dict = None,
                 spawn_delay_mode: SpawnDelayMode = SpawnDelayMode.NONE,
                 delay_value: str = None,
                 total_session_minutes: int = None,
                 cached_departures_pool: Optional[List[Dict]] = None,
                 cached_arrivals_pool: Optional[List[Dict]] = None,
                 cached_transient_pool: Optional[List[Dict]] = None,
                 custom_boundary_waypoints: Optional[List[str]] = None) -> List[Aircraft]:
        """
        Generate ARTCC enroute scenario

        Args:
            num_enroute: Number of enroute transient aircraft
            num_arrivals: Number of arrival aircraft
            num_departures: Number of departure aircraft
            arrival_airports: List of arrival airport ICAOs
            departure_airports: List of departure airport ICAOs
            arrival_airport_runways: Dict mapping airport ICAO to list of active runways
            departure_airport_runways: Dict mapping airport ICAO to list of active runways
            difficulty_config_enroute: Difficulty distribution for enroute aircraft
            difficulty_config_arrivals: Difficulty distribution for arrivals
            difficulty_config_departures: Difficulty distribution for departures
            spawn_delay_mode: Spawn delay mode
            delay_value: Delay value/range
            total_session_minutes: Total session minutes for TOTAL mode
            cached_departures_pool: Optional pre-loaded departures pool (skips API fetch if provided)
            cached_arrivals_pool: Optional pre-loaded arrivals pool (skips API fetch if provided)
            cached_transient_pool: Optional pre-loaded transient pool (skips API fetch if provided)

        Returns:
            List of Aircraft objects
        """
        import concurrent.futures
        from pathlib import Path

        self.aircraft = []
        self.used_callsigns = set()
        self.used_spawn_points = set()

        # Optional custom boundary — a user-defined polygon built from a list
        # of waypoint identifiers. When present, every subsequent
        # ``is_point_in_artcc`` / ``get_artcc_polygon`` / boundary-distance
        # check runs against this polygon instead of the facility's ARTCC
        # polygon. The scenario's ``artcc_id`` string is still used for
        # log/display text but no longer drives geometry.
        if custom_boundary_waypoints:
            self._install_custom_boundary(custom_boundary_waypoints)

        # Store configuration for filtering and runway assignment
        self.arrival_airports = arrival_airports or []
        self.arrival_airport_runways = arrival_airport_runways or {}
        # Per-airport quotas for enroute arrivals/departures (new UI). Keys
        # are K-prefixed ICAO codes; values are integer counts. If empty,
        # generator code falls back to proportional splitting of the
        # aggregate `num_arrivals`/`num_departures` across listed airports.
        self.per_airport_arrival_counts = {
            k.upper(): max(0, int(v or 0))
            for k, v in (per_airport_arrival_counts or {}).items()
        }
        self.per_airport_departure_counts = {
            k.upper(): max(0, int(v or 0))
            for k, v in (per_airport_departure_counts or {}).items()
        }
        # Persistent remaining quotas — top-up passes re-enter the generator
        # functions, so rebuilding `remaining = dict(per_airport)` fresh each
        # call would overshoot by re-running the full quota every pass.
        self._arrival_remaining = (
            dict(self.per_airport_arrival_counts)
            if any(v > 0 for v in self.per_airport_arrival_counts.values())
            else None
        )
        self._departure_remaining = (
            dict(self.per_airport_departure_counts)
            if any(v > 0 for v in self.per_airport_departure_counts.values())
            else None
        )

        # Spawn-band configuration (falls back to class defaults when None).
        self.arrival_spawn_band = tuple(arrival_spawn_band) if arrival_spawn_band else self.DEFAULT_ARRIVAL_BAND_NM
        self.overflight_spawn_band = tuple(overflight_spawn_band) if overflight_spawn_band else self.DEFAULT_OVERFLIGHT_BAND_NM
        self.per_airport_arrival_bands = {
            k.upper(): (float(v[0]), float(v[1]))
            for k, v in (per_airport_arrival_bands or {}).items()
            if isinstance(v, (list, tuple)) and len(v) == 2
        }
        # STAR prefix filter per arrival airport (e.g. {'KPHX': ['EAGUL']}
        # only pulls arrivals filed with a STAR whose base name is EAGUL).
        # Empty / missing entry = accept any STAR at that airport.
        self.arrival_airport_procedures = {
            k.upper(): [str(s).upper() for s in v]
            for k, v in (per_airport_arrival_procedures or {}).items()
            if v
        }
        # Collect warnings/notes for the conclusion screen. `config_warnings`
        # already holds validation messages from the bridge (e.g. rejected
        # STAR tokens containing digits); keep them so the UI sees them.
        self.generation_warnings: List[str] = list(config_warnings or [])
        self.generation_notes: List[str] = []
        self.enroute_min_remaining_nm = (
            float(enroute_min_remaining_nm)
            if enroute_min_remaining_nm is not None
            else self.MIN_REMAINING_IN_ARTCC_NM
        )

        logger.info(f"Generating ARTCC {self.artcc_id} scenario: {num_enroute} enroute, {num_arrivals} arrivals, {num_departures} departures")
        # Total targets exposed for flight_pool buffer math inside
        # _fetch_pool_* helpers (they size each per-airport call as
        # target // len(airports)).
        self._num_departures_total = num_departures
        self._num_arrivals_total = num_arrivals
        self._num_enroute_total = num_enroute

        # Cross-check runway vs STAR prefix selections — emit advisory
        # warnings for any airport whose active runways don't overlap any
        # of the requested STAR's published runway transitions. Generation
        # still proceeds; runway assignment falls back to the STAR's first
        # published runway via `_get_runway_for_star`.
        self._validate_arrival_runway_procedures()

        departures_pool = []
        arrivals_pool = []
        transient_pool = []

        # Use cached pools if provided, otherwise fetch
        if cached_departures_pool is not None:
            logger.info(f"Using cached Departures Pool: {len(cached_departures_pool)} flights")
            departures_pool = cached_departures_pool
        if cached_arrivals_pool is not None:
            logger.info(f"Using cached Arrivals Pool: {len(cached_arrivals_pool)} flights")
            arrivals_pool = cached_arrivals_pool
        if cached_transient_pool is not None:
            logger.info(f"Using cached Transient Pool: {len(cached_transient_pool)} flights")
            transient_pool = cached_transient_pool

            # Filter out arrivals to configured airports (since cache was loaded before airports were selected)
            if arrival_airports and transient_pool:
                arrival_set = set(airport.upper() for airport in arrival_airports)
                before_count = len(transient_pool)
                transient_pool = [
                    f for f in transient_pool
                    if f.get('arrivalAirport', '').upper() not in arrival_set
                ]
                if before_count != len(transient_pool):
                    logger.info(f"Filtered cached Transient Pool: removed {before_count - len(transient_pool)} arrivals to configured airports")

        # Only fetch pools that weren't cached
        if cached_departures_pool is None or cached_arrivals_pool is None or cached_transient_pool is None:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}

                # 1. Fetch Departures Pool if needed and not cached
                if cached_departures_pool is None and num_departures > 0 and departure_airports:
                    logger.info(f"Fetching Departures Pool from {departure_airports}")
                    futures['departures'] = executor.submit(
                        self._fetch_pool_departures,
                        departure_airports
                    )

                # 2. Fetch Arrivals Pool if needed and not cached
                if cached_arrivals_pool is None and num_arrivals > 0 and arrival_airports:
                    logger.info(f"Fetching Arrivals Pool to {arrival_airports}")
                    futures['arrivals'] = executor.submit(
                        self._fetch_pool_arrivals,
                        arrival_airports
                    )

                # 3. Fetch Transient Pool if needed and not cached
                if cached_transient_pool is None and num_enroute > 0:
                    logger.info(f"Fetching Transient Pool for ARTCC {self.artcc_id}")
                    futures['transient'] = executor.submit(
                        self._fetch_pool_transient,
                        arrival_airports or []
                    )

                # Wait for all fetches to complete
                for pool_name, future in futures.items():
                    try:
                        result = future.result()
                        if pool_name == 'departures':
                            departures_pool = result
                            logger.info(f"Departures Pool: {len(departures_pool)} flights")
                        elif pool_name == 'arrivals':
                            arrivals_pool = result
                            logger.info(f"Arrivals Pool: {len(arrivals_pool)} flights")
                        elif pool_name == 'transient':
                            transient_pool = result
                            logger.info(f"Transient Pool: {len(transient_pool)} flights")
                    except Exception as e:
                        logger.error(f"Error fetching {pool_name} pool: {e}")

        # Compute requested totals up-front so we can report shortfalls
        # after generation. For enroute, the per-airport quotas are
        # authoritative when populated; otherwise we fall back to the
        # aggregate num_arrivals / num_departures values.
        req_arr = sum(self.per_airport_arrival_counts.values()) or num_arrivals
        req_dep = sum(self.per_airport_departure_counts.values()) or num_departures
        req_enr = num_enroute
        req_ovf = num_overflight
        requested_total = req_arr + req_dep + req_enr + req_ovf
        counts_before: Dict[str, int] = {'total': len(self.aircraft)}

        # Generate aircraft from pools in parallel using threading.
        counts: Dict[str, int] = {
            'departures': 0, 'arrivals': 0, 'enroute': 0, 'overflight': 0,
        }

        def _run_generation(targets: Dict[str, int]) -> None:
            """Submit the requested-per-type targets in parallel and tally
            how many of each type were actually produced."""
            futures: Dict[str, concurrent.futures.Future] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                if targets.get('departures', 0) > 0 and departures_pool:
                    logger.info(f"Generating {targets['departures']} departure aircraft...")
                    futures['departures'] = executor.submit(
                        self._generate_departure_aircraft,
                        targets['departures'], departures_pool,
                        difficulty_config_departures, departure_airport_runways,
                    )
                if targets.get('arrivals', 0) > 0 and arrivals_pool:
                    logger.info(f"Generating {targets['arrivals']} arrival aircraft...")
                    futures['arrivals'] = executor.submit(
                        self._generate_arrival_aircraft,
                        targets['arrivals'], arrivals_pool, difficulty_config_arrivals,
                    )
                if targets.get('enroute', 0) > 0 and transient_pool:
                    logger.info(f"Generating {targets['enroute']} enroute aircraft...")
                    futures['enroute'] = executor.submit(
                        self._generate_enroute_aircraft,
                        targets['enroute'], transient_pool, difficulty_config_enroute,
                    )
                if targets.get('overflight', 0) > 0 and transient_pool:
                    logger.info(f"Generating {targets['overflight']} overflight aircraft...")
                    futures['overflight'] = executor.submit(
                        self._generate_overflight_aircraft,
                        targets['overflight'], transient_pool, difficulty_config_enroute,
                    )
                for gen_type, future in futures.items():
                    try:
                        produced = int(future.result() or 0)
                        counts[gen_type] += produced
                        logger.debug(f"Completed {gen_type} generation: {produced}")
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Error generating {gen_type} aircraft: {e}")

        initial_targets = {
            'departures': num_departures,
            'arrivals': num_arrivals,
            'enroute': num_enroute,
            'overflight': num_overflight,
        }
        _run_generation(initial_targets)

        # Top-up passes: if a type came in under its requested count, run
        # it again for the deficit. When a pass produces zero new aircraft
        # (pool is drained), fetch additional flights from the API using
        # paginated offsets and keep going — the DB holds millions of
        # flights so we shouldn't ever truly run out.
        requested = {
            'departures': req_dep, 'arrivals': req_arr,
            'enroute': req_enr, 'overflight': req_ovf,
        }
        api_offsets = {'departures': 0, 'arrivals': 0, 'transient': 0}
        # Track how many we've pulled so the next fetch starts past the
        # current pool. Pagination nudges: 500 departures/arrivals per refill,
        # 1000 transient per refill.
        REFILL_DEP = 500
        REFILL_ARR = 500
        REFILL_TRANSIENT = 1000
        # Initial fetches consumed target_pool_size(num_required) from offset 0.
        from utils.data_pipeline.flight_pool import target_pool_size
        api_offsets['departures'] = target_pool_size(num_departures) if num_departures else 0
        api_offsets['arrivals'] = target_pool_size(num_arrivals) if num_arrivals else 0
        api_offsets['transient'] = target_pool_size(num_enroute) if num_enroute else 0

        MAX_TOPUP_PASSES = 5
        for pass_n in range(1, MAX_TOPUP_PASSES + 1):
            deficit = {
                k: max(0, requested[k] - counts[k]) for k in requested
            }
            total_deficit = sum(deficit.values())
            if total_deficit <= 0:
                break
            logger.info(
                f"Top-up pass {pass_n}: deficit {deficit} "
                f"(total {total_deficit}); rerunning shortfall types"
            )
            before = dict(counts)
            _run_generation(deficit)
            produced_this_pass = sum(counts[k] - before[k] for k in counts)
            if produced_this_pass > 0:
                continue
            # Zero produced — current pools are drained for the types in
            # deficit. Refill from the API at the next pagination window
            # and let the next top-up pass consume them.
            logger.info(
                f"Top-up pass {pass_n} stalled; refilling flight pools "
                f"from API (offsets={api_offsets})"
            )
            refilled_any = False
            if deficit.get('departures', 0) > 0 and departure_airports:
                more = self._fetch_pool_departures(
                    departure_airports,
                    start_offset=api_offsets['departures'],
                    target_override=REFILL_DEP,
                )
                if more:
                    # Dedupe against current pool by GUFI so we don't re-add
                    # flights already rejected. Pool filters already applied.
                    seen = {f.get('gufi') for f in departures_pool if f.get('gufi')}
                    new = [f for f in more if f.get('gufi') not in seen]
                    departures_pool.extend(new)
                    api_offsets['departures'] += REFILL_DEP
                    logger.info(
                        f"Departures refill: +{len(new)} new "
                        f"(pool now {len(departures_pool)})"
                    )
                    refilled_any = refilled_any or bool(new)
            if (deficit.get('arrivals', 0) > 0) and arrival_airports:
                more = self._fetch_pool_arrivals(
                    arrival_airports,
                    start_offset=api_offsets['arrivals'],
                    target_override=REFILL_ARR,
                )
                if more:
                    seen = {f.get('gufi') for f in arrivals_pool if f.get('gufi')}
                    new = [f for f in more if f.get('gufi') not in seen]
                    arrivals_pool.extend(new)
                    api_offsets['arrivals'] += REFILL_ARR
                    logger.info(
                        f"Arrivals refill: +{len(new)} new "
                        f"(pool now {len(arrivals_pool)})"
                    )
                    refilled_any = refilled_any or bool(new)
            if deficit.get('enroute', 0) > 0 or deficit.get('overflight', 0) > 0:
                more = self._fetch_pool_transient(
                    arrival_airports or [],
                    start_offset=api_offsets['transient'],
                    target_override=REFILL_TRANSIENT,
                )
                if more:
                    seen = {f.get('gufi') for f in transient_pool if f.get('gufi')}
                    new = [f for f in more if f.get('gufi') not in seen]
                    transient_pool.extend(new)
                    api_offsets['transient'] += REFILL_TRANSIENT
                    logger.info(
                        f"Transient refill: +{len(new)} new "
                        f"(pool now {len(transient_pool)})"
                    )
                    refilled_any = refilled_any or bool(new)
            if not refilled_any:
                logger.warning(
                    f"Top-up pass {pass_n}: API returned no new flights "
                    f"at offset {api_offsets}; true end of data. Stopping."
                )
                break

        # Apply spawn delays across all aircraft
        self.apply_spawn_delays(self.aircraft, spawn_delay_mode, delay_value, total_session_minutes)

        # Distance-based spawn spacing. When no spawn delay is configured we
        # need ≥ 20 NM physical separation between aircraft sharing a route;
        # with a spawn delay the temporal offset can close the gap so long as
        # the effective separation (distance + Δt × avg groundspeed) is
        # ≥ 10 NM. Aircraft may be shifted past their arrival-band max — we
        # record a note to the conclusion screen when that happens.
        self._resolve_spawn_proximity(spawn_delay_mode)

        # Resolve enroute/overflight altitude conflicts: no two in-flight
        # aircraft may spawn within 10 NM of each other at the same cruise
        # altitude. Violators get their altitude dropped in 2000 ft steps.
        self._resolve_enroute_altitude_conflicts()

        # Final verification: compare requested vs actual. Expose on the
        # instance so the bridge can surface shortfalls in the UI.
        actual_total = len(self.aircraft)
        shortfall = {
            k: max(0, requested[k] - counts[k]) for k in requested
        }
        self.generation_stats = {
            'requested_total': requested_total,
            'actual_total': actual_total,
            'requested': dict(requested),
            'actual': dict(counts),
            'shortfall': shortfall,
            'warnings': list(self.generation_warnings),
            'notes': list(self.generation_notes),
        }
        if actual_total < requested_total:
            nonzero = {k: v for k, v in shortfall.items() if v > 0}
            logger.warning(
                f"Generation shortfall: produced {actual_total} of "
                f"{requested_total} requested aircraft for ARTCC "
                f"{self.artcc_id}. Missing: {nonzero}"
            )
        else:
            logger.info(
                f"Generation met requested counts: {actual_total}/{requested_total} "
                f"for ARTCC {self.artcc_id} (by type: {counts})"
            )
        return self.aircraft

    def _fetch_pool_departures(self, departure_airports: List[str],
                                 start_offset: int = 0,
                                 target_override: Optional[int] = None) -> List[Dict]:
        """
        Fetch Departures Pool from API (fetches each airport individually).
        ``start_offset``/``target_override`` plumb into the API paginator so
        top-up passes can request fresh pages without refetching the initial
        block.
        """
        from utils.data_pipeline import fetch_departures as pool_fetch_deps

        all_flights = []
        # Roughly split the overall departure count across the listed airports
        # so each airport's buffer is sized proportionally.
        per_airport = max(5, getattr(self, '_num_departures_total', 20) // max(1, len(departure_airports)))
        for airport in departure_airports:
            try:
                flights, _ = pool_fetch_deps(
                    self.api_client, airport, num_required=per_airport,
                    start_offset=start_offset, target_override=target_override,
                )
                all_flights.extend(flights)
                logger.info(
                    f"Fetched {len(flights)} departures from {airport} "
                    f"(start_offset={start_offset})"
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error fetching departures from {airport}: {e}")

        if not all_flights:
            logger.warning("No departures fetched for any airports")
            return []
        filtered = self._filter_pool(all_flights, "Departures")
        logger.info(f"Departures Pool: Fetched {len(all_flights)} total, filtered to {len(filtered)}")
        return filtered

    def _fetch_pool_arrivals(self, arrival_airports: List[str],
                               start_offset: int = 0,
                               target_override: Optional[int] = None) -> List[Dict]:
        """Fetch arrivals across the configured airports via FlightPool.
        ``start_offset`` / ``target_override`` drive API pagination during
        top-up passes so we get fresh flights rather than re-parsing the
        same cached initial window."""
        from utils.data_pipeline import fetch_arrivals as pool_fetch_arrs

        all_flights = []
        per_airport = max(5, getattr(self, '_num_arrivals_total', 20) // max(1, len(arrival_airports)))
        proc_map = getattr(self, 'arrival_airport_procedures', {}) or {}
        for airport in arrival_airports:
            # Optional STAR prefix filter. The API side-matches on prefix
            # (EAGUL -> EAGUL6, EAGUL7, …), but we double-check after
            # fetch too so any historical stragglers are dropped.
            star_prefixes = proc_map.get(airport.upper()) or None
            try:
                flights, _ = pool_fetch_arrs(
                    self.api_client, airport, num_required=per_airport,
                    requested_stars=star_prefixes,
                    start_offset=start_offset, target_override=target_override,
                )
                if star_prefixes:
                    prefix_set = {p.upper() for p in star_prefixes}
                    before = len(flights)
                    flights = [
                        f for f in flights
                        if re.sub(r'\d+$', '',
                                  (f.get('arrivalProcedure') or '').upper())
                        in prefix_set
                    ]
                    if before != len(flights):
                        logger.info(
                            f"{airport}: post-filter dropped "
                            f"{before - len(flights)} arrivals not matching "
                            f"STARs {sorted(prefix_set)}"
                        )
                all_flights.extend(flights)
                logger.info(
                    f"Fetched {len(flights)} arrivals to {airport} "
                    f"(start_offset={start_offset}, "
                    f"stars={star_prefixes or 'any'})"
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Error fetching arrivals to {airport}: {e}")

        if not all_flights:
            logger.warning("No arrivals fetched for any airports")
            return []
        filtered = self._filter_pool(all_flights, "Arrivals")
        logger.info(f"Arrivals Pool: Fetched {len(all_flights)} total, filtered to {len(filtered)}")
        return filtered

    def _fetch_pool_transient(self, arrival_airports: List[str],
                                start_offset: int = 0,
                                target_override: Optional[int] = None) -> List[Dict]:
        """
        Fetch Transient Pool from API. ``start_offset``/``target_override``
        support API-paginated top-ups.

        Args:
            arrival_airports: List of arrival airports to filter out

        Returns:
            Filtered list of transient flights
        """
        try:
            from utils.data_pipeline import fetch_artcc as pool_fetch_artcc
            flights, _ = pool_fetch_artcc(
                self.api_client, self.artcc_id,
                num_required=getattr(self, '_num_enroute_total', 20),
                start_offset=start_offset, target_override=target_override,
            )
            if not flights:
                logger.warning(f"No transient flights fetched for ARTCC {self.artcc_id}")
                return []

            # Filter for valid flights with complete data (double-pass safety)
            filtered = self._filter_pool(flights, "Transient")

            # Additional filter: Remove arrivals to specified airports
            if arrival_airports:
                arrival_set = set(airport.upper() for airport in arrival_airports)
                before_count = len(filtered)
                filtered = [
                    f for f in filtered
                    if f.get('arrivalAirport', '').upper() not in arrival_set
                ]
                logger.info(f"Transient Pool: Filtered out {before_count - len(filtered)} arrivals to specified airports")

            logger.info(f"Transient Pool: Fetched {len(flights)}, filtered to {len(filtered)}")
            return filtered

        except Exception as e:
            logger.error(f"Error fetching Transient Pool: {e}")
            return []

    def _filter_pool(self, flights: List[Dict], pool_name: str) -> List[Dict]:
        """
        Filter flight pool: Validate flights have complete flight plans

        Args:
            flights: Raw flight data from API
            pool_name: Name of pool for logging

        Returns:
            Filtered list of valid flights
        """
        # API now only returns PROPOSED flights, no client-side status filtering needed
        # Apply standard validity filtering (checks for basic required fields)
        valid_flights = filter_valid_flights(flights)
        logger.debug(f"{pool_name}: {len(valid_flights)}/{len(flights)} passed validity checks")

        # Altitude is optional on every pool: the downstream aircraft factory
        # falls back to the aircraft type's cruise altitude when the API
        # record omits requestedAltitude/assignedAltitude (which, empirically,
        # is common for filed departure records at many airports).
        require_altitude = False

        # Filter for required fields and no lat/long in routes
        clean_flights = []
        missing_dep_proc = 0
        missing_arr_proc = 0

        for flight in valid_flights:
            callsign = flight.get('aircraftIdentification', '')
            route = flight.get('route', '')
            altitude = flight.get('requestedAltitude') or flight.get('assignedAltitude')
            speed = flight.get('requestedAirspeed')  # API uses 'requestedAirspeed' not 'cruiseSpeed'
            dep_proc = flight.get('departureProcedure', '')
            arr_proc = flight.get('arrivalProcedure', '')
            arrival_airport = flight.get('arrivalAirport', '')

            # NEW: For Arrivals pool, only accept flights to user-selected airports
            if pool_name == "Arrivals" and arrival_airport:
                if arrival_airport not in self.arrival_airports:
                    logger.debug(f"{pool_name}: Skipping {callsign} - arrival airport {arrival_airport} not in configured list")
                    continue

            # Procedure requirements are direction-specific. The earlier
            # version rejected every flight without BOTH procedures, which
            # killed the Departures pool to zero because filed flight plans
            # commonly carry only the SID at the origin end.
            require_dep_proc = pool_name == "Departures"
            require_arr_proc = pool_name == "Arrivals"
            if require_dep_proc and not dep_proc:
                missing_dep_proc += 1
                logger.debug(f"{pool_name}: Skipping {callsign} - missing departure procedure")
                continue
            if require_arr_proc and not arr_proc:
                missing_arr_proc += 1
                logger.debug(f"{pool_name}: Skipping {callsign} - missing arrival procedure")
                continue

            # Validate STAR name for arrivals (skip single-letter airways and missing STARs)
            if pool_name == "Arrivals" and arr_proc:
                # Skip single-letter STARs (these are airways, not STARs)
                if len(arr_proc) == 1:
                    logger.debug(f"{pool_name}: Skipping {callsign} - STAR '{arr_proc}' is single letter (likely airway)")
                    continue

                # Check if CIFP parser exists and STAR is valid
                if arrival_airport in self.cifp_parsers:
                    cifp_parser = self.cifp_parsers[arrival_airport]
                    available_stars = cifp_parser.get_available_stars()

                    # Match STAR base name (strip numbers)
                    import re
                    star_base = re.sub(r'\d+$', '', arr_proc.upper())
                    star_found = False

                    for cifp_star in available_stars:
                        cifp_star_base = re.sub(r'\d+$', '', cifp_star.upper())
                        if cifp_star_base == star_base:
                            star_found = True
                            break

                    if not star_found:
                        logger.debug(f"{pool_name}: Skipping {callsign} - STAR '{arr_proc}' not found in CIFP for {arrival_airport}")
                        continue

            # Check for lat/long in routes
            if self._has_lat_long_format(route):
                logger.debug(f"{pool_name}: Skipping {callsign} - route contains lat/long")
                continue

            # Require valid route and speed
            if not route:
                logger.debug(f"{pool_name}: Skipping {callsign} - missing route")
                continue
            if not speed:
                logger.debug(f"{pool_name}: Skipping {callsign} - missing cruise speed")
                continue

            # Altitude is only required for Arrivals/Departures
            if require_altitude and not altitude:
                logger.debug(f"{pool_name}: Skipping {callsign} - missing altitude")
                continue

            clean_flights.append(flight)

        logger.info(f"{pool_name}: Filtered to {len(clean_flights)} flights with complete data (from {len(valid_flights)} valid)")
        if missing_dep_proc > 0 or missing_arr_proc > 0:
            logger.info(f"  - Filtered out {missing_dep_proc} flights missing departure procedure")
            logger.info(f"  - Filtered out {missing_arr_proc} flights missing arrival procedure")

        return clean_flights

    def _procedure_matches_runways(self, procedure: str, active_runways: List[str],
                                   airport_icao: str, is_sid: bool) -> bool:
        """
        Check if a SID or STAR matches the active runways using CIFP data

        Args:
            procedure: SID or STAR name (e.g., "EAGUL6")
            active_runways: List of active runway identifiers (e.g., ["08", "7R"])
            airport_icao: Airport ICAO code
            is_sid: True if checking SID, False if checking STAR

        Returns:
            True if procedure is valid for at least one active runway
        """
        if not procedure:
            return False

        # Get CIFP parser for this airport
        cifp_parser = self.cifp_parsers.get(airport_icao)
        if not cifp_parser:
            logger.debug(f"No CIFP parser for {airport_icao}, accepting all procedures")
            return True

        # Strip numeric suffix from procedure name
        proc_base = re.sub(r'\d+$', '', procedure)

        # Check each active runway
        for runway in active_runways:
            if is_sid:
                # Get SIDs for this runway
                sids = cifp_parser.get_sids_for_runway(runway)
                if any(re.sub(r'\d+$', '', sid) == proc_base for sid in sids):
                    return True
            else:
                # Get STARs for this runway
                stars = cifp_parser.get_stars_for_runway(runway)
                if any(re.sub(r'\d+$', '', star) == proc_base for star in stars):
                    return True

        return False


    def _generate_enroute_aircraft(self, count: int, flight_pool: List[Dict],
                                    difficulty_config: Dict = None) -> int:
        """Generate enroute transient aircraft. Returns count actually created."""
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        if not flight_pool:
            logger.warning("No flights in Transient Pool")
            return 0

        created = 0
        attempts = 0
        max_attempts = count * 20

        while created < count and attempts < max_attempts and flight_pool:
            flight_data = random.choice(flight_pool)

            # Create enroute aircraft
            aircraft = self._create_enroute_aircraft(flight_data)

            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                # Thread-safe append
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                created += 1

            attempts += 1

        logger.info(f"Created {created} enroute aircraft (requested {count})")
        return created

    def _generate_arrival_aircraft(self, count: int, flight_pool: List[Dict],
                                    difficulty_config: Dict = None) -> int:
        """Generate arrival aircraft with per-airport quotas when configured.
        Returns count actually created."""
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        if not flight_pool:
            logger.warning("No flights in Arrivals Pool")
            return 0

        # Use the scenario-scoped persistent remaining dict so top-up passes
        # only generate the quota that's actually still outstanding.
        remaining = self._arrival_remaining
        use_quotas = remaining is not None
        target = min(count, sum(remaining.values())) if use_quotas else count

        created = 0
        attempts = 0
        max_attempts = max(target * 20, 20)

        while created < target and attempts < max_attempts and flight_pool:
            if use_quotas:
                # Pick only from flights whose destination still has quota.
                eligible = [
                    f for f in flight_pool
                    if remaining.get((f.get('arrivalAirport') or '').upper(), 0) > 0
                ]
                if not eligible:
                    logger.info("All per-airport arrival quotas filled")
                    break
                flight_data = random.choice(eligible)
            else:
                flight_data = random.choice(flight_pool)

            aircraft = self._create_arrival_aircraft(flight_data)
            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                if use_quotas:
                    dest = (flight_data.get('arrivalAirport') or '').upper()
                    if dest in remaining:
                        remaining[dest] = max(0, remaining[dest] - 1)
                created += 1

            attempts += 1

        if use_quotas:
            short = {a: n for a, n in remaining.items() if n > 0}
            logger.info(
                f"Created {created} arrival aircraft this pass "
                f"(target {target}); remaining per-airport: "
                f"{short if short else 'all quotas filled'}"
            )
        else:
            logger.info(f"Created {created} arrival aircraft (requested {target})")
        return created

    def _generate_departure_aircraft(self, count: int, flight_pool: List[Dict],
                                      difficulty_config: Dict = None,
                                      departure_airport_runways: Dict[str, List[str]] = None) -> int:
        """Generate departure aircraft at parking spots. Returns count created."""
        from pathlib import Path

        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)

        if not flight_pool:
            logger.warning("No flights in Departures Pool")
            return

        # Get unique departure airports from pool
        departure_airports = set()
        for flight in flight_pool:
            dep_airport = flight.get('departureAirport', '').upper()
            if dep_airport:
                departure_airports.add(dep_airport)

        # Resolve each departure airport's geojson through the lazy map,
        # which already uses `resource_path()` to find `airport_data/*` in
        # both dev mode and packaged builds. The previous hand-rolled
        # `Path('airport_data')` check was CWD-relative and failed silently
        # under the PyInstaller-packaged electron app.
        valid_airports = {}
        for airport_icao in departure_airports:
            parser = self.geojson_parsers.get(airport_icao)
            if parser:
                valid_airports[airport_icao] = parser
                logger.debug(f"Loaded geojson for {airport_icao}")
            else:
                logger.warning(
                    f"WARNING: No geojson available for {airport_icao}; "
                    f"departures from this airport will be skipped"
                )

        if not valid_airports:
            logger.error("ERROR: No valid airport GeoJSON data available for departure aircraft spawning")
            logger.error(f"Skipping {count} requested departure aircraft")
            return 0

        # Collect all parking spots from valid airports. If an airport's
        # geojson has no parking spots but does contain runway geometry, fall
        # back to spawning at the runway threshold (the active runways for
        # this airport, if configured).
        from models.airport import ParkingSpot

        all_parking_spots = []
        airport_parking_map = {}

        for airport_icao, geojson_parser in valid_airports.items():
            parking_spots = geojson_parser.get_parking_spots()
            logger.info(f"Found {len(parking_spots)} parking spots at {airport_icao}")

            if parking_spots:
                for spot in parking_spots:
                    all_parking_spots.append(spot)
                    airport_parking_map[spot.name] = airport_icao
                continue

            # Runway-threshold fallback.
            active_for_airport = (departure_airport_runways or {}).get(airport_icao) or []
            runways = geojson_parser.get_runways() or []
            synthesized = 0
            for runway in runways:
                try:
                    ends = runway.get_runway_ends()
                except Exception:  # noqa: BLE001
                    continue
                for end in ends:
                    clean_end = end.replace('RW', '').strip().upper()
                    if active_for_airport and clean_end not in [r.upper() for r in active_for_airport]:
                        continue
                    try:
                        lat, lon = runway.get_threshold_position(end)
                        heading = int(runway.get_runway_heading(end))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(f"Skipping runway end {end} at {airport_icao}: {exc}")
                        continue
                    fake_spot = ParkingSpot(
                        name=f"RW{clean_end}@{airport_icao}",
                        latitude=lat, longitude=lon, heading=heading,
                    )
                    all_parking_spots.append(fake_spot)
                    airport_parking_map[fake_spot.name] = airport_icao
                    synthesized += 1
            if synthesized:
                logger.info(
                    f"No parking data at {airport_icao}; synthesized {synthesized} "
                    f"runway-threshold spawn points"
                )

        if not all_parking_spots:
            logger.error("ERROR: No parking spots found in airport GeoJSON data")
            logger.error(f"Skipping {count} requested departure aircraft")
            return 0

        if count > len(all_parking_spots):
            logger.warning(f"Requested {count} departures but only {len(all_parking_spots)} parking spots available")
            count = len(all_parking_spots)

        # Shuffle parking spots for variety
        random.shuffle(all_parking_spots)

        # Persistent per-airport remaining — top-up passes must not regenerate
        # the full quota on top of aircraft already created in earlier passes.
        remaining = self._departure_remaining
        use_quotas = remaining is not None
        if use_quotas:
            count = min(count, sum(remaining.values()))

        created = 0
        for spot in all_parking_spots:
            if created >= count:
                break

            # Get the airport for this parking spot
            airport_icao = airport_parking_map[spot.name]

            # Skip spots at airports whose quota is already filled.
            if use_quotas and remaining.get(airport_icao, 0) <= 0:
                continue

            # Filter flights departing from this airport
            airport_flights = [f for f in flight_pool if f.get('departureAirport', '').upper() == airport_icao]

            if not airport_flights:
                logger.debug(f"No flights available for departure airport {airport_icao}")
                continue

            # If active runways specified for this airport, filter by SID compatibility
            active_runways = departure_airport_runways.get(airport_icao) if departure_airport_runways else None

            if active_runways:
                # Filter flights with SIDs that match active runways
                valid_flights = []
                for flight in airport_flights:
                    sid = flight.get('departureProcedure', '')
                    if not sid or self._procedure_matches_runways(sid, active_runways, airport_icao, is_sid=True):
                        valid_flights.append(flight)

                if valid_flights:
                    airport_flights = valid_flights
                    logger.debug(f"Filtered to {len(valid_flights)} flights with valid SIDs for runways {active_runways} at {airport_icao}")
                else:
                    logger.warning(f"No flights with valid SIDs for runways {active_runways} at {airport_icao}, using any available flight")

            flight_data = random.choice(airport_flights)

            aircraft = self._create_departure_aircraft(flight_data, spot, airport_icao)

            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                # Thread-safe append
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                if use_quotas:
                    remaining[airport_icao] = max(0, remaining[airport_icao] - 1)
                created += 1

        if use_quotas:
            short = {a: n for a, n in remaining.items() if n > 0}
            logger.info(
                f"Created {created} departure aircraft this pass "
                f"(target {count}); remaining per-airport: "
                f"{short if short else 'all quotas filled'}"
            )
        else:
            logger.info(f"Created {created} departure aircraft at parking spots (requested {count})")
        return created

    def _generate_overflight_aircraft(self, count: int, flight_pool: List[Dict],
                                       difficulty_config: Dict = None) -> int:
        """Generate overflight aircraft that enter the ARTCC from a neighbor.

        Shares the transient flight pool (any flight whose filed route crosses
        our airspace but whose destination is outside our configured arrival
        list). The spawn position is offset ~15 NM outside the ARTCC boundary
        on the reverse bearing from the first inside-ARTCC waypoint, with
        heading pointed AT that waypoint — so the aircraft appears to be
        handed off from the adjacent facility.
        """
        difficulty_list, difficulty_index = self._setup_difficulty_assignment(difficulty_config)
        if not flight_pool:
            logger.warning("No flights in pool for overflights")
            return 0

        created = 0
        attempts = 0
        max_attempts = count * 20

        while created < count and attempts < max_attempts and flight_pool:
            flight_data = random.choice(flight_pool)
            aircraft = self._create_overflight_aircraft(flight_data)
            if aircraft:
                difficulty_index = self._assign_difficulty(aircraft, difficulty_list, difficulty_index)
                with self.aircraft_lock:
                    self.aircraft.append(aircraft)
                created += 1
            attempts += 1

        logger.info(f"Created {created} overflight aircraft (requested {count})")
        return created

    def _find_overflight_spawn_on_route(self, route: str) -> Optional[Dict]:
        """Return a spawn state for an overflight: position offset between
        ``overflight_spawn_band`` NM outside the ARTCC boundary on the reverse
        bearing from the first waypoint that's inside the ARTCC.

        Returns dict matching `_find_spawn_waypoint_on_route`'s contract:
        `{waypoint, latitude, longitude, heading, initial_route}`.
        """
        from utils.geo_utils import calculate_bearing, calculate_destination

        waypoints = self.route_parser.parse_route_string(route)
        if not waypoints:
            return None
        route_coords = self.route_parser.get_route_waypoint_coordinates(waypoints)
        if len(route_coords) < 2:
            return None

        # Find the first waypoint that's inside the ARTCC — that's our
        # handoff/entry point.
        entry_idx = None
        for i, (wp_name, lat, lon) in enumerate(route_coords):
            if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
                entry_idx = i
                break
        if entry_idx is None:
            return None

        entry_name, entry_lat, entry_lon = route_coords[entry_idx]

        # Establish the "outbound from the boundary" bearing:
        # - If there's a waypoint upstream (outside ARTCC), use its bearing
        #   to the entry waypoint — that's the actual approach direction.
        # - Otherwise fall back to the bearing FROM the NEXT in-ARTCC waypoint
        #   TO the entry, which still points roughly into our airspace.
        if entry_idx > 0:
            up_name, up_lat, up_lon = route_coords[entry_idx - 1]
            inbound_heading = calculate_bearing(up_lat, up_lon, entry_lat, entry_lon)
        elif entry_idx + 1 < len(route_coords):
            nxt_name, nxt_lat, nxt_lon = route_coords[entry_idx + 1]
            inbound_heading = calculate_bearing(entry_lat, entry_lon, nxt_lat, nxt_lon)
        else:
            return None

        # Sanity check: the inbound heading should actually point toward the
        # flight's downstream waypoints. If the filed route has at least one
        # more in-ARTCC waypoint, the bearing from entry to that waypoint
        # should be within 90° of the inbound_heading — otherwise we've
        # resolved waypoints out of order and would spawn the aircraft
        # pointing the wrong way.
        if entry_idx + 1 < len(route_coords):
            _, dn_lat, dn_lon = route_coords[entry_idx + 1]
            downstream_bearing = calculate_bearing(entry_lat, entry_lon, dn_lat, dn_lon)
            if abs((inbound_heading - downstream_bearing + 540) % 360 - 180) > 90:
                logger.debug(
                    f"Overflight entry heading {inbound_heading} conflicts with "
                    f"downstream bearing {downstream_bearing}; rejecting to avoid "
                    f"opposite-direction spawn"
                )
                return None

        # Place the aircraft in a configurable band BEHIND the entry waypoint
        # on the reverse bearing, still pointed AT the entry (matches what
        # the adjacent facility would see on their scope just before handoff).
        min_nm, max_nm = getattr(self, 'overflight_spawn_band', (10.0, 25.0))
        offset_nm = random.uniform(min_nm, max_nm) if max_nm > min_nm else min_nm
        reverse_bearing = (inbound_heading + 180) % 360
        spawn_lat, spawn_lon = calculate_destination(entry_lat, entry_lon, reverse_bearing, offset_nm)

        # Initial navigation: target the entry waypoint, then the rest of
        # the route. Start the initial_route at the entry waypoint.
        remainder = ' '.join(wp for wp, _, _ in route_coords[entry_idx:])
        return {
            'waypoint': entry_name,
            'latitude': spawn_lat,
            'longitude': spawn_lon,
            'heading': int(inbound_heading),
            'initial_route': remainder,
        }

    def _create_overflight_aircraft(self, flight_data: Dict) -> Optional[Aircraft]:
        """Build a single overflight aircraft. Same API-data plumbing as
        `_create_enroute_aircraft` but spawns at the boundary-entry position.
        """
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')
        departure = flight_data.get('departureAirport', 'KORD')
        arrival = flight_data.get('arrivalAirport', 'KLAX')

        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        clean_route = clean_route_string(filed_route)
        spawn_info = self._find_overflight_spawn_on_route(clean_route)
        if not spawn_info:
            logger.debug(f"No ARTCC boundary-entry found for {callsign}; skipping overflight")
            with self.callsign_lock:
                self.used_callsigns.discard(callsign)
            return None

        # Let two overflights share an entry waypoint (they're offset 15 NM
        # apart along the airway already); only dedupe if the exact lat/lon
        # pair collides. Key by rounded position.
        spawn_key = f"OVF:{round(spawn_info['latitude'], 3)},{round(spawn_info['longitude'], 3)}"
        with self.spawn_point_lock:
            if spawn_key in self.used_spawn_points:
                with self.callsign_lock:
                    self.used_callsigns.discard(callsign)
                return None
            self.used_spawn_points.add(spawn_key)

        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            try:
                altitude = int(float(requested_alt))
            except (ValueError, TypeError):
                altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        else:
            altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        cruise_altitude = str(altitude)

        cruise_kias, ground_speed, mach_value = self._derive_airborne_speed(
            flight_data, aircraft_type, altitude, on_star=False,
        )

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=spawn_info['latitude'],
            longitude=spawn_info['longitude'],
            altitude=altitude,
            # No explicit heading — vNAS derives it from navigationPath's
            # first fix (the entry waypoint). Providing a heading caused
            # aircraft to spawn pointing the wrong way when the magnetic /
            # waypoint-database coordinates disagreed.
            heading=0,
            ground_speed=ground_speed,
            # Spawn at a bare lat/lon (no fix) — the aircraft isn't yet over
            # the entry waypoint, it's outside the boundary. vNAS handles
            # FixOrFrd spawns or we leave starting_conditions_type default.
            starting_conditions_type='FixOrFrd',
            fix=spawn_info['waypoint'],
            departure=departure,
            arrival=arrival,
            route=clean_route,
            navigation_path=spawn_info.get('initial_route') or clean_route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_kias,
            mach=mach_value,
            flight_rules="I",
            primary_airport=None,
            spawn_delay=None,
        )
        return aircraft

    def _create_enroute_aircraft(self, flight_data: Dict) -> Optional[Aircraft]:
        """Create enroute transient aircraft spawned along their route within ARTCC"""
        # Extract flight data - preserve API route exactly
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')  # Keep exact API route
        departure = flight_data.get('departureAirport', 'KORD')
        arrival = flight_data.get('arrivalAirport', 'KLAX')

        # Check callsign uniqueness (thread-safe)
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        # Add equipment suffix
        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        # Find spawn waypoint along route within ARTCC (use clean version for parsing only)
        clean_route = clean_route_string(filed_route)
        spawn_info = self._find_spawn_waypoint_on_route(clean_route, is_arrival=False)

        if not spawn_info:
            logger.debug(f"Could not find spawn waypoint for {callsign} on route: {filed_route}")
            self.used_callsigns.remove(callsign)  # Return callsign to pool
            return None

        # Reserve the spawn waypoint. If it's already in use by another
        # enroute aircraft, shift this one 20 NM back along its filed route
        # (creating an FRD spawn upstream) and let it proceed to the original
        # waypoint as its first navigation fix.
        reserve_input = dict(spawn_info)
        reserve_input['fix'] = spawn_info['waypoint']
        reserve_input['starting_conditions_type'] = 'Fix'
        reserved = self._reserve_spawn_or_shift_back(
            reserve_input, prefix='ENR', callsign=callsign,
        )
        if reserved is None:
            with self.callsign_lock:
                self.used_callsigns.discard(callsign)
            return None

        # Get filed altitude from API, or estimate if not available
        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            altitude = int(float(requested_alt))
        else:
            # API doesn't provide altitude for PROPOSED flights, estimate it
            altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
            logger.debug(f"{callsign}: Estimated altitude {altitude} ft (API data not available)")
        cruise_altitude = str(altitude)

        cruise_kias, ground_speed, mach_value = self._derive_airborne_speed(
            flight_data, aircraft_type, altitude, on_star=False,
        )

        # Navigation path: next waypoint after spawn, followed by remainder of filed route.
        # If this spawn was shifted back due to a collision, prepend the original
        # waypoint so the aircraft flies to it first, then continues on the route.
        if reserved.get('_shifted_back'):
            original_wp = spawn_info['waypoint']
            remainder = spawn_info.get('initial_route', '') or ''
            initial_route = original_wp + ((' ' + remainder) if remainder else '')
            spawn_lat = reserved['latitude']
            spawn_lon = reserved['longitude']
            spawn_fix = reserved['fix']
            starting_type = 'FixOrFrd'
        else:
            # When the aircraft spawns exactly on a named waypoint, its nav
            # path must start at the NEXT fix — not the waypoint it's already
            # over. `initial_route` from the spawn finder already excludes the
            # current waypoint. If it's empty (spawn landed on the last route
            # waypoint), fall back to the arrival airport rather than the full
            # filed route (which would re-include the spawn fix as the first
            # nav token).
            initial_route = spawn_info.get('initial_route') or arrival
            spawn_lat = spawn_info['latitude']
            spawn_lon = spawn_info['longitude']
            spawn_fix = spawn_info['waypoint']
            starting_type = 'Fix'

        # Create aircraft
        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=spawn_lat,
            longitude=spawn_lon,
            altitude=altitude,
            # Heading left to vNAS — computed from the first fix in
            # navigationPath (the next waypoint on the filed route).
            heading=0,
            ground_speed=ground_speed,
            starting_conditions_type=starting_type,
            fix=spawn_fix,
            departure=departure,
            arrival=arrival,
            route=clean_route,  # Cleaned route (dots to spaces, airports/time removed)
            navigation_path=initial_route or arrival,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_kias,
            mach=mach_value,
            flight_rules="I",
            primary_airport=None,
            spawn_delay=None
        )

        return aircraft

    def _create_arrival_aircraft(self, flight_data: Dict) -> Optional[Aircraft]:
        """Create arrival aircraft spawned inside ARTCC at a distance-from-
        destination band. Prefers real waypoints on the filed route or STAR;
        synthesizes an FRD-style point along the route leg if the band falls
        between named waypoints."""
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')
        departure = flight_data.get('departureAirport', 'KORD')
        arrival = flight_data.get('arrivalAirport', 'KPHX')
        arr_proc = flight_data.get('arrivalProcedure', '')

        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        # Per-airport band overrides the scenario-wide default.
        scenario_band = getattr(self, 'arrival_spawn_band',
                                self.DEFAULT_ARRIVAL_BAND_NM)
        per_airport_bands = getattr(self, 'per_airport_arrival_bands', {}) or {}
        min_nm, max_nm = per_airport_bands.get(arrival.upper(), scenario_band)

        spawn = self._find_arrival_spawn_on_route(filed_route, arrival, arr_proc,
                                                   min_nm, max_nm)
        if not spawn:
            logger.debug(f"No arrival spawn in [{min_nm},{max_nm}] NM from {arrival} for {callsign}")
            with self.callsign_lock:
                self.used_callsigns.discard(callsign)
            return None

        # Use the CIFP-resolved STAR name for downstream procedure strings.
        actual_star_name = spawn.get('actual_star_name') or arr_proc
        arr_proc = actual_star_name or arr_proc

        # Collision handling: reject a named-waypoint spawn if another aircraft
        # already occupies it, and shift this one 20 NM back along the filed
        # route — creating an FRD spawn upstream of the collision. Retry up
        # to a few times if the shifted point also collides.
        spawn = self._reserve_spawn_or_shift_back(
            spawn, prefix='ARR', callsign=callsign,
        )
        if spawn is None:
            with self.callsign_lock:
                self.used_callsigns.discard(callsign)
            return None

        # Altitude priority:
        # 1. CIFP altitude constraint at the chosen STAR waypoint (the
        #    published crossing altitude — always authoritative when present).
        # 2. Rule-of-3s profile from spawn distance-to-destination, capped at
        #    the type's typical cruise. This covers both FRD spawns on the
        #    filed route and un-constrained STAR waypoints, and keeps aircraft
        #    at sensible descending altitudes as they approach the field.
        star_wp_obj = spawn.get('star_waypoint_obj')
        dist_to_dest = spawn.get('distance_to_dest_nm')
        if star_wp_obj is not None and (star_wp_obj.max_altitude or star_wp_obj.min_altitude):
            altitude = self._get_altitude_from_cifp(star_wp_obj, arr_proc, departure, arrival, aircraft_type)
        elif dist_to_dest is not None:
            altitude = self._rule_of_3s_altitude(dist_to_dest, aircraft_type)
        else:
            altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        cruise_altitude = str(altitude)

        on_star = bool(spawn.get('on_star'))
        cruise_kias, ground_speed, mach_value = self._derive_airborne_speed(
            flight_data, aircraft_type, altitude, on_star=on_star,
        )

        # Extract 3-letter airport code from ICAO (e.g., KPHX -> PHX)
        arrival_3letter = arrival[1:] if arrival.startswith('K') else arrival[-3:]

        # Runway assignment unchanged.
        arrival_runway = None
        if arr_proc and arrival in self.arrival_airport_runways:
            active_runways = self.arrival_airport_runways[arrival]
            arrival_runway = self._get_runway_for_star(arrival, arr_proc, active_runways)

        # Navigation path: next waypoint (if spawn was on STAR, the next STAR
        # waypoint; otherwise the STAR itself) + procedure + runway suffix.
        navigation_path = self._build_arrival_navigation_path(
            arrival, arr_proc, arrival_runway, spawn,
        )

        clean_route = clean_route_string(filed_route)

        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=spawn['latitude'],
            longitude=spawn['longitude'],
            altitude=altitude,
            # Heading intentionally left at 0 — vNAS derives initial heading
            # from the first fix in navigationPath. Providing an explicit
            # heading here was the root cause of wrong-direction spawns.
            heading=0,
            ground_speed=ground_speed,
            starting_conditions_type=spawn['starting_conditions_type'],
            fix=spawn['fix'],
            departure=departure,
            arrival=arrival,
            route=clean_route,
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_kias,
            mach=mach_value,
            navigation_path=navigation_path,
            arrival_runway=arrival_runway,
            star=arr_proc,
            flight_rules="I",
            primary_airport=arrival_3letter,
            spawn_delay=None,
        )
        # Stash polyline context so `_resolve_spawn_proximity` can shift
        # this aircraft further back along its filed route if another
        # aircraft spawns too close (physical or time-adjusted).
        aircraft._spawn_ctx = {
            'polyline_coords': spawn.get('_polyline_coords'),
            'polyline_names': spawn.get('_polyline_names'),
            'forward_nm': spawn.get('_polyline_forward_nm'),
            'anchor_lat': spawn.get('_anchor_lat'),
            'anchor_lon': spawn.get('_anchor_lon'),
            'actual_star_name': spawn.get('actual_star_name'),
            'arrival_airport': arrival,
            'min_nm': min_nm,
            'max_nm': max_nm,
        }
        return aircraft

    def _build_arrival_navigation_path(self, arrival_icao: str, star_name: str,
                                        arrival_runway: Optional[str],
                                        spawn: Dict) -> str:
        """Compose the vNAS navigation path for an arrival.

        Format:
          * Flight plan ending in a STAR: ``<downstream filed fixes> <STAR>[.<rwy>]``
            — runway suffix appended only when the STAR actually publishes
            runway transitions in CIFP. Pure "ALL"/common-segment STARs
            (e.g. BEAHR3 at KELP) get no runway suffix.
          * Flight plan with no STAR: ``<downstream filed fixes> <airport>``
            — fly the remainder of the filed route direct to the field.

        The first token is always the **next** waypoint the aircraft flies
        to, never the spawn fix itself.
        """
        cifp_parser = self.cifp_parsers.get(arrival_icao)
        # Does this arrival actually end in a STAR the CIFP knows?
        has_star = False
        if star_name and cifp_parser is not None:
            star_wps = getattr(cifp_parser, 'star_waypoints', {}).get(star_name, {})
            has_star = bool(star_wps)

        # Does the STAR publish runway-specific transitions? If only an
        # "ALL"/common segment exists, vNAS should see ``<STAR>`` alone; the
        # ``.<rwy>`` suffix asks for a non-existent procedure branch.
        has_runway_transitions = False
        if has_star:
            star_wps = cifp_parser.star_waypoints.get(star_name, {})
            for wp in star_wps.values():
                tn = (getattr(wp, 'transition_name', '') or '').upper()
                if re.match(r'^RW\d{1,2}[LCRB]?$', tn):
                    has_runway_transitions = True
                    break

        # Build the trailing procedure/airport token.
        if has_star:
            if has_runway_transitions and arrival_runway:
                rwy_suffix = self._star_runway_suffix(
                    arrival_icao, star_name, arrival_runway,
                    self.arrival_airport_runways.get(arrival_icao, []),
                )
                tail = f"{star_name}.{rwy_suffix}"
            else:
                tail = star_name
        else:
            tail = arrival_icao

        # Build the prefix (downstream fly-to fixes). vNAS rejects a nav
        # path that's only ``<STAR>.<rwy>`` with no preceding fly-to fix, so
        # we chain fallbacks until we have at least one fix before the tail.
        prefix: List[str] = []
        spawn_upper = str(spawn.get('fix', '')).upper()

        def _fill(src_list: List[str]) -> None:
            for name in src_list:
                if name:
                    prefix.append(name)

        if has_star and spawn.get('on_star'):
            # Aircraft is on the STAR — use segment-aware traversal.
            nxt = self._next_star_waypoint(
                cifp_parser, star_name, spawn['fix'], arrival_runway,
            )
            if nxt:
                prefix.append(nxt)

        if not prefix and spawn.get('boundary_entry'):
            # Boundary-entry spawn: aircraft is outside the ARTCC, flying
            # toward the entry waypoint, then any filed-route fixes past it.
            entry = spawn.get('boundary_entry_name')
            if entry:
                prefix.append(entry)
            for name in spawn.get('_downstream_filed_fixes') or []:
                if name.upper() != (entry or '').upper():
                    prefix.append(name)

        if not prefix:
            # Filed-route or FRD spawn: remaining filed-route tokens past
            # the spawn. Handles the `... ABQ SLNNK WAZKO1` case cleanly.
            _fill(spawn.get('_downstream_filed_fixes') or [])

        if not prefix and has_star and cifp_parser is not None:
            # Last-resort: the FRD anchor may be a STAR waypoint (e.g.
            # spawn ``BRMLY142001`` off BRMLY on LOWBO3). ``_next_star_waypoint``
            # strips the FRD form and walks the STAR's own graph. If nothing
            # matches, fall back to the STAR's first common-segment fix so
            # the nav path at least resolves in vNAS.
            nxt = self._next_star_waypoint(
                cifp_parser, star_name, spawn['fix'], arrival_runway,
            )
            if not nxt:
                nxt = self._first_common_star_waypoint(cifp_parser, star_name)
            if nxt:
                prefix.append(nxt)

        # Dedupe consecutive entries and drop anything that echoes the spawn
        # fix (aircraft is already there).
        cleaned_prefix: List[str] = []
        for name in prefix:
            if not name:
                continue
            if name.upper() == spawn_upper:
                continue
            if cleaned_prefix and cleaned_prefix[-1].upper() == name.upper():
                continue
            cleaned_prefix.append(name)

        tokens = cleaned_prefix + [tail]
        tokens = [t for t in tokens if t]
        if not tokens:
            tokens = [arrival_icao]
        return ' '.join(tokens)

    def _derive_airborne_speed(self, flight_data: Dict, aircraft_type: str,
                                altitude_ft: int, on_star: bool):
        """Return ``(cruise_kias, ground_speed, mach_or_none)`` for an airborne
        aircraft. Filed KIAS comes from the API when available, else from the
        type lookup. Above FL200 and not on a STAR we set cruise Mach and
        derive ground speed from it; otherwise ground speed is estimated from
        KIAS + altitude."""
        from utils.speed_estimator import (
            cruise_mach, ground_speed_from_mach, ground_speed_from_kias,
            indicated_cruise_kias,
        )
        filed_speed = flight_data.get('requestedAirspeed')
        try:
            cruise_kias = int(float(filed_speed)) if filed_speed else indicated_cruise_kias(aircraft_type)
        except (TypeError, ValueError):
            cruise_kias = indicated_cruise_kias(aircraft_type)

        use_mach = (altitude_ft >= 20000) and not on_star
        if use_mach:
            mach_value = cruise_mach(aircraft_type)
            ground_speed = ground_speed_from_mach(mach_value, altitude_ft)
            return cruise_kias, ground_speed, round(mach_value, 2)
        ground_speed = ground_speed_from_kias(cruise_kias, altitude_ft)
        return cruise_kias, ground_speed, None

    def _create_departure_aircraft(self, flight_data: Dict, parking_spot, airport_icao: str) -> Optional[Aircraft]:
        """Create departure aircraft at parking spot"""
        # Extract flight data - clean route for vNAS
        callsign = flight_data.get('aircraftIdentification', '')
        aircraft_type = flight_data.get('aircraftType', 'B738')
        filed_route = flight_data.get('route', '')
        departure = airport_icao  # Use the actual departure airport from parking assignment
        arrival = flight_data.get('arrivalAirport', 'KORD')
        dep_proc = flight_data.get('departureProcedure', '')  # Fixed: was 'departureProc', should be 'departureProcedure'

        # Check callsign uniqueness (thread-safe)
        with self.callsign_lock:
            if callsign in self.used_callsigns:
                return None
            self.used_callsigns.add(callsign)

        aircraft_type = self._add_equipment_suffix(aircraft_type, False)

        # Clean route for vNAS (convert dots to spaces, remove airports/time)
        clean_route = clean_route_string(filed_route)

        # Extract 3-letter airport code from ICAO (e.g., KPHX -> PHX)
        departure_3letter = departure[1:] if departure.startswith('K') else departure[-3:]

        # The filter relaxed the altitude/speed requirement (many filed plans
        # omit these fields), so fall back to the aircraft-type defaults when
        # the API didn't supply a value.
        requested_alt = flight_data.get('requestedAltitude') or flight_data.get('assignedAltitude')
        if requested_alt:
            try:
                cruise_altitude = str(int(float(requested_alt)))
            except (ValueError, TypeError):
                cruise_altitude = '35000'
        else:
            cruise_altitude = '35000'  # sensible jet cruise default

        filed_speed = flight_data.get('requestedAirspeed')
        if filed_speed:
            try:
                cruise_speed = int(float(filed_speed))
            except (ValueError, TypeError):
                cruise_speed = self.api_client._calculate_cruise_speed(aircraft_type)
        else:
            cruise_speed = self.api_client._calculate_cruise_speed(aircraft_type)

        # Create aircraft at parking spot
        aircraft = Aircraft(
            callsign=callsign,
            aircraft_type=aircraft_type,
            latitude=parking_spot.latitude,
            longitude=parking_spot.longitude,
            altitude=0,  # Ground level
            heading=int(parking_spot.heading),
            ground_speed=0,  # Stationary at gate
            starting_conditions_type='Parking',
            parking_spot_name=parking_spot.name,
            departure=departure,
            arrival=arrival,
            route=clean_route,  # Cleaned route (dots to spaces, airports/time removed)
            cruise_altitude=cruise_altitude,
            cruise_speed=cruise_speed,
            sid=dep_proc,  # Store SID in the sid field
            flight_rules="I",
            # Ground departures spawn at parking at their own airport, which
            # may not be the scenario's primary airport. Setting
            # primary_airport makes vNAS treat this aircraft as originating
            # from that airport (required when parking waypoints aren't
            # resolvable under the scenario's primary airport).
            primary_airport=departure_3letter,
            spawn_delay=None
        )

        return aircraft

    def _find_spawn_waypoint_on_route(self, route: str, is_arrival: bool = False,
                                      star_name: str = '') -> Optional[Dict]:
        """
        Find a waypoint on the route that is within ARTCC boundaries

        Args:
            route: Route string
            is_arrival: True if this is an arrival (spawn before STAR)
            star_name: STAR name for arrivals

        Returns:
            Dict with 'waypoint', 'heading', or None if no suitable waypoint found
        """
        # Parse route into waypoints
        waypoints = self.route_parser.parse_route_string(route)

        if not waypoints:
            return None

        # Get coordinates for waypoints
        route_coords = self.route_parser.get_route_waypoint_coordinates(waypoints)

        if len(route_coords) < 2:
            return None

        # Find waypoints within ARTCC
        waypoints_in_artcc = []
        for i, (wp_name, lat, lon) in enumerate(route_coords):
            if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
                waypoints_in_artcc.append((i, wp_name, lat, lon))

        if not waypoints_in_artcc:
            logger.debug(f"No waypoints found within ARTCC {self.artcc_id}")
            return None

        # For arrivals, find STAR waypoints and spawn before them
        if is_arrival and star_name:
            # Strip numeric suffix from STAR name
            star_base = re.sub(r'\d+$', '', star_name.upper())

            # Try to find STAR waypoint in route (look for exact match or match with numbers)
            star_index = None
            for i, wp_name in enumerate(waypoints):
                wp_upper = wp_name.upper()
                # Match either exact STAR base name or with numbers (DINGO or DINGO6)
                if wp_upper == star_base or wp_upper == star_name.upper():
                    star_index = i
                    break

            # Filter to waypoints before STAR
            if star_index is not None:
                logger.debug(f"Found STAR {star_name} at waypoint index {star_index} ({waypoints[star_index]})")
                waypoints_in_artcc = [
                    (idx, name, lat, lon) for idx, name, lat, lon in waypoints_in_artcc
                    if idx < star_index
                ]
                logger.debug(f"Filtered to {len(waypoints_in_artcc)} waypoints before STAR")
            else:
                # STAR not found in route - this is unusual but can happen
                logger.warning(f"STAR {star_name} not found in route, using all ARTCC waypoints")

        if not waypoints_in_artcc:
            logger.warning(f"No suitable waypoints found before STAR, cannot spawn arrival")
            return None

        # For arrivals, select the FIRST waypoint in ARTCC (maximize time in airspace)
        # For enroute, prefer a randomly-chosen *unused* waypoint so that two
        # transient aircraft on the same airway don't both claim the same fix
        # (which caused the earlier "Spawn point X already in use, skipping"
        # warnings and reduced the generated-count).
        if is_arrival:
            selected_idx, wp_name, lat, lon = waypoints_in_artcc[0]
            logger.debug(f"Selected first waypoint within ARTCC: {wp_name} at index {selected_idx}")
        else:
            from utils.geo_utils import route_remaining_inside_artcc
            shuffled = list(waypoints_in_artcc)
            random.shuffle(shuffled)
            used = getattr(self, 'used_spawn_points', set())
            unused = [w for w in shuffled if w[1] not in used]
            candidates = unused if unused else shuffled
            # Filter to candidates that have enough remaining route inside the
            # ARTCC — a transient aircraft that crosses our boundary within
            # a few miles of spawn is useless as a training target.
            min_remaining = getattr(self, 'enroute_min_remaining_nm',
                                     self.MIN_REMAINING_IN_ARTCC_NM)
            latlon_coords = [(lat_, lon_) for _, lat_, lon_ in route_coords]
            deep_candidates = []
            for cand in candidates:
                idx_ = cand[0]
                remaining_nm = route_remaining_inside_artcc(
                    latlon_coords, idx_, self.artcc_id,
                    self.artcc_boundaries,
                )
                if remaining_nm >= min_remaining:
                    deep_candidates.append(cand)
            if not deep_candidates:
                logger.debug(
                    f"No transient spawn candidates with >={min_remaining} NM "
                    f"remaining inside ARTCC {self.artcc_id}; skipping this flight"
                )
                return None
            # Pick the first candidate whose next-waypoint bearing points
            # roughly toward the end of the filed route. This catches
            # waypoint-db mismatches that would otherwise spawn the aircraft
            # pointing backwards along its filed route.
            from utils.geo_utils import calculate_bearing as _cb
            last_lat, last_lon = route_coords[-1][1], route_coords[-1][2]
            selected = None
            for cand in deep_candidates:
                idx_, name_, lat_, lon_ = cand
                if idx_ + 1 >= len(route_coords):
                    continue
                nx_lat, nx_lon = route_coords[idx_ + 1][1], route_coords[idx_ + 1][2]
                nx_bearing = _cb(lat_, lon_, nx_lat, nx_lon)
                dest_bearing = _cb(lat_, lon_, last_lat, last_lon)
                if abs((nx_bearing - dest_bearing + 540) % 360 - 180) <= 90:
                    selected = cand
                    break
            if selected is None:
                selected = deep_candidates[0]
            selected_idx, wp_name, lat, lon = selected

        # Calculate heading to next waypoint
        heading = 0
        if selected_idx + 1 < len(route_coords):
            next_wp_name, next_lat, next_lon = route_coords[selected_idx + 1]
            heading = int(self.route_parser.calculate_bearing(lat, lon, next_lat, next_lon))

        # Build initial route string (waypoints after the spawn point)
        remaining_waypoints = waypoints[selected_idx + 1:] if selected_idx + 1 < len(waypoints) else []
        initial_route = ' '.join(remaining_waypoints) if remaining_waypoints else ''

        # Polyline context so callers can shift this spawn back along the
        # filed route when the waypoint collides with another aircraft.
        from utils.geo_utils import calculate_distance_nm as _cd
        polyline_coords = [(lat_, lon_) for _, lat_, lon_ in route_coords]
        polyline_names = [wp_ for wp_, _, _ in route_coords]
        forward_nm = 0.0
        for i in range(selected_idx):
            forward_nm += _cd(
                route_coords[i][1], route_coords[i][2],
                route_coords[i + 1][1], route_coords[i + 1][2],
            )

        return {
            'waypoint': wp_name,
            'heading': heading,
            'latitude': lat,
            'longitude': lon,
            'waypoint_index': selected_idx,
            'all_waypoints': waypoints,
            'initial_route': initial_route,
            '_polyline_coords': polyline_coords,
            '_polyline_names': polyline_names,
            '_polyline_forward_nm': forward_nm,
            '_anchor_lat': None,
            '_anchor_lon': None,
        }

    def _add_equipment_suffix(self, aircraft_type: str, is_ga: bool) -> str:
        """Add equipment suffix to aircraft type"""
        if '/' in aircraft_type:
            return aircraft_type

        suffix = '/G' if is_ga else '/L'
        return f"{aircraft_type}{suffix}"

    def _estimate_cruise_altitude(self, dep_airport: str, arr_airport: str, aircraft_type: str) -> int:
        """
        Estimate a reasonable cruise altitude based on aircraft type when API doesn't provide it

        Args:
            dep_airport: Departure airport ICAO
            arr_airport: Arrival airport ICAO
            aircraft_type: Aircraft type code (e.g., B738, A320)

        Returns:
            Estimated cruise altitude in feet
        """
        if not aircraft_type:
            return 35000  # Default to typical jet altitude

        # Remove equipment suffix if present
        ac_type = aircraft_type.split('/')[0].upper()

        # Jets - typically cruise FL340-FL410
        jet_types = [
            'B7', 'A3', 'B737', 'B738', 'B739', 'B737', 'A320', 'A321', 'A319',
            'B752', 'B753', 'B763', 'B764', 'B772', 'B773', 'B77W', 'B788', 'B789',
            'CRJ', 'E170', 'E175', 'E190', 'E195', 'A21N', 'B38M', 'B39M',
            'MD8', 'MD9', 'DC9', 'E545', 'E135', 'E145', 'CL30', 'CL60', 'GLF'
        ]

        # Turboprops - typically cruise FL240-FL280
        turboprop_types = [
            'DH8', 'AT7', 'AT4', 'SF34', 'BE20', 'BE35', 'PC12', 'TBM'
        ]

        # Light aircraft - typically cruise 8000-12000 ft
        ga_types = ['C1', 'C2', 'P28', 'BE', 'PA', 'SR2', 'COL']

        # Check if it's a jet
        if any(ac_type.startswith(j) for j in jet_types):
            # Jets typically cruise FL340-FL410, with FL350-FL380 most common
            return random.choice([34000, 35000, 36000, 37000, 38000, 39000, 40000])

        # Check if it's a turboprop
        if any(ac_type.startswith(tp) for tp in turboprop_types):
            # Turboprops typically cruise FL240-FL280
            return random.choice([24000, 25000, 26000, 27000, 28000])

        # Check if it's a GA aircraft
        if any(ac_type.startswith(ga) for ga in ga_types):
            return random.choice([8000, 9000, 10000, 11000, 12000])

        # Default to typical commercial jet altitude
        logger.debug(f"Unknown aircraft type {aircraft_type}, defaulting to FL350")
        return 35000

    def _rule_of_3s_altitude(self, distance_to_dest_nm: float,
                              aircraft_type: str, field_elevation_ft: int = 1000) -> int:
        """Standard 3-to-1 descent profile: 3 NM per 1,000 ft of descent.

        Returns a sensible pre-descent altitude for an arrival spawned
        ``distance_to_dest_nm`` away from the field. Clamps to the type's
        typical cruise so a 600 NM spawn doesn't end up at FL180 (you'd still
        be at cruise that far out).
        """
        nm = max(0.0, float(distance_to_dest_nm))
        # descent_ft ≈ NM * 1000 / 3. Round to the nearest 1,000 so the strip
        # shows a whole flight level. Add a small field-elevation cushion so
        # the aircraft doesn't spawn below the destination's pattern altitude.
        raw_ft = int(round((nm * 1000.0 / 3.0) / 1000.0)) * 1000 + field_elevation_ft
        cruise_cap = self._estimate_cruise_altitude('', '', aircraft_type)
        return max(3000, min(raw_ft, cruise_cap))

    def _get_altitude_from_cifp(self, waypoint, star_name: str, departure: str, arrival: str, aircraft_type: str) -> int:
        """
        Get altitude from CIFP waypoint data with fallback to API/estimation

        Args:
            waypoint: Waypoint object from CIFP (may be None)
            star_name: STAR name
            departure: Departure airport ICAO
            arrival: Arrival airport ICAO
            aircraft_type: Aircraft type code

        Returns:
            Altitude in feet MSL
        """
        # Priority 1: CIFP max_altitude (top of altitude window)
        if waypoint and waypoint.max_altitude:
            logger.debug(f"Using CIFP max_altitude: {waypoint.max_altitude} ft for STAR {star_name}")
            return waypoint.max_altitude

        # Priority 2: CIFP min_altitude
        if waypoint and waypoint.min_altitude:
            logger.debug(f"Using CIFP min_altitude: {waypoint.min_altitude} ft for STAR {star_name}")
            return waypoint.min_altitude

        # Priority 3: Estimate based on aircraft type (CIFP data not available)
        altitude = self._estimate_cruise_altitude(departure, arrival, aircraft_type)
        logger.debug(f"No CIFP altitude constraints, estimating {altitude} ft for {aircraft_type}")
        return altitude

    # Minimum lateral separation (NM) required between two in-flight
    # aircraft at the same cruise altitude. If a pair would spawn inside
    # this bubble, the lower-priority aircraft's altitude is stepped down
    # by ``ALT_SEPARATION_STEP_FT``.
    ENROUTE_LATERAL_SEPARATION_NM: float = 10.0
    ALT_SEPARATION_STEP_FT: int = 2000

    # Default shift-back distance (NM) when two aircraft would overlap on
    # the same route waypoint. The colliding aircraft becomes an FRD spawn
    # this far upstream along its filed route.
    WAYPOINT_COLLISION_BACKUP_NM: float = 20.0

    # How far outside the ARTCC boundary an arrival may still spawn while
    # satisfying the band requirement. Needed for cases like SKW5669/PHX
    # where the in-band named waypoints on the filed route (e.g., BOILE)
    # sit ~200 NM outside ZAB but BLH is only ~40 NM outside — BLH is a
    # reasonable spawn anchor; BOILE isn't.
    ARRIVAL_BAND_BOUNDARY_TOLERANCE_NM: float = 50.0

    def _shift_spawn_back_on_polyline(
        self,
        polyline_coords: List[Tuple[float, float]],
        polyline_names: List[str],
        current_forward_nm: float,
        anchor_lat: Optional[float],
        anchor_lon: Optional[float],
        matching_star: Optional[str] = None,
        backup_nm: float = None,
    ) -> Optional[Dict]:
        """Step backward along a filed-route polyline by ``backup_nm`` and
        return a spawn dict suitable for FRD rendering. Used when a primary
        spawn collides with another aircraft's waypoint.

        Returns None when we can't step that far back (polyline too short
        before the spawn position)."""
        from utils.geo_utils import (
            calculate_bearing, calculate_distance_nm, interpolate_along_path,
        )
        if backup_nm is None:
            backup_nm = self.WAYPOINT_COLLISION_BACKUP_NM
        new_forward = current_forward_nm - backup_nm
        if new_forward <= 0 or len(polyline_coords) < 2:
            return None
        interp = interpolate_along_path(polyline_coords, new_forward)
        if not interp:
            return None
        lat, lon, heading = interp

        # Pin the FRD to the nearest upstream named waypoint. vNAS uses the
        # ``fix`` field as the raw starting-position reference — a bare
        # waypoint name spawns the aircraft AT that waypoint, ignoring the
        # lat/lon we computed. Encode the proper FixRadialDistance string
        # (``<NAME><RRR><DDD>``) so vNAS actually places the aircraft at the
        # shifted-back position.
        cum = 0.0
        upstream_name = polyline_names[0] if polyline_names else ''
        upstream_lat = polyline_coords[0][0] if polyline_coords else None
        upstream_lon = polyline_coords[0][1] if polyline_coords else None
        for i in range(len(polyline_coords) - 1):
            leg = calculate_distance_nm(
                polyline_coords[i][0], polyline_coords[i][1],
                polyline_coords[i + 1][0], polyline_coords[i + 1][1],
            )
            if cum + leg >= new_forward:
                if i < len(polyline_names):
                    upstream_name = polyline_names[i]
                upstream_lat = polyline_coords[i][0]
                upstream_lon = polyline_coords[i][1]
                break
            cum += leg

        if upstream_name and upstream_lat is not None and upstream_lon is not None:
            brg = int(round(calculate_bearing(
                upstream_lat, upstream_lon, lat, lon,
            ))) % 360
            dist = max(1, int(round(calculate_distance_nm(
                upstream_lat, upstream_lon, lat, lon,
            ))))
            fix_str = f"{upstream_name}{brg:03d}{dist:03d}"
        else:
            fix_str = upstream_name

        distance_to_dest = (
            calculate_distance_nm(lat, lon, anchor_lat, anchor_lon)
            if anchor_lat is not None and anchor_lon is not None else None
        )
        return {
            'fix': fix_str,
            'latitude': lat,
            'longitude': lon,
            'heading': int(heading),
            'starting_conditions_type': 'FixOrFrd',
            'on_star': False,
            'actual_star_name': matching_star,
            'star_waypoint_obj': None,
            'node_index': None,
            'distance_to_dest_nm': distance_to_dest,
            '_polyline_coords': polyline_coords,
            '_polyline_names': polyline_names,
            '_polyline_forward_nm': new_forward,
            '_anchor_lat': anchor_lat,
            '_anchor_lon': anchor_lon,
            '_shifted_back': True,
        }

    def _reserve_spawn_or_shift_back(
        self,
        spawn: Dict,
        prefix: str,
        callsign: str,
        max_shifts: int = 4,
    ) -> Optional[Dict]:
        """Atomically register ``spawn`` in ``self.used_spawn_points``.
        If its waypoint is already taken, shift the aircraft 20 NM back
        along its filed-route polyline (creating an FRD spawn) and retry.

        Returns the registered spawn dict (possibly the shifted one), or
        None if we exhausted shifts without finding a free slot."""
        current = spawn
        for attempt in range(max_shifts + 1):
            key = f"{prefix}:{current['fix'].upper()}"
            coord_key = f"{prefix}:{round(current['latitude'], 2)},{round(current['longitude'], 2)}"
            with self.spawn_point_lock:
                if key not in self.used_spawn_points and coord_key not in self.used_spawn_points:
                    self.used_spawn_points.add(key)
                    self.used_spawn_points.add(coord_key)
                    return current
            # Collision — try shifting back along the polyline.
            poly = current.get('_polyline_coords')
            names = current.get('_polyline_names')
            fwd = current.get('_polyline_forward_nm')
            anchor_lat = current.get('_anchor_lat')
            anchor_lon = current.get('_anchor_lon')
            star = current.get('actual_star_name')
            if not (poly and names and fwd is not None):
                logger.debug(
                    f"{callsign}: collision at {current['fix']} but no polyline "
                    f"context to shift back; skipping"
                )
                return None
            shifted = self._shift_spawn_back_on_polyline(
                poly, names, fwd, anchor_lat, anchor_lon, star,
            )
            if shifted is None:
                logger.debug(
                    f"{callsign}: collision at {current['fix']}, can't step "
                    f"another {self.WAYPOINT_COLLISION_BACKUP_NM} NM back "
                    f"(attempt {attempt + 1}/{max_shifts}); skipping"
                )
                return None
            logger.debug(
                f"{callsign}: {current['fix']} taken, shifting "
                f"{self.WAYPOINT_COLLISION_BACKUP_NM} NM back to FRD off "
                f"{shifted['fix']}"
            )
            current = shifted
        logger.debug(f"{callsign}: exhausted collision shift-backs")
        return None

    def _install_custom_boundary(self, waypoint_names: List[str]) -> None:
        """Replace ``self.artcc_boundaries`` with a :class:`CustomBoundary`
        built from the user-specified waypoint list. Requires at least four
        resolvable waypoints — anything less can't form a useful polygon.

        Tokens that don't resolve are logged and dropped. If fewer than four
        valid waypoints remain, the ARTCC polygon is left in place so the
        scenario still generates (with a warning) instead of silently
        spawning aircraft against an empty boundary.
        """
        from utils.artcc_utils import CustomBoundary

        resolved: List[Tuple[float, float]] = []  # (lon, lat)
        dropped: List[str] = []
        wdb = self.route_parser.waypoint_db
        for name in waypoint_names:
            token = (name or '').strip().upper()
            if not token:
                continue
            coord = wdb.get_coordinates(token)
            if not coord:
                dropped.append(token)
                continue
            lat, lon = coord
            resolved.append((lon, lat))

        if dropped:
            logger.warning(
                f"Custom boundary: dropped unresolvable waypoints {dropped}"
            )

        if len(resolved) < 4:
            logger.error(
                f"Custom boundary needs at least 4 resolvable waypoints; "
                f"got {len(resolved)}. Falling back to ARTCC polygon."
            )
            return

        self.artcc_boundaries = CustomBoundary(resolved)
        logger.info(
            f"Custom boundary active — polygon from {len(resolved)} waypoints: "
            f"{[n.strip().upper() for n in waypoint_names if n]}"
        )

    def _validate_arrival_runway_procedures(self) -> None:
        """For each arrival airport with BOTH active runways AND a STAR
        prefix filter configured, verify at least one published runway
        transition on a matching STAR lines up with an active runway.
        When no overlap exists we don't block generation — ``_get_runway_for_star``
        already falls back to the STAR's first published runway — but we
        record an advisory so the user sees it on the conclusion screen.
        """
        proc_map = getattr(self, 'arrival_airport_procedures', {}) or {}
        if not proc_map:
            return

        for airport, prefixes in proc_map.items():
            active = [r.upper() for r in
                      (self.arrival_airport_runways.get(airport) or [])]
            if not active:
                # Empty runway list = any runway allowed; skip the check.
                continue
            parser = self.cifp_parsers.get(airport)
            if not parser:
                self.generation_warnings.append(
                    f"{airport}: no CIFP data loaded — cannot verify runway "
                    f"vs STAR compatibility for {prefixes}."
                )
                continue

            star_names_by_prefix = {}
            all_stars = list(getattr(parser, 'star_waypoints', {}).keys())
            for prefix in prefixes:
                matches = [s for s in all_stars
                           if re.sub(r'\d+$', '', s.upper()) == prefix.upper()]
                star_names_by_prefix[prefix] = matches
                if not matches:
                    self.generation_warnings.append(
                        f"{airport}: STAR prefix '{prefix}' matched no "
                        f"published STAR in CIFP."
                    )

            # For each (airport, prefix) check whether ANY matching STAR has
            # a runway transition that overlaps ANY of the active runways.
            for prefix, stars in star_names_by_prefix.items():
                if not stars:
                    continue
                published = set()
                for star_name in stars:
                    for rwy in parser.get_runways_for_arrival(star_name) or []:
                        published.add(str(rwy).upper().replace('RW', ''))
                if not published:
                    # STAR publishes no runway-specific transitions (common/ALL
                    # segment only) — any active runway is a valid fallback.
                    continue
                active_clean = {r.replace('RW', '') for r in active}
                if not (published & active_clean):
                    self.generation_warnings.append(
                        f"{airport}: STAR '{prefix}' publishes runways "
                        f"{sorted(published)} but active runways are "
                        f"{sorted(active_clean)} — no overlap. Arrivals "
                        f"will use the STAR's first published runway."
                    )

    def _resolve_spawn_proximity(self, spawn_delay_mode) -> None:
        """Enforce distance-based spawn spacing on arrivals sharing a filed
        route. Called after ``apply_spawn_delays`` so every aircraft's
        ``spawn_delay`` (seconds) reflects its final staggering.

        Required effective separation between any two arrivals on the same
        route is:

          * ``REQUIRED_NO_DELAY_NM`` (20) when no spawn delay is configured
            — effective separation is purely physical.
          * ``REQUIRED_WITH_DELAY_NM`` (10) otherwise — the time offset
            between spawns closes the gap at the pair's average groundspeed.

        When two aircraft are too close the later-spawning one is shifted
        back along its polyline (reusing ``_shift_spawn_back_on_polyline``).
        If shifting pushes it past the airport's arrival-band max, that's
        allowed — we just surface a note.
        """
        from models.spawn_delay_mode import SpawnDelayMode
        from utils.geo_utils import calculate_distance_nm

        REQUIRED_NO_DELAY_NM = 20.0
        REQUIRED_WITH_DELAY_NM = 10.0
        STEP_NM = 5.0
        MAX_STEPS = 20

        no_delay = (spawn_delay_mode == SpawnDelayMode.NONE)
        required = REQUIRED_NO_DELAY_NM if no_delay else REQUIRED_WITH_DELAY_NM

        # Group by (arrival airport, filed route signature). Same-airport
        # aircraft filed on different routes through the ARTCC rarely share
        # spawn points, so the simple keying is fine.
        groups: Dict[Tuple[str, str], List] = {}
        for ac in self.aircraft:
            ctx = getattr(ac, '_spawn_ctx', None)
            if not ctx or not ctx.get('polyline_coords'):
                continue
            key = (ctx.get('arrival_airport', ''),
                   (ac.route or '').strip().upper())
            groups.setdefault(key, []).append(ac)

        for key, aircraft_list in groups.items():
            if len(aircraft_list) < 2:
                continue
            # Sort by spawn time (seconds). `spawn_delay` may be None when
            # no-delay mode is active; treat as 0.
            aircraft_list.sort(key=lambda a: (a.spawn_delay or 0))

            placed = []  # aircraft we've already resolved against
            for ac in aircraft_list:
                shifted = 0
                while shifted < MAX_STEPS:
                    violation = None
                    for other in placed:
                        d_nm = calculate_distance_nm(
                            ac.latitude, ac.longitude,
                            other.latitude, other.longitude,
                        )
                        if no_delay:
                            effective = d_nm
                        else:
                            dt_s = abs((ac.spawn_delay or 0) - (other.spawn_delay or 0))
                            avg_gs = 0.5 * (ac.ground_speed + other.ground_speed)
                            effective = d_nm + (dt_s * avg_gs / 3600.0)
                        if effective < required:
                            violation = (other, d_nm, effective)
                            break
                    if violation is None:
                        placed.append(ac)
                        break

                    # Try to shift this aircraft back along its polyline.
                    ctx = ac._spawn_ctx
                    new_fwd = (ctx.get('forward_nm') or 0) - STEP_NM
                    if new_fwd <= 0:
                        self.generation_notes.append(
                            f"{ac.callsign}: could not maintain {required:.0f} NM "
                            f"separation on route into {ctx.get('arrival_airport')} "
                            f"— polyline exhausted; leaving spawn in place."
                        )
                        placed.append(ac)
                        break
                    new_spawn = self._shift_spawn_back_on_polyline(
                        ctx['polyline_coords'], ctx['polyline_names'],
                        ctx['forward_nm'],
                        ctx.get('anchor_lat'), ctx.get('anchor_lon'),
                        ctx.get('actual_star_name'),
                        backup_nm=STEP_NM,
                    )
                    if new_spawn is None:
                        self.generation_notes.append(
                            f"{ac.callsign}: could not maintain {required:.0f} NM "
                            f"separation on route into {ctx.get('arrival_airport')} "
                            f"— leaving spawn in place."
                        )
                        placed.append(ac)
                        break

                    # Commit the shift onto the aircraft and its context.
                    ac.latitude = new_spawn['latitude']
                    ac.longitude = new_spawn['longitude']
                    ac.fix = new_spawn['fix']
                    ac.starting_conditions_type = new_spawn['starting_conditions_type']
                    ctx['forward_nm'] = new_spawn['_polyline_forward_nm']
                    shifted += 1

                    # If we've passed the arrival band max, note it once.
                    dist_to_dest = new_spawn.get('distance_to_dest_nm')
                    max_nm = ctx.get('max_nm')
                    if (dist_to_dest is not None and max_nm is not None
                            and dist_to_dest > max_nm
                            and not ctx.get('_band_note_logged')):
                        self.generation_notes.append(
                            f"{ac.callsign}: spawn extended to "
                            f"{dist_to_dest:.0f} NM from "
                            f"{ctx.get('arrival_airport')} (beyond "
                            f"{max_nm:.0f} NM band) to maintain "
                            f"{required:.0f} NM separation."
                        )
                        ctx['_band_note_logged'] = True
                else:
                    # max shifts exhausted
                    self.generation_notes.append(
                        f"{ac.callsign}: exhausted spawn shift attempts; "
                        f"remaining separation may be below {required:.0f} NM."
                    )
                    placed.append(ac)

    def _resolve_enroute_altitude_conflicts(self) -> None:
        """Separate any two airborne aircraft spawning within
        ``ENROUTE_LATERAL_SEPARATION_NM`` of each other at the same altitude
        by stepping one of them down by ``ALT_SEPARATION_STEP_FT``.

        Targets enroute transients and overflights — aircraft at their
        cruise altitude, where a lateral 10 NM overlap at the same flight
        level is an immediate TCAS event. Arrivals (descending on the STAR)
        and departures (still on the ground) are exempt.
        """
        from utils.geo_utils import calculate_distance_nm

        candidates = [
            a for a in self.aircraft
            if a.altitude and a.altitude > 0
            and a.starting_conditions_type in ('Fix', 'FixOrFrd')
            and not a.arrival_runway
            and not a.star
            and not a.parking_spot_name
        ]
        if len(candidates) < 2:
            return

        MIN_FLOOR_FT = 10000

        def _apply_alt(ac, new_alt: int) -> None:
            ac.altitude = new_alt
            if ac.cruise_altitude is not None:
                ac.cruise_altitude = str(new_alt)

        for pass_n in range(1, 21):
            moved = 0
            # Sort by altitude descending so we adjust higher aircraft first
            # (keeps separation symmetric and avoids oscillation).
            candidates.sort(key=lambda a: -a.altitude)
            for i in range(len(candidates)):
                for j in range(i + 1, len(candidates)):
                    a, b = candidates[i], candidates[j]
                    if a.altitude != b.altitude:
                        continue
                    d = calculate_distance_nm(
                        a.latitude, a.longitude, b.latitude, b.longitude,
                    )
                    if d >= self.ENROUTE_LATERAL_SEPARATION_NM:
                        continue
                    new_alt = b.altitude - self.ALT_SEPARATION_STEP_FT
                    if new_alt < MIN_FLOOR_FT:
                        logger.debug(
                            f"{b.callsign}: conflict with {a.callsign} at "
                            f"{a.altitude} ft ({d:.1f} NM) — can't step below "
                            f"{MIN_FLOOR_FT} ft, leaving altitude alone"
                        )
                        continue
                    logger.debug(
                        f"{b.callsign}: {d:.1f} NM from {a.callsign} at "
                        f"{a.altitude} ft → stepping down to {new_alt} ft"
                    )
                    _apply_alt(b, new_alt)
                    moved += 1
            if moved == 0:
                break
        if pass_n >= 20:
            logger.warning(
                "Enroute altitude conflict resolver hit max passes (20) — "
                "some aircraft may still overlap"
            )

    def _nm_to_artcc_boundary(self, lat: float, lon: float) -> float:
        """Great-circle distance (NM) from ``(lat, lon)`` to the nearest
        vertex of this ARTCC's polygon. Returns 0 if the point is inside,
        ``inf`` if the polygon is missing.

        Used as the "near-boundary" test for arrival-band checks. Vertex
        distance is a conservative (upper-bound) approximation of true
        point-to-edge distance — good enough at the ~50 NM tolerance we
        apply here."""
        if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
            return 0.0
        poly = self.artcc_boundaries.get_artcc_polygon(self.artcc_id) or []
        if not poly:
            return float('inf')
        from utils.geo_utils import calculate_distance_nm
        best = float('inf')
        for plon, plat in poly:
            d = calculate_distance_nm(lat, lon, plat, plon)
            if d < best:
                best = d
        return best

    def _point_in_band_and_reachable(self, lat: float, lon: float,
                                       dist_to_dest: float,
                                       min_nm: float, max_nm: float) -> bool:
        """True if the point sits inside the [min_nm, max_nm] distance band
        AND either lies inside the ARTCC or within the configured boundary
        tolerance of it."""
        if not (min_nm <= dist_to_dest <= max_nm):
            return False
        if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
            return True
        return (
            self._nm_to_artcc_boundary(lat, lon)
            <= self.ARRIVAL_BAND_BOUNDARY_TOLERANCE_NM
        )

    def _find_boundary_entry_spawn(self, nodes: List[Tuple],
                                     anchor_lat: float, anchor_lon: float,
                                     matching_star: Optional[str]) -> Optional[Dict]:
        """Safety fallback for arrivals whose requested band falls entirely
        outside our ARTCC: spawn the aircraft just outside the boundary on
        the reverse bearing from where the filed route first enters our
        airspace, pointed inbound at that entry waypoint — same handoff
        geometry as an overflight.

        Keeps the arrival on its filed route and procedure rather than
        dropping it; the controller sees it check in from the adjacent
        facility instead of teleporting to a named fix inside the sector.
        """
        from utils.geo_utils import (
            calculate_bearing, calculate_destination, calculate_distance_nm,
        )

        # Find the first node inside the ARTCC — that's the route's entry.
        entry_idx = None
        for i, (_, lat, lon, _, _) in enumerate(nodes):
            if self.artcc_boundaries.is_point_in_artcc(lat, lon, self.artcc_id):
                entry_idx = i
                break
        if entry_idx is None:
            # Route never enters our airspace — nothing we can do.
            return None

        entry_name, entry_lat, entry_lon, entry_is_star, entry_wp_obj = nodes[entry_idx]

        # Establish the inbound bearing the same way overflights do.
        if entry_idx > 0:
            _, up_lat, up_lon, _, _ = nodes[entry_idx - 1]
            inbound_heading = calculate_bearing(up_lat, up_lon, entry_lat, entry_lon)
        elif entry_idx + 1 < len(nodes):
            _, nx_lat, nx_lon, _, _ = nodes[entry_idx + 1]
            inbound_heading = calculate_bearing(entry_lat, entry_lon, nx_lat, nx_lon)
        else:
            return None

        # Offset outside the boundary. Reuse the overflight band so the UI
        # knob controls both handoff geometries; clamp the min to a small
        # positive value so we always end up outside the polygon.
        min_nm, max_nm = getattr(self, 'overflight_spawn_band',
                                  self.DEFAULT_OVERFLIGHT_BAND_NM)
        offset_nm = random.uniform(min_nm, max_nm) if max_nm > min_nm else min_nm
        reverse_bearing = (inbound_heading + 180) % 360
        spawn_lat, spawn_lon = calculate_destination(
            entry_lat, entry_lon, reverse_bearing, offset_nm,
        )
        # Verify we actually ended up outside — for odd-shaped ARTCCs the
        # reverse-bearing offset can still land inside a lobe of the polygon.
        tries = 0
        while (self.artcc_boundaries.is_point_in_artcc(spawn_lat, spawn_lon, self.artcc_id)
                and tries < 4):
            offset_nm += 10
            spawn_lat, spawn_lon = calculate_destination(
                entry_lat, entry_lon, reverse_bearing, offset_nm,
            )
            tries += 1

        distance_to_dest = calculate_distance_nm(
            spawn_lat, spawn_lon, anchor_lat, anchor_lon,
        )

        # vNAS ignores the aircraft's lat/lon for ``FixOrFrd`` starts and
        # uses the ``fix`` string as the position reference. A bare waypoint
        # name would spawn the aircraft AT the entry waypoint (inside the
        # ARTCC), defeating the whole point of a boundary-entry handoff.
        # Build the FRD form ``<FIX><RRR><DDD>`` — radial on the reverse
        # bearing from the entry fix, distance = offset_nm — so vNAS places
        # the aircraft at the computed outside-ARTCC position.
        frd_fix = f"{entry_name}{int(reverse_bearing) % 360:03d}{max(1, int(round(offset_nm))):03d}"

        return {
            'fix': frd_fix,
            'latitude': spawn_lat,
            'longitude': spawn_lon,
            'heading': int(inbound_heading),
            'starting_conditions_type': 'FixOrFrd',
            # Boundary-entry spawns are always pre-STAR from our sector's
            # point of view even if the entry waypoint happens to be on the
            # STAR, so Mach dispatch still applies until the aircraft reaches
            # STAR territory.
            'on_star': False,
            'actual_star_name': matching_star,
            'star_waypoint_obj': None,
            'node_index': entry_idx,
            'distance_to_dest_nm': distance_to_dest,
            'boundary_entry': True,
            # The name of the entry waypoint (before FRD encoding) so the
            # nav-path builder can put it as the first fly-to fix — the
            # aircraft is approaching that waypoint from outside the ARTCC.
            'boundary_entry_name': entry_name,
        }

    def _find_arrival_spawn_on_route(self, filed_route: str, arrival_icao: str,
                                      star_name: str,
                                      min_nm: float, max_nm: float) -> Optional[Dict]:
        """Pick an arrival spawn point whose straight-line distance from the
        arrival airport falls in [min_nm, max_nm].

        Strategy:
        1. Build a forward polyline: cleaned filed-route waypoints + CIFP STAR
           waypoints (de-duplicated at the seam).
        2. Tag each node with distance-to-destination using the airport's
           reported center and the existing haversine helper.
        3. Prefer a *named* in-ARTCC node whose dist-to-dest is in the band.
        4. If none match, interpolate a synthetic FRD-style point along the
           leg that crosses the band (prefer the midpoint of the band that
           still falls inside the ARTCC).
        5. If nothing in the band is inside the ARTCC, return None — caller
           will try a different flight.

        Returns a dict with keys the arrival creator already expects:
        ``{fix, latitude, longitude, heading, starting_conditions_type,
           actual_star_name, star_waypoint_obj, on_star}``. ``on_star`` flags
        whether the chosen spawn falls on a STAR waypoint (used by the speed
        logic to decide whether Mach is appropriate).
        """
        from utils.geo_utils import (
            calculate_bearing, calculate_distance_nm, cumulative_distances,
            interpolate_along_path,
        )

        cifp_parser = self.cifp_parsers.get(arrival_icao)
        if not cifp_parser:
            return None

        # 1a. Clean filed route → named waypoints with coords.
        clean = clean_route_string(filed_route)
        filed_names = self.route_parser.parse_route_string(clean)

        # 1b. Resolve the STAR name via the same base-match the old code used.
        available_stars = cifp_parser.get_available_stars()
        star_base = re.sub(r'\d+$', '', (star_name or '').upper())
        matching_star = None
        for s in available_stars:
            if re.sub(r'\d+$', '', s.upper()) == star_base:
                matching_star = s
                break
        star_nodes: List[Tuple[str, float, float, object]] = []
        # Waypoint-name → (lat, lon) map pulled from the STAR's CIFP records.
        # Used to override the global waypoint DB for filed-route tokens that
        # collide with unrelated waypoints (e.g., "GUP" as the EAGUL6 enroute
        # transition in western NM vs. an identically-named fix in Arkansas).
        star_wp_coords: Dict[str, Tuple[float, float]] = {}
        if matching_star:
            for wp_name in cifp_parser.get_arrival_waypoints(matching_star) or []:
                wp_obj = cifp_parser.get_transition_waypoint(wp_name, matching_star)
                if wp_obj and wp_obj.latitude and wp_obj.longitude:
                    star_nodes.append((wp_name, wp_obj.latitude, wp_obj.longitude, wp_obj))
                    star_wp_coords.setdefault(
                        wp_name.upper(), (wp_obj.latitude, wp_obj.longitude),
                    )
            star_wps = getattr(cifp_parser, 'star_waypoints', {}).get(matching_star, {})
            for name, wp in star_wps.items():
                if wp.latitude and wp.longitude:
                    star_wp_coords.setdefault(
                        name.upper(), (wp.latitude, wp.longitude),
                    )

        # 1a'. Resolve filed tokens with STAR-CIFP priority. For tokens the
        # STAR knows (e.g., "GUP" on EAGUL6), use the CIFP coords — the
        # global waypoint DB is subject to name collisions that distort the
        # polyline geometry (a 1000 NM dogleg through a same-named fix in
        # another ARTCC will wreck every downstream band/tolerance check).
        filed_coords: List[Tuple[str, float, float]] = []
        for tok in filed_names:
            tok_u = tok.upper()
            if tok_u in star_wp_coords:
                lat, lon = star_wp_coords[tok_u]
                filed_coords.append((tok, lat, lon))
                continue
            coord = self.route_parser.waypoint_db.get_coordinates(tok)
            if coord:
                filed_coords.append((tok, coord[0], coord[1]))

        # 1a''. Dogleg sanity check — any filed waypoint whose leg from the
        # previous node exceeds 500 NM AND bears away from the destination is
        # almost certainly a name collision (the correct waypoint would be
        # close to the route corridor). Drop it so it doesn't poison the
        # polyline scan.
        def _drop_dogleg(
            coords: List[Tuple[str, float, float]],
            dest_lat: Optional[float], dest_lon: Optional[float],
        ) -> List[Tuple[str, float, float]]:
            if not coords or dest_lat is None or dest_lon is None:
                return coords
            out = [coords[0]]
            for name, lat, lon in coords[1:]:
                plast_name, plast_lat, plast_lon = out[-1]
                leg = calculate_distance_nm(plast_lat, plast_lon, lat, lon)
                if leg > 500:
                    # Is the jump heading away from (or wildly off from) the
                    # destination? If so, reject.
                    brg = calculate_bearing(plast_lat, plast_lon, lat, lon)
                    dest_brg = calculate_bearing(plast_lat, plast_lon, dest_lat, dest_lon)
                    diff = abs((brg - dest_brg + 540) % 360 - 180)
                    if diff > 45:
                        logger.debug(
                            f"Dropping filed token {name}: {leg:.0f} NM leg "
                            f"from {plast_name} bears {diff:.0f}° off destination"
                        )
                        continue
                out.append((name, lat, lon))
            return out

        # Destination anchor for the dogleg check. Use the last STAR waypoint
        # when available (most reliable); else the last filed coord we have.
        _dest_lat = star_nodes[-1][1] if star_nodes else (
            filed_coords[-1][1] if filed_coords else None
        )
        _dest_lon = star_nodes[-1][2] if star_nodes else (
            filed_coords[-1][2] if filed_coords else None
        )
        filed_coords = _drop_dogleg(filed_coords, _dest_lat, _dest_lon)

        # 1c. Build the full forward polyline. Seam-dedupe: if the last filed
        # waypoint equals the first STAR waypoint, drop the duplicate.
        # Each node: (name, lat, lon, is_star, wp_obj_or_None).
        nodes: List[Tuple[str, float, float, bool, object]] = []
        for name, lat, lon in filed_coords:
            nodes.append((name, lat, lon, False, None))
        if star_nodes:
            start_idx = 0
            if nodes and nodes[-1][0].upper() == star_nodes[0][0].upper():
                # Replace the seam node with the STAR-tagged version so we
                # don't double-count it.
                nodes[-1] = (star_nodes[0][0], star_nodes[0][1], star_nodes[0][2], True, star_nodes[0][3])
                start_idx = 1
            for wp_name, lat, lon, wp_obj in star_nodes[start_idx:]:
                nodes.append((wp_name, lat, lon, True, wp_obj))

        if len(nodes) < 2:
            return None

        # 2. Distance to destination for each node. Use the last STAR waypoint
        # as the dest anchor if we have one; otherwise fall back to the last
        # route node. (Arrival airport ICAO → lat/lon lookup isn't always
        # reliable for the waypoint database.)
        anchor_lat, anchor_lon = nodes[-1][1], nodes[-1][2]
        dist_to_dest = [
            calculate_distance_nm(lat, lon, anchor_lat, anchor_lon)
            for _, lat, lon, _, _ in nodes
        ]

        # 3. Named-node path in band — inside ARTCC OR within the
        # boundary-tolerance. Named waypoints sitting just outside the ARTCC
        # boundary (e.g., BLH ~40 NM outside ZAB for PHX arrivals) are still
        # valid spawn anchors; filed plans that only cross into ZAB deep in
        # the band otherwise get pushed to the boundary-entry fallback and
        # lose their band compliance.
        in_band_named: List[Tuple[int, float]] = [
            (i, dist_to_dest[i])
            for i in range(len(nodes))
            if self._point_in_band_and_reachable(
                nodes[i][1], nodes[i][2], dist_to_dest[i], min_nm, max_nm,
            )
        ]

        def _downstream_heading(idx: int, fallback_obj=None) -> Optional[int]:
            """Bearing from node[idx] to the next distinct-position node that's
            closer to the destination anchor. Returns None when no valid
            downstream node exists — the caller must then reject this
            candidate rather than spawning with a guessed heading."""
            for j in range(idx + 1, len(nodes)):
                lat_a, lon_a = nodes[idx][1], nodes[idx][2]
                lat_b, lon_b = nodes[j][1], nodes[j][2]
                # Skip duplicate / zero-length legs.
                if abs(lat_a - lat_b) < 1e-6 and abs(lon_a - lon_b) < 1e-6:
                    continue
                # Downstream means the next node is closer to destination
                # than current. Rejecting same-or-farther nodes filters out
                # malformed or reversed route segments (the "opposite
                # direction on the arrival" bug reported by users).
                if dist_to_dest[j] >= dist_to_dest[idx] - 0.5:
                    continue
                return int(calculate_bearing(lat_a, lon_a, lat_b, lon_b))
            # Last-resort: use CIFP inbound course only if it points roughly
            # toward the destination anchor.
            if fallback_obj is not None and getattr(fallback_obj, 'inbound_course', None):
                hdg = int(fallback_obj.inbound_course) % 360
                anchor_bearing = int(calculate_bearing(
                    nodes[idx][1], nodes[idx][2], anchor_lat, anchor_lon
                ))
                diff = abs((hdg - anchor_bearing + 540) % 360 - 180)
                if diff <= 90:
                    return hdg
            return None

        polyline = [(lat, lon) for _, lat, lon, _, _ in nodes]
        polyline_names = [n[0] for n in nodes]
        polyline_cum = cumulative_distances(polyline)

        # Cumulative distance along the filed portion of the polyline (not
        # the full polyline — STAR waypoints are not "filed fixes" we want
        # echoed in the nav path). Indexed to filed_coords.
        filed_cum = [0.0]
        for i in range(1, len(filed_coords)):
            prev = filed_coords[i - 1]
            cur = filed_coords[i]
            filed_cum.append(
                filed_cum[-1]
                + calculate_distance_nm(prev[1], prev[2], cur[1], cur[2])
            )

        # Base name of the filed STAR token (e.g., "WAZKO1" → "WAZKO"). Used
        # by the nav-path builder to strip the trailing STAR-name artifact
        # from downstream filed fixes: vNAS reaches that waypoint via the
        # STAR procedure itself, so re-emitting it as a fly-to fix is both
        # redundant and occasionally wrong (e.g. WAZKO1 whose first common
        # segment waypoint happens to share the base name).
        filed_star_base = star_base if matching_star else ''

        def _downstream_filed(forward_nm: float) -> List[str]:
            """Filed-route tokens whose polyline-cum position is strictly
            past ``forward_nm``. Dedups consecutive duplicates and drops the
            trailing STAR-name artifact so the nav path becomes
            ``<remaining fixes> <STAR>[.<rwy>]`` — e.g.
            ``SMMUR2 DAAYE ABQ SLNNK WAZKO1`` → ``ABQ SLNNK`` when the spawn
            is past DAAYE."""
            out: List[str] = []
            for i, (name, _, _) in enumerate(filed_coords):
                if filed_cum[i] > forward_nm + 0.1:
                    if not out or out[-1].upper() != name.upper():
                        out.append(name)
            if filed_star_base and out and out[-1].upper() == filed_star_base.upper():
                out = out[:-1]
            return out

        def _with_polyline(d: Dict, forward_nm: float) -> Dict:
            """Attach polyline context so the creator can shift back on
            waypoint collision and so the nav-path builder can walk to the
            next downstream named fix."""
            d['_polyline_coords'] = polyline
            d['_polyline_names'] = polyline_names
            d['_polyline_forward_nm'] = forward_nm
            d['_anchor_lat'] = anchor_lat
            d['_anchor_lon'] = anchor_lon
            d['_downstream_filed_fixes'] = _downstream_filed(forward_nm)
            return d

        if in_band_named:
            # Prefer a named node closest to the band midpoint, tiebreak to
            # the deepest (farthest-from-airport) one so aircraft start with
            # more time in the sector when multiple waypoints cluster.
            midpoint = 0.5 * (min_nm + max_nm)
            in_band_named.sort(key=lambda t: (abs(t[1] - midpoint), -t[1]))
            for candidate_idx, dist_dest in in_band_named:
                name, lat, lon, is_star, wp_obj = nodes[candidate_idx]
                hdg = _downstream_heading(candidate_idx, wp_obj)
                if hdg is None:
                    continue
                return _with_polyline({
                    'fix': name,
                    'latitude': lat,
                    'longitude': lon,
                    'heading': hdg,
                    'starting_conditions_type': 'Fix',
                    'on_star': is_star,
                    'actual_star_name': matching_star,
                    'star_waypoint_obj': wp_obj if is_star else None,
                    'node_index': candidate_idx,
                    'distance_to_dest_nm': dist_dest,
                }, polyline_cum[candidate_idx])

        # 4. FRD synthesis. Scan the polyline in small steps for the position
        # that best satisfies BOTH the band AND the boundary tolerance. The
        # previous single-midpoint interpolation used to fall through to
        # ``_find_boundary_entry_spawn`` whenever the band midpoint was >50
        # NM outside the ARTCC — that's how arrivals like SWA9058 on
        # ``FRITR3 CNERY BLH HYDRR1`` ended up spawning at HYDRR (~50 NM
        # from PHX, far inside the boundary and well below the 200–300 NM
        # band). The scan finds any polyline position where the route is
        # simultaneously in-band and within ``ARRIVAL_BAND_BOUNDARY_TOLERANCE_NM``
        # of the boundary, picking the one closest to the band midpoint.
        total_len = polyline_cum[-1] if polyline_cum else 0.0
        band_mid = 0.5 * (min_nm + max_nm)

        def _pin_upstream(forward_nm: float) -> Tuple[Optional[str], Optional[float], Optional[float]]:
            """Return ``(name, lat, lon)`` of the nearest upstream named
            waypoint for a given forward distance along the polyline."""
            cum = 0.0
            for i in range(len(polyline) - 1):
                leg = calculate_distance_nm(
                    polyline[i][0], polyline[i][1],
                    polyline[i + 1][0], polyline[i + 1][1],
                )
                if cum + leg >= forward_nm:
                    return nodes[i][0], polyline[i][0], polyline[i][1]
                cum += leg
            if nodes:
                return nodes[0][0], polyline[0][0], polyline[0][1]
            return None, None, None

        def _frd_fix(upstream_name: Optional[str], u_lat: Optional[float],
                      u_lon: Optional[float], target_lat: float,
                      target_lon: float) -> str:
            """Encode a fix/radial/distance string so vNAS spawns AT the
            computed target position rather than at the bare waypoint.
            Format: ``<NAME><RRR><DDD>`` — radial from the fix, NM distance.
            Falls back to the bare name only when we can't pin a fix (the
            aircraft then really does spawn at that waypoint, which is the
            least-wrong behavior)."""
            if upstream_name and u_lat is not None and u_lon is not None:
                brg = int(round(calculate_bearing(
                    u_lat, u_lon, target_lat, target_lon,
                ))) % 360
                dist = max(1, int(round(calculate_distance_nm(
                    u_lat, u_lon, target_lat, target_lon,
                ))))
                return f"{upstream_name}{brg:03d}{dist:03d}"
            return upstream_name or (nodes[0][0] if nodes else '')

        # Hard constraint: within 50 NM of the ARTCC boundary (inside or
        # outside). Soft preference (via scoring): prefer in-band, then
        # closest-to-band, then closer-to-boundary.
        #
        # Keeping band as a soft preference (not hard filter) lets routes
        # that never reach the full band (e.g. KDEN→KAMA on SLEEK/DHT/PNH
        # where even SLEEK is only 195 NM from KAMA) still spawn at the
        # upstream-most in-tolerance position — ~25 NM short of band vs.
        # inside-boundary-at-50-NM from destination.
        STEP_NM = 2.0
        best: Optional[Tuple[float, float, float, float, float]] = None
        best_score = float('inf')
        if total_len > STEP_NM:
            fwd = STEP_NM
            while fwd < total_len:
                pt = interpolate_along_path(polyline, fwd)
                if not pt:
                    fwd += STEP_NM
                    continue
                lat_p, lon_p, hdg = pt
                d_to_dest = calculate_distance_nm(
                    lat_p, lon_p, anchor_lat, anchor_lon,
                )
                reach_nm = self._nm_to_artcc_boundary(lat_p, lon_p)
                if reach_nm > self.ARRIVAL_BAND_BOUNDARY_TOLERANCE_NM:
                    fwd += STEP_NM
                    continue
                # Must still point toward the destination anchor — reject
                # backtracking legs that would produce wrong-direction spawns.
                anchor_bearing = calculate_bearing(
                    lat_p, lon_p, anchor_lat, anchor_lon,
                )
                if abs((hdg - anchor_bearing + 540) % 360 - 180) > 90:
                    fwd += STEP_NM
                    continue
                # Distance to the band range (0 inside, positive outside).
                if min_nm <= d_to_dest <= max_nm:
                    band_penalty = 0.0
                elif d_to_dest < min_nm:
                    band_penalty = min_nm - d_to_dest
                else:
                    band_penalty = d_to_dest - max_nm
                # Heavy weight on band_penalty ensures any in-band candidate
                # outranks every out-of-band one. Tiebreakers: midpoint
                # proximity (within band) and boundary distance (prefer
                # closer to the boundary edge for cleaner handoffs).
                score = (
                    band_penalty * 1000.0
                    + abs(d_to_dest - band_mid)
                    + 0.05 * reach_nm
                )
                if score < best_score:
                    best_score = score
                    best = (fwd, lat_p, lon_p, hdg, d_to_dest)
                fwd += STEP_NM

        if best is not None:
            fwd, synth_lat, synth_lon, heading, synth_dist_to_dest = best
            upstream_name, u_lat, u_lon = _pin_upstream(fwd)
            return _with_polyline({
                'fix': _frd_fix(upstream_name, u_lat, u_lon, synth_lat, synth_lon),
                'latitude': synth_lat,
                'longitude': synth_lon,
                'heading': int(heading),
                'starting_conditions_type': 'FixOrFrd',
                'on_star': False,
                'actual_star_name': matching_star,
                'star_waypoint_obj': None,
                'node_index': None,
                'distance_to_dest_nm': synth_dist_to_dest,
            }, fwd)

        # 5. No polyline position satisfies band + tolerance simultaneously.
        # This happens when the filed route never approaches the ARTCC while
        # in-band (e.g., routes that enter the ARTCC deep in the terminal
        # area). Hand off at the boundary entry as a last resort — the
        # aircraft comes in from the adjacent facility on its filed route.
        return self._find_boundary_entry_spawn(
            nodes, anchor_lat, anchor_lon, matching_star,
        )

    def _find_star_spawn_waypoint(self, arrival_airport: str, star_name: str):
        """
        Find the first STAR waypoint within ARTCC boundaries using CIFP data

        Args:
            arrival_airport: Arrival airport ICAO code
            star_name: STAR name (e.g., "EAGUL6", "DINGO6", or "BRUSR" from API)

        Returns:
            Tuple of (waypoint_name, waypoint_object, actual_star_name) if found, (None, None, None) otherwise
        """
        # Get CIFP parser for arrival airport
        cifp_parser = self.cifp_parsers.get(arrival_airport)
        if not cifp_parser:
            logger.warning(f"No CIFP parser available for {arrival_airport}")
            return None, None, None

        # Try to find matching STAR - API may return "BRUSR" but CIFP has "BRUSR1"
        # Get available STARs from CIFP
        available_stars = cifp_parser.get_available_stars()
        matching_star = None

        # Strip numbers from input star name to match base name
        import re
        star_base = re.sub(r'\d+$', '', star_name.upper())

        # Look for STAR that starts with the base name
        for cifp_star in available_stars:
            cifp_star_base = re.sub(r'\d+$', '', cifp_star.upper())
            if cifp_star_base == star_base:
                matching_star = cifp_star
                logger.debug(f"Matched API STAR '{star_name}' to CIFP STAR '{cifp_star}'")
                break

        if not matching_star:
            logger.warning(f"No matching STAR found in CIFP for API STAR '{star_name}' at {arrival_airport}")
            logger.debug(f"Available STARs: {available_stars}")
            return None, None, None

        # Get all waypoints in the STAR from CIFP
        star_waypoints_list = cifp_parser.get_arrival_waypoints(matching_star)
        if not star_waypoints_list:
            logger.warning(f"No waypoints found for STAR {matching_star} at {arrival_airport}")
            return None, None, None

        logger.debug(f"Found {len(star_waypoints_list)} waypoints in STAR {matching_star}: {star_waypoints_list}")

        # Find first STAR waypoint within ARTCC boundaries
        for wp_name in star_waypoints_list:
            waypoint = cifp_parser.get_transition_waypoint(wp_name, matching_star)
            if waypoint and waypoint.latitude and waypoint.longitude:
                # Check if waypoint is within ARTCC boundaries
                if self.artcc_boundaries.is_point_in_artcc(waypoint.latitude, waypoint.longitude, self.artcc_id):
                    logger.debug(f"Found STAR waypoint {wp_name} within ARTCC {self.artcc_id} at {waypoint.latitude}, {waypoint.longitude}")
                    return wp_name, waypoint, matching_star
                else:
                    logger.debug(f"STAR waypoint {wp_name} outside ARTCC {self.artcc_id}")

        logger.warning(f"No STAR waypoints within ARTCC {self.artcc_id} for {matching_star}")
        return None, None, None

    def _get_runway_for_star(self, airport_icao: str, star_name: str, active_runways: List[str]) -> Optional[str]:
        """
        Get the appropriate arrival runway for a STAR

        Args:
            airport_icao: Airport ICAO code
            star_name: STAR name (e.g., "EAGUL6")
            active_runways: List of active runways from configuration

        Returns:
            Runway identifier or None
        """
        if not star_name or not active_runways:
            return None

        # Get CIFP parser for this airport
        cifp_parser = self.cifp_parsers.get(airport_icao)
        if not cifp_parser:
            # No CIFP parser, return first active runway
            return active_runways[0] if active_runways else None

        # Strip numeric suffix from STAR name
        star_base = re.sub(r'\d+$', '', star_name.upper())

        # Check if this STAR is valid for any of the active runways
        star_runways = cifp_parser.get_runways_for_arrival(star_name)
        if not star_runways:
            # No runway information, return first active runway
            return active_runways[0] if active_runways else None

        # Find first active runway that matches STAR's runways
        for runway in active_runways:
            runway_clean = runway.replace('RW', '').upper()
            if any(runway_clean in str(sr).upper() for sr in star_runways):
                return runway

        # No match found, return first runway from STAR
        if star_runways:
            return str(star_runways[0])

        # Fallback
        return active_runways[0] if active_runways else None

    def _next_star_waypoint(self, cifp_parser, star_name: str,
                              spawn_fix: str,
                              arrival_runway: Optional[str]) -> Optional[str]:
        """Given a spawn fix on (or anchored to) a STAR, return the next
        waypoint the aircraft should fly to.

        The STAR is partitioned into three kinds of segment:
          * **enroute-transition** segments (bring you TO the STAR) —
            identified by a non-blank ``transition_name`` that isn't the
            STAR name and isn't ``RWxx...``. Once on one, the next fix is
            the next waypoint in that transition; at its end, jump to the
            first common-segment waypoint.
          * **common segment** — waypoints whose ``transition_name`` is
            blank or equals the STAR name. Next fix is the next common
            waypoint; at its end, jump to the first waypoint of the runway
            transition matching ``arrival_runway``.
          * **runway-transition** segments — next fix is the next waypoint
            in the same transition.

        The ``spawn_fix`` may be a bare waypoint name (``BRMLY``) or a
        vNAS-style FRD string (``BRMLY142001``); the latter is parsed to
        extract its anchor before lookup. Returns ``None`` if the anchor
        isn't found anywhere in the STAR.
        """
        if not cifp_parser or not star_name:
            return None
        star_wps = getattr(cifp_parser, 'star_waypoints', {}).get(star_name, {})
        if not star_wps:
            return None

        def _seq(wp):
            return getattr(wp, 'sequence_number', 0) or 0

        common: List[Tuple[int, str]] = []
        per_rwy: Dict[str, List[Tuple[int, str]]] = {}
        enroute: Dict[str, List[Tuple[int, str]]] = {}
        for wp_name, wp in star_wps.items():
            tn = (getattr(wp, 'transition_name', '') or '').upper()
            if not tn or tn == star_name.upper():
                common.append((_seq(wp), wp_name))
            elif re.match(r'^RW\d{1,2}[LCRB]?$', tn):
                per_rwy.setdefault(tn, []).append((_seq(wp), wp_name))
            else:
                enroute.setdefault(tn, []).append((_seq(wp), wp_name))
        common.sort()
        common_names = [n for _, n in common]
        for tn in per_rwy:
            per_rwy[tn].sort()
        for tn in enroute:
            enroute[tn].sort()

        # Parse FRD form (``<FIX><RRR><DDD>``) down to its anchor fix.
        spawn_upper = (spawn_fix or '').upper()
        m = re.match(r'^([A-Z][A-Z0-9]{2,4})\d{3}\d{3}$', spawn_upper)
        if m:
            spawn_upper = m.group(1)

        common_upper = [n.upper() for n in common_names]

        # Enroute transition: walk to next waypoint; at end, hop to the
        # common segment (skipping the duplicate seam waypoint when the
        # transition's last fix matches the first common fix).
        for tn, wps in enroute.items():
            names = [n for _, n in wps]
            names_upper = [n.upper() for n in names]
            if spawn_upper in names_upper:
                idx = names_upper.index(spawn_upper)
                if idx + 1 < len(names):
                    return names[idx + 1]
                if common_names:
                    last_trans_name = names_upper[-1]
                    for cn in common_names:
                        if cn.upper() != last_trans_name:
                            return cn
                    return common_names[0]
                return None

        if spawn_upper in common_upper:
            idx = common_upper.index(spawn_upper)
            if idx + 1 < len(common_names):
                return common_names[idx + 1]
            return self._first_runway_transition_waypoint(per_rwy, arrival_runway)

        for tn, wps in per_rwy.items():
            names = [n for _, n in wps]
            names_upper = [n.upper() for n in names]
            if spawn_upper in names_upper:
                idx = names_upper.index(spawn_upper)
                if idx + 1 < len(names):
                    return names[idx + 1]
                return None

        return None

    def _first_common_star_waypoint(self, cifp_parser, star_name: str) -> Optional[str]:
        """First common-segment waypoint of ``star_name`` by sequence number.

        Used as a final-resort first-fix candidate when we can't derive a
        better one from the filed route or STAR position — e.g. vNAS rejects
        a navigation path that's only ``<STAR>.<rwy>`` with no preceding
        fly-to fix.
        """
        if not cifp_parser or not star_name:
            return None
        star_wps = getattr(cifp_parser, 'star_waypoints', {}).get(star_name, {})
        if not star_wps:
            return None
        common: List[Tuple[int, str]] = []
        for name, wp in star_wps.items():
            tn = (getattr(wp, 'transition_name', '') or '').upper()
            if not tn or tn == star_name.upper():
                common.append((getattr(wp, 'sequence_number', 0) or 0, name))
        if not common:
            return None
        common.sort()
        return common[0][1]

    def _first_runway_transition_waypoint(
        self, per_rwy: Dict[str, List[Tuple[int, str]]],
        arrival_runway: Optional[str],
    ) -> Optional[str]:
        """Pick the first waypoint of the runway transition matching
        ``arrival_runway``. Tries RWxxY, then RWxxB (parallel form), then
        RWxx (base). Falls back to the first available transition when the
        assigned runway isn't represented."""
        if not per_rwy:
            return None
        runway = (arrival_runway or '').replace('RW', '').upper()
        candidates: List[str] = []
        if runway:
            candidates.append(f'RW{runway}')
            m = re.match(r'^(\d{1,2})([LCR])$', runway)
            if m:
                base = m.group(1)
                candidates.append(f'RW{base}B')
                candidates.append(f'RW{base}')
        for c in candidates:
            if c in per_rwy and per_rwy[c]:
                return per_rwy[c][0][1]
        # Assigned runway has no transition entry — use whichever exists.
        for wps in per_rwy.values():
            if wps:
                return wps[0][1]
        return None

    def _star_runway_suffix(self, airport_icao: str, star_name: str,
                              arrival_runway: str,
                              active_runways: List[str]) -> str:
        """Build the runway-side token for a vNAS ``STAR.<RWY>`` nav-path entry.

        When two or more parallel active runways (same number, different L/C/R)
        feed this STAR via an identical runway-transition waypoint sequence,
        emit ``<num>B`` so vNAS treats the assignment as either runway. Falls
        back to the assigned runway (without the ``RW`` prefix) when no shared
        transition is detected.
        """
        cleaned = arrival_runway.replace('RW', '').upper()
        m = re.match(r'^(\d{1,2})([LCR]?)$', cleaned)
        if not m or not m.group(2):
            return cleaned
        base = m.group(1)

        cifp_parser = self.cifp_parsers.get(airport_icao)
        if not cifp_parser or not active_runways:
            return cleaned
        star_wps = getattr(cifp_parser, 'star_waypoints', {}).get(star_name, {})
        if not star_wps:
            return cleaned

        # Group waypoints by runway transition (RW25L, RW25R, ...) for this STAR.
        per_rwy: Dict[str, List[Tuple[int, str]]] = {}
        for wp_name, wp in star_wps.items():
            tn = (getattr(wp, 'transition_name', '') or '').upper()
            tm = re.match(r'^RW(\d{1,2})([LCR]?)$', tn)
            if not tm or tm.group(1) != base:
                continue
            rwy_full = tm.group(1) + tm.group(2)
            seq = getattr(wp, 'sequence_number', 0) or 0
            per_rwy.setdefault(rwy_full, []).append((seq, wp_name))

        if len(per_rwy) < 2:
            return cleaned

        ordered = {
            rwy: tuple(name for _, name in sorted(items))
            for rwy, items in per_rwy.items()
        }

        # Restrict to parallel runways that are actually active in this scenario.
        active_clean = {r.replace('RW', '').upper() for r in active_runways}
        parallel_active = [rwy for rwy in ordered if rwy in active_clean]
        if len(parallel_active) < 2:
            return cleaned

        # All parallel active runways must share the exact same transition
        # waypoint sequence to merge them into the "<num>B" form.
        if len({ordered[rwy] for rwy in parallel_active}) == 1:
            return f"{base}B"
        return cleaned

    def _has_lat_long_format(self, route: str) -> bool:
        """
        Check if route contains lat/long format coordinates or problematic airways (which vNAS can't parse)

        Args:
            route: Route string to check

        Returns:
            True if route contains lat/long format or unsupported airways
        """
        if not route:
            return False

        # Check for common lat/long patterns:
        # - N/S followed by digits (latitude)
        # - Followed by W/E and digits (longitude)
        # Examples: "N40W075", "4012N07805W", "0100S/15500W"

        # Pattern 1: DDMMN/SDDDMMW/E (e.g., 4012N07805W)
        if re.search(r'\d{4}[NS]\d{5}[EW]', route):
            return True

        # Pattern 2: Lat/Long with slashes (e.g., 0100S/15500W)
        if re.search(r'\d{4}[NS]/\d{5}[EW]', route):
            return True

        # Pattern 3: N/SDD.DD W/EDD.DD or similar decimal formats
        if re.search(r'[NS]\d+\.\d+[EW]\d+\.\d+', route):
            return True

        # Pattern 4: Simple coordinate pairs like "N40 W075"
        if re.search(r'[NS]\d+\s+[EW]\d+', route):
            return True

        # Check for G-airways (Pacific routes) which often cause errors
        # Example: G457, G345, etc.
        if re.search(r'\bG\d{3,4}\b', route):
            return True

        return False

    def _setup_difficulty_assignment(self, difficulty_config):
        """Setup difficulty assignment (copied from BaseScenario)"""
        if not difficulty_config:
            return None, 0

        difficulty_list = []
        difficulty_list.extend(['Easy'] * difficulty_config.get('easy', 0))
        difficulty_list.extend(['Medium'] * difficulty_config.get('medium', 0))
        difficulty_list.extend(['Hard'] * difficulty_config.get('hard', 0))

        random.shuffle(difficulty_list)

        return difficulty_list, 0

    def _assign_difficulty(self, aircraft, difficulty_list, difficulty_index):
        """Assign difficulty to aircraft (copied from BaseScenario)"""
        if difficulty_list and difficulty_index < len(difficulty_list):
            aircraft.difficulty = difficulty_list[difficulty_index]
            return difficulty_index + 1
        return difficulty_index

    # Enroute now inherits apply_spawn_delays from BaseScenario so all
    # scenarios share the stratified-realistic TOTAL mode and the proper
    # min-max range handling for INCREMENTAL mode.
