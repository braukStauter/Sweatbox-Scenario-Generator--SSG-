"""
Constants used throughout the application
"""
import json
import os

# Config loader
def _load_config():
    """Load config.json from the application root"""
    # Get the path to config.json (one level up from utils/)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(os.path.dirname(current_dir), 'config.json')

    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return empty dict if config doesn't exist or is invalid
        return {}

# Load config once on module import
_CONFIG = _load_config()

# Popular US airports for random destinations
POPULAR_US_AIRPORTS = [
    "KATL", "KLAX", "KORD", "KDFW", "KDEN", "KJFK", "KSFO", "KLAS", "KSEA", "KMCO",
    "KEWR", "KMIA", "KIAH", "KBOS", "KMSP", "KFLL", "KDTW", "KPHL", "KLGA", "KBWI",
    "KSLC", "KDCA", "KSAN", "KTPA", "KPDX", "KSTL", "KMDW", "KBNA", "KAUS", "KOAK",
    "KSAN", "KSNA", "KMSY", "KSMF", "KSAT", "KRSW", "KPBI", "KCMH", "KPIT", "KCLE",
    "KBUR", "KONT", "KABQ", "KSJC", "KBDL", "KPVD", "KMKE", "KRDU", "KCLT", "KPHX"
]

# Less common US airports for GA traffic - now loaded from config
LESS_COMMON_AIRPORTS = _CONFIG.get('less_common_airports', [
    "KSDL", "KDVT", "KCHD", "KGEU", "KFFZ", "KIWA", "KBXK", "KPRC", "KGYR", "KTUS",
    "KFLG", "KYUM", "KIGM", "KPGA", "KGCN", "KSEZ", "KINW", "KCGZ", "KBLH", "KIFP",
    "KBYS", "KSGU", "KCDC", "KLUF", "KFUL", "KEMT", "KVNY", "KHND", "KBVU", "KSNA"
])

# Common aircraft types by category
COMMON_JETS = [
    "B738", "A320", "B739", "A321", "B737", "A319", "B38M", "A20N", "B77W", "B788",
    "B789", "A359", "B763", "B752", "B753", "A21N", "B744", "A333", "A332", "B772"
]

# Common GA aircraft - now loaded from config
COMMON_GA_AIRCRAFT = _CONFIG.get('common_ga_aircraft', [
    "C172", "C182", "BE36", "C208", "PA32", "SR22", "C210", "P28A", "BE58"
])

# Flight rules
VFR = "V"
IFR = "I"

# Altitude conversion
FEET_PER_NM = 6076.12  # Nautical mile to feet
