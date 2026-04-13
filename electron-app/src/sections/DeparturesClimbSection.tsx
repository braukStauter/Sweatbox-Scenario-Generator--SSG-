import { useScenarioStore } from '../state/scenarioStore';
import { Section } from '../components/Themed';
import { RowListInput } from '../components/RowListInput';

export function DeparturesClimbSection() {
  const { config, update } = useScenarioStore();
  return (
    <Section title="Departures & Climb">
      <label className="row" style={{ gap: 8, cursor: 'pointer' }}>
        <input
          type="checkbox"
          checked={config.enableCifpSids}
          onChange={e => update({ enableCifpSids: e.target.checked })}
        />
        Use CIFP departure procedures (SIDs)
      </label>
      <span style={{ fontSize: 11, color: 'var(--fg-disabled)' }}>
        Filter API routes to SIDs matching active runways.
      </span>

      <RowListInput
        mode="string"
        label="Manual SIDs (optional)"
        addLabel="+ Add SID"
        emptyHint="Leave empty to auto-resolve SIDs from CIFP + active runways."
        placeholder="RDRNR3"
        value={config.manualSids}
        onChange={v => update({ manualSids: v })}
      />
    </Section>
  );
}
