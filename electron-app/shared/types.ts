export type WakeCat = 'L' | 'M' | 'H';

export interface WakeBias {
  L: number;
  M: number;
  H: number;
}

export interface Flight {
  callsign: string;
  aircraftType: string;
  departure: string;
  arrival: string;
  route?: string;
  cruiseSpeed?: number;
  wakeCat?: WakeCat;
  [k: string]: unknown;
}

export type ScenarioType =
  | 'ground_departures'
  | 'ground_mixed'
  | 'tower_mixed'
  | 'tracon_arrivals'
  | 'tracon_mixed'
  | 'enroute';

export type SpawnDelayMode = 'none' | 'incremental' | 'total';

export interface DifficultyCounts {
  enabled: boolean;
  easy: number;
  medium: number;
  hard: number;
}

export type GaFlightRules = 'VFR' | 'IFR';

export interface GaDirection {
  count: number;
  mode: GaFlightRules;
}

export interface GaConfig {
  enabled: boolean;          // master toggle; when false, GA spots are skipped entirely
  departures: GaDirection;   // default { count: 0, mode: 'VFR' }
  arrivals: GaDirection;
}

/**
 * New add-row input types. The bridge still accepts the legacy string shapes
 * for backward-compat with saved configs, but the UI produces these directly.
 */
export interface WaypointStarPair {
  waypoint: string;
  star: string;
}

export interface FrdEntry {
  point: string;
  altitude: number | '';
  speed: number | '';
  initialRoute: string;
}

export interface AirportRunwaysEntry {
  icao: string;
  /** Raw user input (e.g. "08, 7R"). The Python bridge's `parse_runway_map`
   *  splits this on commas at submit time; storing the raw string avoids the
   *  eaten-comma-on-round-trip bug when the user is mid-typing. */
  runways: string;
  /** Enroute-only: number of aircraft to generate at this specific airport
   *  for this direction. Sum across airports becomes the scenario's total
   *  departure/arrival count. Defaults to 0 (airport present but contributes
   *  no aircraft) — use `''` for "not yet set" via the ThemedInput. */
  count?: number | '';
  /** Enroute arrivals only: override the scenario-wide spawn distance band
   *  for this airport (NM from destination). Leave both blank to use the
   *  scenario-wide `arrivalSpawn`. */
  spawnMinNm?: number | '';
  spawnMaxNm?: number | '';
}

export interface SpawnDistanceBand {
  minDistanceNm: number;
  maxDistanceNm: number;
}

export type PresetGroupType =
  | 'all'
  | 'airline'
  | 'destination'
  | 'origin'
  | 'aircraft_type'
  | 'random'
  | 'departures'
  | 'arrivals'
  | 'parking'
  | 'sid'
  | 'star';

export interface PresetCommandRule {
  groupType: PresetGroupType;
  groupValue: string;
  commandTemplate: string;
}

export interface ScenarioConfig {
  departureAirport: string;
  arrivalAirport?: string;
  scenarioType: ScenarioType;

  numDepartures: number;
  numArrivals: number;
  /** Transient traffic: aircraft that spawn *inside* the ARTCC on random
   *  route waypoints and fly through. */
  numEnroute: number;
  /** Overflight traffic (enroute scenarios only): aircraft that spawn just
   *  OUTSIDE the ARTCC boundary and enter our airspace from the handoff
   *  point — they traverse the ARTCC but never land inside it. */
  numOverflight: number;

  activeRunways: string[];
  separationRange: number;

  spawnDelayEnabled: boolean;
  spawnDelayMode: SpawnDelayMode;
  incrementalDelayValue: string;
  totalSessionMinutes: number;

  arrivalMode: 'star' | 'frd';
  arrivalWaypoints: WaypointStarPair[];
  useCifpSpeeds: boolean;
  frd: FrdEntry[];

  enableVfr: boolean;
  numVfr: number;
  vfrSpawnLocations: string[];

  enableCifpSids: boolean;
  manualSids: string[];

  departureDifficulty: DifficultyCounts;
  arrivalDifficulty: DifficultyCounts;

  // Enroute-only — each list has one row per airport with the runways
  // served by that direction at that airport.
  arrivalAirports: AirportRunwaysEntry[];
  departureAirports: AirportRunwaysEntry[];
  enrouteDifficulty: DifficultyCounts;

  /** Enroute-only: distance (NM) from destination at which arrivals spawn.
   *  Per-airport overrides live on `AirportRunwaysEntry.spawnMinNm/Max`. */
  arrivalSpawn: SpawnDistanceBand;
  /** Enroute-only: distance (NM) outside the ARTCC boundary where overflight
   *  aircraft spawn. Random per aircraft between min and max. */
  overflightSpawn: SpawnDistanceBand;

  presetCommands: PresetCommandRule[];

  wakeBiasEnabled: boolean;
  wakeBias: WakeBias;

  ga: GaConfig;
}

export interface GenerationStats {
  requested_total: number;
  actual_total: number;
  requested: Record<string, number>;
  actual: Record<string, number>;
  shortfall: Record<string, number>;
}

export interface ScenarioResult {
  filename: string;
  contents: string;
  flightsUsed: Flight[];
  /** Count of aircraft in the generated scenario. Sourced from the Python
   *  bridge's `aircraft_count` field. For imported scenarios it defaults to
   *  `flightsUsed.length`. */
  aircraftCount: number;
  /** Enroute-only: per-type requested vs. actual counts. Lets the UI call
   *  out shortfalls when the pool couldn't satisfy every requested slot. */
  generationStats?: GenerationStats;
}

export interface VNASUploadResult {
  ok: boolean;
  status: number;
  message: string;
  scenarioId?: string;
}

/**
 * Shape of (the subset we care about of) config.json. The file carries more
 * fields (parking_airlines, less_common_airports, common_ga_aircraft) that
 * the Python side consumes directly — we only expose airport groups here.
 */
export interface SsgConfig {
  artcc_airport_groups?: Record<string, Record<string, string>>;
  [k: string]: unknown;
}

declare global {
  interface Window {
    ssg: {
      scenario: {
        generate(config: ScenarioConfig): Promise<ScenarioResult>;
        onProgress(
          cb: (ev: { stage: string; message: string; percent: number }) => void,
        ): () => void;
      };
      fs: {
        saveScenario(filename: string, contents: string): Promise<string>;
        openScenario(): Promise<{ filename: string; contents: string } | null>;
        loadConfig(): Promise<SsgConfig | null>;
      };
      airports: {
        list(): Promise<Array<{ icao: string; filename: string }>>;
      };
      vnas: {
        upload(scenarioContents: string): Promise<VNASUploadResult>;
        reset(): Promise<void>;
        clearCookies(): Promise<void>;
      };
      app: {
        checkForUpdates(): Promise<{
          currentVersion: string;
          latestVersion: string | null;
          updateAvailable: boolean;
          releaseUrl: string;
          error?: string;
        }>;
        openExternal(url: string): Promise<void>;
      };
    };
  }
}
