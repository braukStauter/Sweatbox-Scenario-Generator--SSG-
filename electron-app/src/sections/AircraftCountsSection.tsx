import { useScenarioStore } from '../state/scenarioStore';
import { Section, ThemedInput } from '../components/Themed';
import { WakeCategoryBias } from '../components/WakeCategoryBias';
import { GeneralAviationCounts } from '../components/GeneralAviationCounts';
import { DifficultyBlock } from './DifficultyBlock';
import type { DifficultyCounts } from '../../shared/types';

function sumDiff(d: DifficultyCounts): number {
  return (d.easy || 0) + (d.medium || 0) + (d.hard || 0);
}

export function AircraftCountsSection() {
  const { config, update } = useScenarioStore();
  const isEnroute = config.scenarioType === 'enroute';
  // Enroute scenarios set arrival/departure counts per-airport in the
  // "Airports & Routes" section (each AirportRunwaysEntry has its own count),
  // so we suppress the global totals here to avoid a confusing double source.
  const showDepartures =
    !isEnroute && config.scenarioType !== 'tracon_arrivals';
  const showArrivals =
    !isEnroute && config.scenarioType !== 'ground_departures';
  const showEnroute = isEnroute;

  const depLocked = config.departureDifficulty.enabled;
  const arrLocked = config.arrivalDifficulty.enabled;
  const enrLocked = config.enrouteDifficulty.enabled;

  const depValue = depLocked ? sumDiff(config.departureDifficulty) : config.numDepartures;
  const arrValue = arrLocked ? sumDiff(config.arrivalDifficulty) : config.numArrivals;
  const enrValue = enrLocked ? sumDiff(config.enrouteDifficulty) : config.numEnroute;

  return (
    <Section title="Aircraft Counts">
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        {showDepartures && (
          <label className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>
              Departures{depLocked && ' (from difficulty)'}
            </span>
            <ThemedInput
              type="number"
              min={0}
              disabled={depLocked}
              value={depValue}
              onChange={e => update({ numDepartures: Math.max(0, Number(e.target.value) || 0) })}
              style={{ width: 120 }}
            />
          </label>
        )}
        {showArrivals && (
          <label className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>
              Arrivals{arrLocked && ' (from difficulty)'}
            </span>
            <ThemedInput
              type="number"
              min={0}
              disabled={arrLocked}
              value={arrValue}
              onChange={e => update({ numArrivals: Math.max(0, Number(e.target.value) || 0) })}
              style={{ width: 120 }}
            />
          </label>
        )}
        {showEnroute && (
          <label className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>
              Enroute{enrLocked && ' (from difficulty)'}
            </span>
            <ThemedInput
              type="number"
              min={0}
              disabled={enrLocked}
              value={enrValue}
              onChange={e => update({ numEnroute: Math.max(0, Number(e.target.value) || 0) })}
              style={{ width: 120 }}
            />
            <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
              Spawn inside ARTCC on route.
            </span>
          </label>
        )}
        {showEnroute && (
          <label className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>Overflight</span>
            <ThemedInput
              type="number"
              min={0}
              value={config.numOverflight}
              onChange={e => update({ numOverflight: Math.max(0, Number(e.target.value) || 0) })}
              style={{ width: 120 }}
            />
            <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
              Spawn just outside ARTCC boundary, transit through.
            </span>
          </label>
        )}
      </div>

      {showEnroute && (
        <div className="row" style={{ gap: 24, flexWrap: 'wrap', marginTop: 12 }}>
          <div className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>
              Arrival spawn distance from destination (NM)
            </span>
            <div className="row" style={{ gap: 8 }}>
              <ThemedInput
                type="number"
                min={0}
                value={config.arrivalSpawn.minDistanceNm}
                onChange={e =>
                  update({
                    arrivalSpawn: {
                      ...config.arrivalSpawn,
                      minDistanceNm: Math.max(0, Number(e.target.value) || 0),
                    },
                  })
                }
                style={{ width: 80 }}
              />
              <span style={{ alignSelf: 'center', color: 'var(--fg-secondary)' }}>to</span>
              <ThemedInput
                type="number"
                min={0}
                value={config.arrivalSpawn.maxDistanceNm}
                onChange={e =>
                  update({
                    arrivalSpawn: {
                      ...config.arrivalSpawn,
                      maxDistanceNm: Math.max(0, Number(e.target.value) || 0),
                    },
                  })
                }
                style={{ width: 80 }}
              />
            </div>
            <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
              Aircraft spawn within this range of their destination airport.
              Per-airport override available in Airports & Routes.
            </span>
          </div>
          <div className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>
              Overflight spawn distance outside boundary (NM)
            </span>
            <div className="row" style={{ gap: 8 }}>
              <ThemedInput
                type="number"
                min={0}
                value={config.overflightSpawn.minDistanceNm}
                onChange={e =>
                  update({
                    overflightSpawn: {
                      ...config.overflightSpawn,
                      minDistanceNm: Math.max(0, Number(e.target.value) || 0),
                    },
                  })
                }
                style={{ width: 80 }}
              />
              <span style={{ alignSelf: 'center', color: 'var(--fg-secondary)' }}>to</span>
              <ThemedInput
                type="number"
                min={0}
                value={config.overflightSpawn.maxDistanceNm}
                onChange={e =>
                  update({
                    overflightSpawn: {
                      ...config.overflightSpawn,
                      maxDistanceNm: Math.max(0, Number(e.target.value) || 0),
                    },
                  })
                }
                style={{ width: 80 }}
              />
            </div>
            <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
              Random per aircraft. All distances are outside the ARTCC.
            </span>
          </div>
        </div>
      )}

      {showDepartures && (
        <DifficultyBlock
          label="Departure Difficulty"
          value={config.departureDifficulty}
          onChange={v => update({ departureDifficulty: v })}
        />
      )}
      {showArrivals && (
        <DifficultyBlock
          label="Arrival Difficulty"
          value={config.arrivalDifficulty}
          onChange={v => update({ arrivalDifficulty: v })}
        />
      )}
      {showEnroute && (
        <DifficultyBlock
          label="Enroute Difficulty"
          value={config.enrouteDifficulty}
          onChange={v => update({ enrouteDifficulty: v })}
        />
      )}

      <WakeCategoryBias
        enabled={config.wakeBiasEnabled}
        bias={config.wakeBias}
        onEnabledChange={v => update({ wakeBiasEnabled: v })}
        onBiasChange={b => update({ wakeBias: b })}
      />

      {config.scenarioType !== 'enroute' && (
        <GeneralAviationCounts value={config.ga} onChange={v => update({ ga: v })} />
      )}
    </Section>
  );
}
