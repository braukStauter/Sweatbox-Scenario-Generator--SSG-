import { useScenarioStore } from '../state/scenarioStore';
import { Section, ThemedInput } from '../components/Themed';

export function TimingSpawningSection() {
  const { config, update } = useScenarioStore();
  const isIncremental = config.spawnDelayMode === 'incremental';
  return (
    <Section title="Timing & Spawning">
      <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={config.spawnDelayEnabled}
          onChange={e => update({ spawnDelayEnabled: e.target.checked })}
        />
        <strong>Enable spawn delays</strong>
      </label>

      <div
        className="stack"
        style={{
          opacity: config.spawnDelayEnabled ? 1 : 0.55,
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: 12,
        }}
      >
        <div className="row" style={{ gap: 16 }}>
          <label className="row" style={{ gap: 6 }}>
            <input
              type="radio"
              name="spawnMode"
              disabled={!config.spawnDelayEnabled}
              checked={isIncremental}
              onChange={() => update({ spawnDelayMode: 'incremental' })}
            />
            Incremental
          </label>
          <label className="row" style={{ gap: 6 }}>
            <input
              type="radio"
              name="spawnMode"
              disabled={!config.spawnDelayEnabled}
              checked={!isIncremental}
              onChange={() => update({ spawnDelayMode: 'total' })}
            />
            Total (Realistic)
          </label>
        </div>

        {isIncremental ? (
          <label className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>Delay (min)</span>
            <ThemedInput
              placeholder="2-5 or 3"
              disabled={!config.spawnDelayEnabled}
              value={config.incrementalDelayValue}
              onChange={e => update({ incrementalDelayValue: e.target.value })}
              style={{ maxWidth: 160 }}
            />
            <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
              Range or fixed value in minutes.
            </span>
          </label>
        ) : (
          <label className="stack" style={{ gap: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>Total session (min)</span>
            <ThemedInput
              type="number"
              min={1}
              disabled={!config.spawnDelayEnabled}
              value={config.totalSessionMinutes}
              onChange={e => update({ totalSessionMinutes: Math.max(1, Number(e.target.value) || 1) })}
              style={{ maxWidth: 160 }}
            />
            <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
              Desired training session length.
            </span>
          </label>
        )}
      </div>
    </Section>
  );
}
