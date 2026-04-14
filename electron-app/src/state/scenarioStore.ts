import { create } from 'zustand';
import type { ScenarioConfig, ScenarioResult } from '../../shared/types';
import { defaultBias } from '../../shared/wakeBias';

export type Screen = 'airport' | 'type' | 'config' | 'generation';

interface StoreState {
  screen: Screen;
  config: ScenarioConfig;
  // When set, Generation screen renders this imported JSON instead of
  // invoking the Python bridge. Used by "Choose JSON…" → push to vNAS.
  importedScenario: ScenarioResult | null;
  setScreen: (s: Screen) => void;
  update: (patch: Partial<ScenarioConfig>) => void;
  setImportedScenario: (r: ScenarioResult | null) => void;
  reset: () => void;
}

function initialConfig(): ScenarioConfig {
  return {
    departureAirport: '',
    arrivalAirport: undefined,
    scenarioType: 'ground_departures',
    numDepartures: 10,
    numArrivals: 5,
    numEnroute: 0,
    numOverflight: 0,
    activeRunways: [],
    separationRange: 0,
    spawnDelayEnabled: false,
    spawnDelayMode: 'incremental',
    incrementalDelayValue: '2-5',
    totalSessionMinutes: 30,
    arrivalMode: 'star',
    arrivalWaypoints: [],
    useCifpSpeeds: true,
    frd: [],
    enableVfr: false,
    numVfr: 0,
    vfrSpawnLocations: [],
    enableCifpSids: true,
    manualSids: [],
    departureDifficulty: { enabled: false, easy: 0, medium: 0, hard: 0 },
    arrivalDifficulty: { enabled: false, easy: 0, medium: 0, hard: 0 },
    arrivalAirports: [],
    departureAirports: [],
    enrouteDifficulty: { enabled: false, easy: 0, medium: 0, hard: 0 },
    arrivalSpawn: { minDistanceNm: 200, maxDistanceNm: 300 },
    overflightSpawn: { minDistanceNm: 10, maxDistanceNm: 25 },
    presetCommands: [],
    wakeBiasEnabled: false,
    wakeBias: defaultBias(),
    ga: {
      enabled: false,
      departures: { count: 0, mode: 'VFR' },
      arrivals: { count: 0, mode: 'VFR' },
    },
    customBoundary: { enabled: false, waypoints: [] },
  };
}

export const useScenarioStore = create<StoreState>(set => ({
  screen: 'airport',
  config: initialConfig(),
  importedScenario: null,
  setScreen: screen => set({ screen }),
  update: patch => set(s => ({ config: { ...s.config, ...patch } })),
  setImportedScenario: importedScenario => set({ importedScenario }),
  reset: () => set({ screen: 'airport', config: initialConfig(), importedScenario: null }),
}));
