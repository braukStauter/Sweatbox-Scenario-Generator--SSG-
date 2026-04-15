"""
Indicated-airspeed and Mach estimates for filed flight plans.

vNAS reads `cruiseSpeed` in filed plans as KIAS (indicated). Using true/ground
speed there produces garbage flight strips at altitude. For airborne spawns at
FL200 and above we additionally set a cruise Mach — that's what real ATC sees
on the strip for jets in the flight levels.
"""
import math


_KIAS_BY_PREFIX = {
    # Heavy / long-haul
    'B74': 290, 'B77': 290, 'B78': 290, 'A33': 290, 'A34': 290, 'A35': 290, 'A38': 290,
    # Large narrowbody
    'B73': 280, 'B75': 280, 'B76': 280, 'A31': 280, 'A32': 280, 'A21': 280, 'B38': 280, 'B39': 280,
    # Regional jets
    'CRJ': 270, 'E17': 270, 'E19': 270, 'E13': 260, 'E14': 260, 'E54': 260, 'MD8': 280, 'MD9': 280,
    # Business jets
    'CL3': 280, 'CL6': 280, 'GLF': 280, 'C56': 260, 'C68': 270, 'FA': 280,
    # Turboprops
    'DH8': 230, 'AT7': 230, 'AT4': 230, 'SF3': 220, 'BE2': 220, 'PC1': 220, 'TBM': 220,
    # Piston singles / twins
    'C1': 120, 'C2': 130, 'P28': 120, 'BE3': 160, 'BE5': 160, 'BE9': 180,
    'PA': 130, 'SR2': 140, 'COL': 150,
}

_MACH_BY_PREFIX = {
    'B74': 0.84, 'B77': 0.83, 'B78': 0.82, 'A33': 0.82, 'A34': 0.82, 'A35': 0.83, 'A38': 0.82,
    'B73': 0.78, 'B75': 0.78, 'B76': 0.80, 'A31': 0.78, 'A32': 0.78, 'A21': 0.78, 'B38': 0.78, 'B39': 0.78,
    'CRJ': 0.74, 'E17': 0.76, 'E19': 0.78, 'E13': 0.74, 'E14': 0.74, 'E54': 0.76, 'MD8': 0.76, 'MD9': 0.76,
    'CL3': 0.80, 'CL6': 0.82, 'GLF': 0.85, 'C56': 0.72, 'C68': 0.78, 'FA': 0.80,
    'DH8': 0.50, 'AT7': 0.50, 'AT4': 0.48, 'SF3': 0.48, 'BE2': 0.48, 'PC1': 0.48, 'TBM': 0.52,
}

_DEFAULT_JET_KIAS = 280
_DEFAULT_PROP_KIAS = 140
_DEFAULT_JET_MACH = 0.78


def _base_type(aircraft_type: str) -> str:
    if not aircraft_type:
        return ''
    return aircraft_type.split('/')[0].upper()


def _looks_like_prop(base: str) -> bool:
    return any(base.startswith(p) for p in ('C1', 'C2', 'P28', 'BE', 'PA', 'SR', 'COL', 'DH', 'AT', 'SF', 'PC', 'TBM'))


def indicated_cruise_kias(aircraft_type: str) -> int:
    """Typical filed KIAS for this aircraft type."""
    base = _base_type(aircraft_type)
    for prefix, kias in _KIAS_BY_PREFIX.items():
        if base.startswith(prefix):
            return kias
    return _DEFAULT_PROP_KIAS if _looks_like_prop(base) else _DEFAULT_JET_KIAS


def cruise_mach(aircraft_type: str) -> float:
    """Typical cruise Mach for this aircraft type."""
    base = _base_type(aircraft_type)
    for prefix, mach in _MACH_BY_PREFIX.items():
        if base.startswith(prefix):
            return mach
    return _DEFAULT_JET_MACH


def speed_of_sound_kt(altitude_ft: int) -> float:
    """Speed of sound in standard atmosphere, knots TAS.
    a = 661.5 * sqrt(1 - 0.00000687558 * h) for h in feet, capped at ~FL650."""
    h = max(0, min(altitude_ft, 65000))
    ratio = max(0.0, 1.0 - 0.00000687558 * h)
    return 661.5 * math.sqrt(ratio)


def ground_speed_from_mach(mach: float, altitude_ft: int) -> int:
    """Approximate ground speed (=TAS in zero-wind) for a given Mach at altitude."""
    return int(round(mach * speed_of_sound_kt(altitude_ft)))


def ground_speed_from_kias(kias: int, altitude_ft: int) -> int:
    """Cheap TAS approximation: +2% per 1000 ft above sea level."""
    return int(round(kias * (1.0 + 0.02 * (altitude_ft / 1000.0))))
