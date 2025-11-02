"""
Spawn delay mode enumeration
"""
from enum import Enum


class SpawnDelayMode(Enum):
    """Enumeration for spawn delay modes"""
    NONE = "none"           # All aircraft spawn at once (no delays)
    INCREMENTAL = "incremental"  # Delays accumulate between each aircraft
    TOTAL = "total"         # Random delays distributed across total session time
