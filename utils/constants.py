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
    "C172", "C182", "PA28", "BE36", "C208", "PA32", "SR22", "C210", "P28A", "BE58"
]

# Flight rules
VFR = "V"
IFR = "I"

# Altitude conversion
FEET_PER_NM = 6076.12  # Nautical mile to feet
