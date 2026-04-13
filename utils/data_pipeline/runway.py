"""Runway identifier normalization + matching.

CIFP stores runway designators as `08L`, `26R`, `36C` (bare 2-digit +
optional side). The UI/API may provide `08`, `8`, `RW08`, `08L`. We match
a user-provided query against a canonical CIFP form by:

- stripping optional `RW` prefix,
- ignoring leading zeros for comparison of the digit part,
- treating a side-less query (`08`) as matching any side of the same digits
  (`08L`, `08R`, `08C`).
"""
import re
from typing import Optional

_RUNWAY_RE = re.compile(r'^(?:RW)?(\d{1,2})([LCR]?)$', re.IGNORECASE)


def canonicalize_runway(value: Optional[str]) -> Optional[str]:
    """Parse `08L`, `8`, `RW08L` etc. into a canonical `(digits, side)` tuple
    represented as e.g. `'08L'` or `'08'`. Returns None for junk."""
    if not value:
        return None
    m = _RUNWAY_RE.match(str(value).strip())
    if not m:
        return None
    digits = m.group(1).zfill(2)
    side = (m.group(2) or '').upper()
    return f"{digits}{side}"


def runway_matches(query: Optional[str], canonical: Optional[str]) -> bool:
    """True if a user-entered runway `query` refers to the same runway as the
    CIFP canonical form. If EITHER side is unspecified we treat it as a
    wildcard — CIFP sometimes stores `28` for a runway-agnostic procedure
    that serves both `28L` and `28R`, so a user query of `28L` should match.

    Examples:
        runway_matches('08', '08L')  -> True   (side-less query)
        runway_matches('08L', '08')  -> True   (side-less CIFP)
        runway_matches('8', '08R')   -> True
        runway_matches('08L', '08L') -> True
        runway_matches('08L', '08R') -> False
        runway_matches('26', '08')   -> False
    """
    q = canonicalize_runway(query)
    c = canonicalize_runway(canonical)
    if q is None or c is None:
        return False
    q_digits, q_side = q[:2], q[2:]
    c_digits, c_side = c[:2], c[2:]
    if q_digits != c_digits:
        return False
    if not q_side or not c_side:
        return True
    return q_side == c_side
