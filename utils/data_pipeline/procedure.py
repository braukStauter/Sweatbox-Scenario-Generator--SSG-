"""Procedure (SID/STAR) name matching helpers.

The flights API stores `departureProcedure`/`arrivalProcedure` as the base
name without the revision digit (e.g. `COLTR`, not `COLTR4`). Users specify
the versioned CIFP name (`COLTR4`). We match by stripping trailing digits
from both sides, so `COLTR` and `COLTR4` are the same procedure.
"""
import re
from typing import Iterable, Optional


_TRAILING_DIGITS = re.compile(r'\d+$')


def strip_suffix(name: str) -> str:
    """Return the procedure name without its trailing numeric revision, upper-cased."""
    if not name:
        return ''
    return _TRAILING_DIGITS.sub('', name.strip().upper())


def matches_procedure(stored: Optional[str], requested: Optional[str]) -> bool:
    """True if a flight's filed procedure matches a user-requested procedure.

    Both sides are upper-cased and have trailing digits stripped before
    comparison, so `COLTR` == `COLTR4` and `EAGUL6` == `EAGUL7`.
    """
    if not stored or not requested:
        return False
    return strip_suffix(stored) == strip_suffix(requested)


def matches_any(stored: Optional[str], requested: Iterable[str]) -> bool:
    """True if `stored` matches any requested procedure."""
    return any(matches_procedure(stored, r) for r in requested)


def format_procedures_param(procedures: Iterable[str]) -> Optional[str]:
    """Format a list of procedure names for the flights API `depproc`/`arrproc`
    query parameter. Trailing digits are stripped (API stores bases) and
    joined with `+` (requests will URL-encode)."""
    if not procedures:
        return None
    bases = []
    for p in procedures:
        b = strip_suffix(p)
        if b and b not in bases:
            bases.append(b)
    return '+'.join(bases) if bases else None
