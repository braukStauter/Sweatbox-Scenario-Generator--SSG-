"""Unified flight-data and CIFP pipeline.

All scenario code should pull airport-code normalization, procedure matching,
wake-category bias, runway matching, CIFP index access, flight-pool fetching,
constraint resolution, and GA synthesis from this package rather than from
scattered `utils/*.py` modules.
"""
from utils.data_pipeline.airport import (
    to_icao,
    dedupe_by_gufi,
    dedupe_by_callsign,
    diversify_callsigns,
)
from utils.data_pipeline.procedure import (
    strip_suffix,
    matches_procedure,
    matches_any,
    format_procedures_param,
)
from utils.data_pipeline.wake import (
    WAKE_CATEGORIES,
    WakeBudget,
    split_counts,
    bucket_by_wake,
    normalize_category,
)
from utils.data_pipeline.runway import runway_matches, canonicalize_runway
from utils.data_pipeline.flight_pool import (
    fetch_departures,
    fetch_arrivals,
    fetch_artcc,
    target_pool_size,
)
from utils.data_pipeline.ga_fleet import (
    GA_FLEET,
    is_ga_type,
    pick_ifr_plan_from_pool,
    synthesize_vfr_plan,
    generate_ga_callsign,
)
from utils.data_pipeline.cifp_index import CIFPIndex, load as load_cifp_index
from utils.data_pipeline.constraints import resolve_altitude, resolve_speed

__all__ = [
    'to_icao',
    'dedupe_by_gufi',
    'dedupe_by_callsign',
    'diversify_callsigns',
    'strip_suffix',
    'matches_procedure',
    'matches_any',
    'format_procedures_param',
    'WAKE_CATEGORIES',
    'WakeBudget',
    'split_counts',
    'bucket_by_wake',
    'normalize_category',
    'runway_matches',
    'canonicalize_runway',
    'fetch_departures',
    'fetch_arrivals',
    'fetch_artcc',
    'target_pool_size',
    'GA_FLEET',
    'is_ga_type',
    'pick_ifr_plan_from_pool',
    'synthesize_vfr_plan',
    'generate_ga_callsign',
    'CIFPIndex',
    'load_cifp_index',
    'resolve_altitude',
    'resolve_speed',
]
