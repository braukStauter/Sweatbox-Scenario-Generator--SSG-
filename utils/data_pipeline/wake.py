"""Wake-turbulence category bias helpers.

The UI exposes a per-scenario bias as three weights (L, M, H). We translate
that to integer counts so each category has an explicit quota the selector
tries to satisfy. If a category's pool is short, we backfill from other
categories with the largest remaining budget — `closely match` per user spec,
not hard-fail.
"""
import logging
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)

WAKE_CATEGORIES = ('L', 'M', 'H')


def normalize_category(value: Optional[str]) -> str:
    """Collapse anything unknown into 'M' (the safest default for airline traffic)."""
    if not value:
        return 'M'
    v = str(value).strip().upper()
    if v in WAKE_CATEGORIES:
        return v
    # vNAS/CIFP occasionally use 'J' for super or variant codes
    if v == 'J':
        return 'H'
    return 'M'


# Back-compat alias; some call sites imported the leading-underscore form.
_normalize_category = normalize_category


def split_counts(total: int, weights: Dict[str, float]) -> Dict[str, int]:
    """Distribute `total` integer slots across L/M/H using the given weights.

    Uses largest-remainder rounding so the sum always equals `total`.
    """
    total = max(0, int(total))
    if total == 0:
        return {c: 0 for c in WAKE_CATEGORIES}

    raw = {c: max(0.0, float(weights.get(c, 0))) for c in WAKE_CATEGORIES}
    denom = sum(raw.values())
    if denom <= 0:
        # Flat distribution when no bias is provided
        raw = {c: 1.0 for c in WAKE_CATEGORIES}
        denom = 3.0

    ideal = {c: raw[c] * total / denom for c in WAKE_CATEGORIES}
    floor_ = {c: int(ideal[c]) for c in WAKE_CATEGORIES}
    remaining = total - sum(floor_.values())
    # Distribute remainders by largest fractional part
    order = sorted(WAKE_CATEGORIES, key=lambda c: ideal[c] - floor_[c], reverse=True)
    for c in order[:remaining]:
        floor_[c] += 1
    return floor_


class WakeBudget:
    """Running budget tracker for wake-category slot assignment."""

    def __init__(self, counts: Dict[str, int]):
        self.budget = {c: int(counts.get(c, 0)) for c in WAKE_CATEGORIES}
        self.used = {c: 0 for c in WAKE_CATEGORIES}
        self.backfill_events = 0

    @classmethod
    def from_counts(cls, counts: Dict[str, int]) -> 'WakeBudget':
        return cls(counts)

    def total_remaining(self) -> int:
        return sum(max(0, self.budget[c] - self.used[c]) for c in WAKE_CATEGORIES)

    def preferred_category(self, available: Dict[str, int]) -> Optional[str]:
        """Pick the wake category with the highest remaining budget that still has
        at least one flight available. Returns None if nothing is available."""
        candidates = [c for c in WAKE_CATEGORIES if available.get(c, 0) > 0]
        if not candidates:
            return None

        def score(c: str) -> tuple:
            remaining = self.budget[c] - self.used[c]
            return (remaining, available.get(c, 0))
        return max(candidates, key=score)

    def consume(self, intended: str, actual: Optional[str] = None) -> None:
        """Record a consumed slot. If `actual` differs from `intended`, we count
        a backfill event (budget is still drawn from `intended`)."""
        intended = normalize_category(intended)
        if intended not in self.budget:
            return
        self.used[intended] += 1
        if actual is not None and normalize_category(actual) != intended:
            self.backfill_events += 1

    def shortfall_summary(self) -> Dict[str, int]:
        """Per-category shortfall vs. budget; non-negative values only."""
        return {c: max(0, self.budget[c] - self.used[c]) for c in WAKE_CATEGORIES}


def bucket_by_wake(flights: Iterable[dict]) -> Dict[str, list]:
    """Split a flight list by normalized wake category."""
    out: Dict[str, list] = {c: [] for c in WAKE_CATEGORIES}
    for f in flights:
        cat = normalize_category(f.get('wakeTurbulence'))
        out[cat].append(f)
    return out
