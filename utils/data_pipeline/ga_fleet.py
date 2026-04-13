"""General-aviation fleet helpers.

The GA feature on the Aircraft Counts page expects two modes per direction:

- **VFR**: synthesize a flight plan from a hardcoded fleet list. Deterministic,
  no API dependency. Random N-number callsign, DCT route to a nearby airport.
- **IFR**: pick a flight plan from the already-fetched main API pool whose
  `aircraftType` matches one of the GA types. No extra API call.
"""
from __future__ import annotations

import random
from typing import Iterable, List, Optional

# Typical piston / light turboprop GA types used for VFR synthesis and IFR
# aircraft-type filtering. Order is the round-robin preference.
GA_FLEET: List[str] = [
    'C172', 'C182', 'SR22', 'BE36', 'PA32', 'DA40', 'BE58', 'C208', 'PC12',
]


def is_ga_type(aircraft_type: Optional[str]) -> bool:
    """True if the given ICAO aircraft-type designator is in the GA fleet."""
    if not aircraft_type:
        return False
    base = aircraft_type.strip().upper().split('/')[0]
    return base in GA_FLEET


def pick_ifr_plan_from_pool(pool: Iterable[dict], used_gufis: Optional[set] = None) -> Optional[dict]:
    """Return the first unused flight in `pool` whose aircraft type is a GA
    type. `used_gufis` is optional tracking to avoid double-assigning the
    same aircraft."""
    used_gufis = used_gufis if used_gufis is not None else set()
    for f in pool:
        if not is_ga_type(f.get('aircraftType')):
            continue
        gufi = f.get('gufi')
        if gufi and gufi in used_gufis:
            continue
        if gufi:
            used_gufis.add(gufi)
        return f
    return None


def synthesize_vfr_plan(
    origin: str,
    *,
    aircraft_type: Optional[str] = None,
    destination_hint: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> dict:
    """Return a flight-plan-shaped dict with `flight_rules='V'` for VFR GA
    spawning. The returned dict mirrors the API response shape so downstream
    scenario code can treat it the same as an API flight.

    Callers are responsible for attaching a callsign (use `generate_ga_callsign`).
    """
    r = rng or random
    ac_type = (aircraft_type or r.choice(GA_FLEET)).upper()
    destination = destination_hint or origin  # stay local by default

    return {
        'aircraftType': ac_type,
        'aircraftIdentification': generate_ga_callsign(r),
        'departureAirport': origin,
        'arrivalAirport': destination,
        'route': 'DCT',
        'initialFlightRules': 'V',
        'requestedAltitude': str(r.choice([3500, 4500, 5500, 6500, 7500])),
        'requestedAirspeed': str(r.choice([95, 110, 120, 140])),
        'departureProcedure': None,
        'arrivalProcedure': None,
        'wakeTurbulence': 'L',
        'operator': None,
        'gufi': None,
        'registration': None,
        '_synthetic_vfr_ga': True,  # marker so scenario code can branch if needed
    }


def generate_ga_callsign(rng: Optional[random.Random] = None) -> str:
    """N-number GA callsign: N + 1–3 digits + optional 1–2 letters."""
    r = rng or random
    digits = ''.join(str(r.randint(0, 9)) for _ in range(r.randint(2, 4)))
    suffix_len = r.choice([0, 1, 2])
    suffix = ''.join(r.choice('ABCDEFGHJKLMNPRSTUVWXYZ') for _ in range(suffix_len))
    return f"N{digits}{suffix}"
