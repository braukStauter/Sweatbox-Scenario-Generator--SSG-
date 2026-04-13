"""Airport-code normalization + per-GUFI deduplication.

The flights API is asymmetric: `arrival=ABQ` works but `departure=ABQ` returns
nothing — only `departure=KABQ` is honored. The UI and GeoJSON files use 3-letter
FAA codes; CIFP uses K-prefixed ICAO. We normalize to ICAO whenever we hit
the flights API or the CIFP index.
"""


def to_icao(airport: str) -> str:
    """Prefix a bare 3-letter US FAA code with 'K'. 4-letter codes pass through."""
    code = (airport or '').strip().upper()
    if len(code) == 3 and code.isalpha():
        return 'K' + code
    return code


def dedupe_by_gufi(flights):
    """Drop duplicates returned across paginated API requests (same GUFI)."""
    seen = set()
    out = []
    for f in flights or []:
        gufi = f.get('gufi')
        if gufi is None:
            out.append(f)
            continue
        if gufi in seen:
            continue
        seen.add(gufi)
        out.append(f)
    return out


def dedupe_by_callsign(flights):
    """Deprecated: kept for back-compat. Prefer `diversify_callsigns`.

    Real-world airline ops legitimately reuse the same flight number daily,
    so collapsing the pool to one record per callsign throws away usable
    traffic. `diversify_callsigns` keeps every record but rewrites the
    numeric suffix so each aircraft gets a unique in-scenario callsign
    while preserving the operator prefix.
    """
    seen = set()
    out = []
    for f in flights or []:
        cs = (f.get('aircraftIdentification') or '').strip().upper()
        if not cs:
            out.append(f)
            continue
        if cs in seen:
            continue
        seen.add(cs)
        out.append(f)
    return out


import random as _random
import re as _re

# Airline callsign: 2-4 letter ICAO prefix + 1-4 digit flight number, sometimes
# followed by a single identifier letter. Examples matched:
#   FDX1583, UAL900, SWA45, AAL99X, JBU217A
# Not matched (left alone): N-numbers (`N12345`), ATC squawks, free-form text.
_AIRLINE_CS_RE = _re.compile(r'^([A-Z]{2,4})(\d{1,4})([A-Z]?)$')


def _randomize_airline_callsign(original: str, used: set, rng: _random.Random) -> str:
    """Return a new callsign with the same operator prefix but a random 3-4
    digit flight number, avoiding anything already in `used`.
    """
    m = _AIRLINE_CS_RE.match(original.strip().upper())
    if not m:
        # Non-airline pattern — leave it alone (GA tail numbers, etc.).
        return original
    operator, _old_num, suffix = m.group(1), m.group(2), m.group(3)
    for _ in range(128):
        # 3-4 digit number; skew toward 3 digits like most real airline ops.
        digits = rng.randint(1, 9999)
        new_cs = f"{operator}{digits}{suffix}"
        if new_cs not in used and new_cs != original.upper():
            used.add(new_cs)
            return new_cs
    # Fallback: append a collision-busting suffix.
    return f"{operator}{_random.randint(10000, 99999)}{suffix}"


def diversify_callsigns(flights, *, rng: _random.Random = None):
    """Rewrite every flight's `aircraftIdentification` so each has a unique
    in-scenario callsign while keeping the operator prefix.

    Mutates the flight dicts in place and returns the same list. Non-airline
    callsigns (GA tail numbers, free-form) are preserved verbatim.
    """
    rng = rng or _random.Random()
    used: set = set()
    for f in flights or []:
        cs = (f.get('aircraftIdentification') or '').strip()
        if not cs:
            continue
        new_cs = _randomize_airline_callsign(cs, used, rng)
        if new_cs != cs:
            f['aircraftIdentification'] = new_cs
    return flights
