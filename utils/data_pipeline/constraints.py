"""Spawn-state resolver honoring CIFP ARINC 424 constraints.

CIFP waypoints carry an altitude descriptor (`@` at, `+` at-or-above,
`-` at-or-below, `B` between) plus optional min/max altitudes and a speed
limit. When a vNAS arrival is spawned at one of these waypoints, we honor
the constraint rather than falling back to the API-filed assignedAltitude
— otherwise aircraft spawn outside the procedure envelope.

The resolver also walks upstream through the procedure sequence so a speed
limit earlier in the arrival (e.g. "250 below FL180") cascades to a
downstream waypoint with no explicit speed.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_altitude(waypoint, *, api_assigned: Optional[int] = None,
                     default: int = 11000) -> int:
    """Return spawn altitude in feet MSL for an arrival at `waypoint`.

    Precedence, per ARINC 424 descriptor on the waypoint record:
      - `-` (at-or-below): use `max_altitude` (spawn at the ceiling we must
        be below by the time we cross it — aircraft descend into it).
      - `@` (at): use `min_altitude`/`max_altitude` (same value).
      - `+` (at-or-above): use `max(min_altitude, api_assigned)` so we don't
        underfly the floor.
      - `B` (between): midpoint of min and max.
      - No descriptor / missing data: fall back to the existing heuristic
        (max first, then min) then `default`.
    """
    desc = getattr(waypoint, 'altitude_descriptor', None)
    lo = getattr(waypoint, 'min_altitude', None)
    hi = getattr(waypoint, 'max_altitude', None)

    if desc == '-':  # at or below
        if hi:
            return int(hi)
    elif desc == '@':  # at
        if lo:
            return int(lo)
        if hi:
            return int(hi)
    elif desc == '+':  # at or above
        if lo:
            if api_assigned:
                return max(int(lo), int(api_assigned))
            return int(lo)
    elif desc == 'B':  # between
        if lo and hi:
            return int((int(lo) + int(hi)) // 2)

    # Fallback: max first (matches most arrival expectations), then min.
    if hi:
        return int(hi)
    if lo:
        return int(lo)
    if api_assigned:
        return int(api_assigned)
    return int(default)


def resolve_speed(
    waypoint,
    *,
    star_waypoints: Optional[dict] = None,
    use_cifp_speeds: bool = True,
    api_requested: Optional[int] = None,
    fallback: Optional[int] = None,
) -> Optional[int]:
    """Return spawn speed in knots for an arrival at `waypoint`.

    Precedence:
      1. If `use_cifp_speeds`, prefer the waypoint's own speed limit.
      2. If `use_cifp_speeds` and the waypoint has no limit, walk *upstream*
         through `star_waypoints` (a `{name: Waypoint}` mapping from the
         CIFP parser/index) to find the most recent active restriction.
      3. Otherwise the API-filed `requested_airspeed`.
      4. Otherwise the caller's `fallback` value.

    Returns None if every source is empty.
    """
    if use_cifp_speeds:
        direct = getattr(waypoint, 'speed_limit', None)
        if direct:
            return int(direct)

        seq = getattr(waypoint, 'sequence_number', None)
        if star_waypoints and seq:
            # Walk backwards in sequence (ARINC 424 numbers are usually 10,20,30…).
            for back_seq in range(int(seq) - 10, 0, -10):
                for wpt in star_waypoints.values():
                    if getattr(wpt, 'sequence_number', None) == back_seq and getattr(wpt, 'speed_limit', None):
                        return int(wpt.speed_limit)

    if api_requested:
        try:
            return int(float(api_requested))
        except (ValueError, TypeError):
            pass
    return fallback
