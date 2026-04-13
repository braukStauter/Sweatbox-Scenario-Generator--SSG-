"""Buffered, server-filtered flight-pool fetching.

Scenarios ask for `num_required` aircraft in a particular direction. We
pre-fetch more than that so attrition from `filter_valid_flights`, airline-to-
gate mismatch rejection, or wake-category shortfalls doesn't leave us short.

Buffer math:
    target = min(max(num_required * 3, 100), 1000)

When a wake budget is supplied, we fan out *per wake category* and issue
separate server-filtered fetches (`wakecat=H`, `wakecat=M`, `wakecat=L`).
This is the only way to get reliable representation of each category at
small airports — at KABQ an unfiltered pull is ~98 % medium, so client-side
bucketing would starve the H/L targets even though the API has plenty of
those flights available via the `wakecat=` query.

`fetch_all_flights` / `fetch_all_artcc_flights` paginate up to `target`, and
we dedupe across pages by GUFI. Callers receive `(flights, warnings)`; the
warnings list flags when the post-filter pool is smaller than `num_required`
so the scenario can surface a user-facing note.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Tuple

from utils.data_pipeline.airport import to_icao, dedupe_by_gufi, diversify_callsigns
from utils.data_pipeline.procedure import format_procedures_param
from utils.data_pipeline.wake import WAKE_CATEGORIES
from utils.flight_data_filter import filter_valid_flights

logger = logging.getLogger(__name__)

BUFFER_FLOOR = 100
BUFFER_CEILING = 1000
BUFFER_MULTIPLIER = 3


def target_pool_size(num_required: int) -> int:
    """Compute the API `max_flights` target for a given `num_required`.

    >>> target_pool_size(5)
    100
    >>> target_pool_size(50)
    150
    >>> target_pool_size(400)
    1000
    """
    n = max(0, int(num_required))
    return max(BUFFER_FLOOR, min(BUFFER_CEILING, n * BUFFER_MULTIPLIER))


def _per_category_target(category_count: int) -> int:
    """Buffer size for a single-category fetch when fanning out.

    Per-category floor is generous (200) because at small/hub-lite airports
    the first page of results for a rare wake class is dominated by the top
    one or two callsigns — the full set of unique operations only surfaces
    across multiple pages. Fetching through to the ceiling is wasteful on
    API quota but the results are disk-cached, so repeat runs on the same
    airport are free.
    """
    n = max(0, int(category_count))
    return max(200, min(BUFFER_CEILING, n * BUFFER_MULTIPLIER))


def _shortfall_warning(role: str, got: int, required: int) -> Optional[str]:
    if got >= required or required <= 0:
        return None
    return (
        f"{role} pool has {got} flights after filtering, below the requested "
        f"{required}. Scenario may come up short; consider relaxing procedure "
        f"filters or active runways."
    )


def _wake_fanout_targets(
    wake_counts: Optional[Dict[str, int]],
) -> Optional[Dict[str, int]]:
    """Translate a wake budget into per-category fetch targets.

    Returns a `{'H': N, 'M': N, 'L': N}` map with only non-zero categories,
    or None when no wake bias is active (caller should then do a single
    unfiltered fetch).
    """
    if not wake_counts:
        return None
    targets = {
        cat: _per_category_target(int(wake_counts.get(cat, 0) or 0))
        for cat in WAKE_CATEGORIES
        if int(wake_counts.get(cat, 0) or 0) > 0
    }
    return targets or None


def fetch_departures(
    api,
    airport: str,
    *,
    num_required: int,
    allowed_sids: Optional[Iterable[str]] = None,
    wake_counts: Optional[Dict[str, int]] = None,
) -> Tuple[List[dict], List[str]]:
    """Fetch departures for `airport`, server-filtered by SID and wake.

    Returns `(flights, warnings)`. Flights are deduped by GUFI and pass
    `filter_valid_flights`. When `wake_counts` is provided the fetch is
    fanned out per wake category (H/M/L) with a buffer sized to each
    category's requested count — this is how small airports with thin
    heavy traffic still end up with a viable heavy pool.
    """
    icao = to_icao(airport)
    warnings: List[str] = []
    depproc = format_procedures_param(allowed_sids) if allowed_sids else None

    fanout = _wake_fanout_targets(wake_counts)
    raw: List[dict] = []

    if fanout:
        logger.info(
            f"Fetching departures: departure={icao} "
            f"depproc={depproc or '(none)'} wake fanout={fanout}"
        )
        for cat, cat_target in fanout.items():
            batch = api.fetch_all_flights(
                departure=icao, depproc=depproc,
                wakecat=cat, max_flights=cat_target,
            )
            if batch:
                raw.extend(batch)
    else:
        target = target_pool_size(num_required)
        logger.info(
            f"Fetching departures: departure={icao} "
            f"depproc={depproc or '(none)'} target={target}"
        )
        raw = api.fetch_all_flights(
            departure=icao, depproc=depproc, max_flights=target,
        ) or []

    # Keep every record (an airline may run the same flight number dozens of
    # times a day in the historical feed); diversify_callsigns rewrites the
    # numeric suffix per-record so each pool aircraft has a unique callsign
    # in the generated scenario while preserving the operator prefix.
    raw = diversify_callsigns(dedupe_by_gufi(raw))
    valid = filter_valid_flights(raw)
    logger.info(f"Departures fetched: {len(raw)} unique / {len(valid)} valid")

    msg = _shortfall_warning('Departures', len(valid), num_required)
    if msg:
        warnings.append(msg)
        logger.warning(msg)

    return valid, warnings


def fetch_arrivals(
    api,
    airport: str,
    *,
    num_required: int,
    requested_stars: Optional[Iterable[str]] = None,
    wake_counts: Optional[Dict[str, int]] = None,
) -> Tuple[List[dict], List[str]]:
    """Fetch arrivals for `airport`, server-filtered by STAR and wake.

    Same per-wake fanout strategy as `fetch_departures` when `wake_counts`
    is supplied. This is the path that makes e.g. KABQ actually return
    heavies on the COLTR STAR — the unfiltered pull gets only a handful
    of H-wake flights in a mostly-medium pool.
    """
    icao = to_icao(airport)
    warnings: List[str] = []
    arrproc = format_procedures_param(requested_stars) if requested_stars else None

    fanout = _wake_fanout_targets(wake_counts)
    raw: List[dict] = []

    if fanout:
        logger.info(
            f"Fetching arrivals: arrival={icao} "
            f"arrproc={arrproc or '(none)'} wake fanout={fanout}"
        )
        for cat, cat_target in fanout.items():
            batch = api.fetch_all_flights(
                arrival=icao, arrproc=arrproc,
                wakecat=cat, max_flights=cat_target,
            )
            if batch:
                raw.extend(batch)
    else:
        target = target_pool_size(num_required)
        logger.info(
            f"Fetching arrivals: arrival={icao} "
            f"arrproc={arrproc or '(none)'} target={target}"
        )
        raw = api.fetch_all_flights(
            arrival=icao, arrproc=arrproc, max_flights=target,
        ) or []

    # Keep every record (an airline may run the same flight number dozens of
    # times a day in the historical feed); diversify_callsigns rewrites the
    # numeric suffix per-record so each pool aircraft has a unique callsign
    # in the generated scenario while preserving the operator prefix.
    raw = diversify_callsigns(dedupe_by_gufi(raw))
    valid = filter_valid_flights(raw)
    logger.info(f"Arrivals fetched: {len(raw)} unique / {len(valid)} valid")

    msg = _shortfall_warning('Arrivals', len(valid), num_required)
    if msg:
        warnings.append(msg)
        logger.warning(msg)

    return valid, warnings


def fetch_artcc(
    api,
    artcc_id: str,
    *,
    num_required: int,
) -> Tuple[List[dict], List[str]]:
    """Fetch flights transiting a specific ARTCC (used by enroute scenarios)."""
    target = target_pool_size(num_required)
    warnings: List[str] = []

    logger.info(f"Fetching ARTCC transient flights: artcc={artcc_id} target={target}")
    raw = api.fetch_all_artcc_flights(artcc_id=artcc_id, max_flights=target)

    # ARTCC transient pool gets the same treatment as dep/arr: keep every
    # record but rewrite duplicate callsigns so each aircraft has a unique id.
    raw = diversify_callsigns(dedupe_by_gufi(raw or []))
    valid = filter_valid_flights(raw)
    logger.info(f"ARTCC fetched: {len(raw)} unique / {len(valid)} valid")

    msg = _shortfall_warning('ARTCC transient', len(valid), num_required)
    if msg:
        warnings.append(msg)
        logger.warning(msg)

    return valid, warnings
