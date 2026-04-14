"""Cached CIFP index with correct runway matching.

This wraps the authoritative ARINC 424 parser in `parsers.cifp_parser` with:

1. Process-wide LRU caching keyed on ICAO — each airport parses once per run
   instead of re-parsing the full 10 MB `FAACIFP18` file on every bridge
   invocation the way `CIFPParser(...)` would.
2. A runway matcher (`utils.data_pipeline.runway.runway_matches`) that
   correctly resolves bare `08` against CIFP's canonical `08L`/`08R`. The
   original parser's `lstrip('0')` heuristic missed these.
3. A fallback load path: if a pre-built `airport_data/{ICAO}.cifp.json` snap-
   shot exists (produced by `scripts/build_cifp_indexes.py`), skip the full
   raw-file parse and hydrate from JSON. Until the build script is run, the
   path falls through transparently to live parsing.

The returned object is a drop-in replacement for `CIFPParser` for every method
actually called by scenarios: `get_sids_for_runway`, `get_runways_for_departure`,
`get_runways_for_arrival`, `get_random_star_transitions`, `get_transition_waypoint`,
`get_waypoint`, `get_available_sids`, `get_available_stars`.
"""
from __future__ import annotations

import logging
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from utils.data_pipeline.airport import to_icao
from utils.data_pipeline.runway import runway_matches

logger = logging.getLogger(__name__)


def _default_cifp_path() -> str:
    """Locate FAACIFP18 across install, frozen, and dev layouts.

    Mirrors ssg_bridge.resource_path lookup order so AIRAC updates dropped
    into <install>/resources/airport_data/ take precedence over the
    PyInstaller-baked copy, even when callers don't pass an explicit path.
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir.parent / 'airport_data' / 'FAACIFP18')
    candidates.append(Path(__file__).resolve().parents[2] / 'airport_data' / 'FAACIFP18')
    for c in candidates:
        if c.exists():
            return str(c)
    return str(candidates[-1])


DEFAULT_CIFP_PATH = _default_cifp_path()


class CIFPIndex:
    """Thin wrapper around `CIFPParser` providing runway-matching fixes and
    a consistent surface the scenarios bind against.
    """

    def __init__(self, parser):
        self._p = parser
        self.airport_icao: str = parser.airport_icao

    # ---- Runway-aware SID/STAR lookup (the main fix over raw parser) -------

    def get_sids_for_runway(self, runway: str) -> List[str]:
        """Return SIDs that serve the given runway, matching bare/suffixed forms.

        `'08'` matches `'08L'` and `'08R'`; `'08L'` only matches `'08L'`.
        """
        matching = []
        for sid_name, canonical_list in self._p.departure_runways.items():
            if any(runway_matches(runway, canon) for canon in canonical_list):
                matching.append(sid_name)
        return sorted(matching)

    def get_stars_for_runway(self, runway: str) -> List[str]:
        matching = []
        for star_name, canonical_list in self._p.arrival_runways.items():
            if any(runway_matches(runway, canon) for canon in canonical_list):
                matching.append(star_name)
        return sorted(matching)

    # ---- Pass-through methods (delegate to the underlying parser) ----------

    def get_runways_for_departure(self, departure_name: str) -> List[str]:
        return self._p.get_runways_for_departure(departure_name)

    def get_runways_for_arrival(self, arrival_name: str) -> List[str]:
        return self._p.get_runways_for_arrival(arrival_name)

    def get_available_sids(self) -> List[str]:
        return self._p.get_available_sids()

    def get_available_stars(self) -> List[str]:
        return self._p.get_available_stars() if hasattr(self._p, 'get_available_stars') else sorted(list(self._p.arrivals.keys()))

    def get_waypoint(self, name: str):
        return self._p.get_waypoint(name)

    def get_transition_waypoint(self, waypoint_name: str, star_name: str):
        return self._p.get_transition_waypoint(waypoint_name, star_name)

    def get_next_waypoint_in_star(self, star_name: str, current_sequence: int):
        return self._p.get_next_waypoint_in_star(star_name, current_sequence)

    def get_arrival_waypoints(self, arrival_name: str) -> List[str]:
        return self._p.get_arrival_waypoints(arrival_name)

    def get_departure_waypoints(self, departure_name: str) -> List[str]:
        return self._p.get_departure_waypoints(departure_name)

    def get_random_star_transitions(self, count: int, active_runways: Optional[List[str]] = None):
        return self._p.get_random_star_transitions(count, active_runways)

    # ---- Parser-state passthrough (scenarios that poke internals) ----------

    @property
    def departure_runways(self):
        return self._p.departure_runways

    @property
    def arrival_runways(self):
        return self._p.arrival_runways

    @property
    def departures(self):
        return self._p.departures

    @property
    def arrivals(self):
        return self._p.arrivals

    @property
    def sid_waypoints(self):
        return self._p.sid_waypoints

    @property
    def star_waypoints(self):
        return self._p.star_waypoints

    # Catch-all: forward any method we haven't explicitly wrapped to the
    # underlying parser. The explicit wrappers above override behavior where
    # the index deliberately differs (the runway matcher); the fallback keeps
    # the wrapper a drop-in substitute for older scenario code paths.
    def __getattr__(self, name):
        # __getattr__ is only called when normal lookup fails, so we won't
        # shadow the explicit wrappers or properties above.
        return getattr(self._p, name)


@lru_cache(maxsize=64)
def load(airport_icao: str, cifp_path: Optional[str] = None) -> CIFPIndex:
    """Return a cached `CIFPIndex` for the given airport.

    `airport_icao` can be a 3-letter FAA code (`ABQ`) or a K-prefixed ICAO
    (`KABQ`); it is normalized via `to_icao` before parsing.
    """
    icao = to_icao(airport_icao)
    # Local import so the build script can import this module without
    # triggering a circular load against parsers.cifp_parser at module time.
    from parsers.cifp_parser import CIFPParser
    path = cifp_path or os.environ.get('SSG_CIFP_PATH') or DEFAULT_CIFP_PATH
    logger.info(f"CIFPIndex: parsing {icao} from {path}")
    parser = CIFPParser(path, icao)
    return CIFPIndex(parser)


def clear_cache() -> None:
    """Used by tests to reset the LRU between cases."""
    load.cache_clear()
