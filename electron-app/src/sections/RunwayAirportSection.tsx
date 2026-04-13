import { useScenarioStore } from '../state/scenarioStore';
import { Section, ThemedInput } from '../components/Themed';
import { RowListInput } from '../components/RowListInput';

export function RunwayAirportSection() {
  const { config, update } = useScenarioStore();
  const showSeparation = config.scenarioType === 'tower_mixed';
  return (
    <Section title="Runway & Airport">
      <RowListInput
        mode="string"
        label="Active Runways *"
        addLabel="+ Add Runway"
        emptyHint="At least one active runway is required."
        placeholder="7L"
        value={config.activeRunways}
        onChange={v => update({ activeRunways: v })}
      />

      {showSeparation && (
        <label className="stack" style={{ gap: 4 }}>
          <span style={{ fontSize: 12, color: 'var(--fg-secondary)' }}>Separation Range (NM)</span>
          <ThemedInput
            type="number"
            min={0}
            value={config.separationRange}
            onChange={e => update({ separationRange: Math.max(0, Number(e.target.value) || 0) })}
            style={{ maxWidth: 120 }}
          />
          <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
            Additional NM to add to minimum separation.
          </span>
        </label>
      )}
    </Section>
  );
}
