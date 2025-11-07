"""
Constants used throughout the application
"""

# Popular US airports for random destinations
POPULAR_US_AIRPORTS = [
    "KATL", "KLAX", "KORD", "KDFW", "KDEN", "KJFK", "KSFO", "KLAS", "KSEA", "KMCO",
    "KEWR", "KMIA", "KIAH", "KBOS", "KMSP", "KFLL", "KDTW", "KPHL", "KLGA", "KBWI",
    "KSLC", "KDCA", "KSAN", "KTPA", "KPDX", "KSTL", "KMDW", "KBNA", "KAUS", "KOAK",
    "KSAN", "KSNA", "KMSY", "KSMF", "KSAT", "KRSW", "KPBI", "KCMH", "KPIT", "KCLE",
    "KBUR", "KONT", "KABQ", "KSJC", "KBDL", "KPVD", "KMKE", "KRDU", "KCLT", "KPHX"
]

# Less common US airports for GA traffic
LESS_COMMON_AIRPORTS = [
    "KSDL", "KDVT", "KCHD", "KGEU", "KFFZ", "KIWA", "KBXK", "KPRC", "KGYR", "KTUS",
    "KFLG", "KYUM", "KIGM", "KPGA", "KGCN", "KSEZ", "KINW", "KCGZ", "KBLH", "KIFP",
    "KBYS", "KSGU", "KCDC", "KLUF", "KFUL", "KEMT", "KVNY", "KHND", "KBVU", "KSNA"
]

# Common aircraft types by category
COMMON_JETS = [
    "B738", "A320", "B739", "A321", "B737", "A319", "B38M", "A20N", "B77W", "B788",
    "B789", "A359", "B763", "B752", "B753", "A21N", "B744", "A333", "A332", "B772"
]

COMMON_GA_AIRCRAFT = [
    "C172", "C182", "BE36", "C208", "PA32", "SR22", "C210", "P28A", "BE58"
]

# Flight rules
VFR = "V"
IFR = "I"

# Altitude conversion
FEET_PER_NM = 6076.12  # Nautical mile to feet

# Typical cruise speeds (knots TAS) for common aircraft types
# Source: ICAO aircraft type database and typical flight characteristics
AIRCRAFT_CRUISE_SPEEDS = {
    # Modern narrowbody jets
    "B738": 450, "B739": 450, "B38M": 453, "B737": 450,
    "A320": 447, "A321": 447, "A319": 447, "A20N": 454, "A21N": 454,

    # Widebody jets
    "B77W": 490, "B788": 488, "B789": 488, "B78X": 488,
    "A359": 488, "A350": 488, "A333": 470, "A332": 470,
    "B744": 490, "B748": 490, "B772": 490, "B773": 490,
    "B763": 459, "B764": 459, "B752": 459, "B753": 459,

    # Regional jets
    "CRJ2": 400, "CRJ7": 447, "CRJ9": 447, "E145": 405, "E170": 447, "E175": 447, "E190": 447,

    # Business jets
    "C56X": 513, "GLF4": 476, "GLF5": 488, "GLF6": 516, "F2TH": 450, "FA7X": 488,

    # Turboprops
    "DH8D": 287, "DH8C": 287, "DH8A": 243, "AT43": 302, "AT45": 302, "AT72": 302,
    "C208": 151, "PC12": 260, "TBM9": 330,

    # General Aviation (piston)
    "C172": 110, "C182": 145, "C206": 145, "C210": 168,
    "PA28": 122, "PA32": 144, "P28A": 122,
    "BE36": 169, "BE58": 200,
    "SR20": 155, "SR22": 183,

    # Other common types
    "A306": 470, "A310": 470, "MD82": 430, "MD83": 430, "MD88": 430,
}

# Default cruise speeds by equipment suffix (fallback if aircraft type not in mapping)
DEFAULT_CRUISE_SPEEDS_BY_SUFFIX = {
    "L": 450,   # Modern airliners (jets)
    "H": 470,   # Heavy aircraft (widebody jets)
    "S": 470,   # Super heavy (A380, AN225)
    "G": 130,   # General aviation
    "A": 450,   # Advanced equipment
}

# Default cruise speed if nothing else matches
DEFAULT_CRUISE_SPEED = 450  # Generic jet
